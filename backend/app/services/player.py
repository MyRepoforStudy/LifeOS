from datetime import date, datetime, timedelta

from sqlalchemy import Date, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import dates
from app.domain.enums import AttributeType, OccurrenceStatus, QuestStatus
from app.domain.levels import LevelCurve, level_for_xp, level_progress
from app.errors import InvalidRequest
from app.models import Attribute, PlayerProfile, Quest, QuestOccurrence, User, XpLedgerEntry
from app.schemas import (
    AttributeOut,
    DailyXp,
    LedgerEntryOut,
    ProfileOut,
    ProfileUpdateIn,
    StatisticsOut,
    XpHistoryOut,
)

MAX_STATISTICS_DAYS = 366


def effective_timezone(user: User, now: datetime) -> str:
    """Time zone in force at `now`: a pending change applies from its start instant."""
    if user.pending_timezone and user.pending_timezone_from and now >= user.pending_timezone_from:
        return user.pending_timezone
    return user.timezone


def _promote_pending_timezone(user: User, now: datetime) -> None:
    if user.pending_timezone and user.pending_timezone_from and now >= user.pending_timezone_from:
        user.timezone = user.pending_timezone
        user.pending_timezone = None
        user.pending_timezone_from = None


async def get_profile(session: AsyncSession, user: User, now: datetime, curve: LevelCurve) -> ProfileOut:
    profile = await session.scalar(select(PlayerProfile).where(PlayerProfile.user_id == user.id))
    assert profile is not None
    active_quests = await session.scalar(
        select(func.count())
        .select_from(Quest)
        .where(Quest.user_id == user.id, Quest.deleted_at.is_(None), Quest.status == QuestStatus.ACTIVE)
    )
    completed_quests, last_activity = (
        await session.execute(
            select(func.count(), func.max(QuestOccurrence.completed_at)).where(
                QuestOccurrence.user_id == user.id, QuestOccurrence.status == OccurrenceStatus.COMPLETED
            )
        )
    ).one()
    progress = level_progress(profile.total_xp, profile.current_level, curve)
    pending = user.pending_timezone if effective_timezone(user, now) == user.timezone else None
    return ProfileOut(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_url=profile.avatar_url,
        registered_at=user.created_at,
        development_started_on=profile.development_started_on,
        timezone=effective_timezone(user, now),
        pending_timezone=pending,
        pending_timezone_from=user.pending_timezone_from if pending else None,
        level=progress.level,
        total_xp=progress.total_xp,
        xp_in_level=progress.xp_in_level,
        xp_for_level=progress.xp_for_level,
        xp_to_next_level=progress.xp_to_next_level,
        level_progress=progress.progress,
        active_quests=active_quests or 0,
        completed_quests=completed_quests or 0,
        last_activity_at=last_activity,
    )


async def update_profile(session: AsyncSession, user: User, data: ProfileUpdateIn, now: datetime) -> None:
    fields = data.model_fields_set
    profile = await session.scalar(select(PlayerProfile).where(PlayerProfile.user_id == user.id))
    assert profile is not None

    if "display_name" in fields:
        if data.display_name is None:
            raise InvalidRequest("display_name cannot be empty", code="display_name_required")
        user.display_name = data.display_name
    if "avatar_url" in fields:
        profile.avatar_url = data.avatar_url
    if "development_started_on" in fields:
        profile.development_started_on = data.development_started_on
    if "timezone" in fields:
        if data.timezone is None:
            raise InvalidRequest("timezone cannot be empty", code="timezone_required")
        _promote_pending_timezone(user, now)
        if data.timezone == user.timezone:
            user.pending_timezone = None
            user.pending_timezone_from = None
        else:
            # The new zone starts at the next local midnight of the current one, so a
            # change can neither add nor remove a day that is already running.
            user.pending_timezone = data.timezone
            user.pending_timezone_from = dates.next_local_midnight(user.timezone, now)
    session.add(user)
    await session.flush()


async def get_attributes(session: AsyncSession, user: User, now: datetime, curve: LevelCurve) -> list[AttributeOut]:
    attributes = (await session.execute(select(Attribute).where(Attribute.user_id == user.id))).scalars().all()
    since_7 = now - timedelta(days=7)
    since_30 = now - timedelta(days=30)
    rows = await session.execute(
        select(
            XpLedgerEntry.attribute_type,
            func.coalesce(func.sum(XpLedgerEntry.xp_amount).filter(XpLedgerEntry.created_at >= since_7), 0),
            func.coalesce(func.sum(XpLedgerEntry.xp_amount), 0),
        )
        .where(
            XpLedgerEntry.user_id == user.id,
            XpLedgerEntry.attribute_type.is_not(None),
            XpLedgerEntry.created_at >= since_30,
        )
        .group_by(XpLedgerEntry.attribute_type)
    )
    recent = {attr: (int(xp7), int(xp30)) for attr, xp7, xp30 in rows}
    order = {a.value: i for i, a in enumerate(AttributeType)}
    result = []
    for attribute in sorted(attributes, key=lambda a: order.get(a.attribute_type, 99)):
        level = level_for_xp(attribute.total_xp, curve)
        progress = level_progress(attribute.total_xp, level, curve)
        xp7, xp30 = recent.get(attribute.attribute_type, (0, 0))
        result.append(
            AttributeOut(
                attribute_type=AttributeType(attribute.attribute_type),
                level=level,
                total_xp=attribute.total_xp,
                xp_in_level=progress.xp_in_level,
                xp_for_level=progress.xp_for_level,
                xp_to_next_level=progress.xp_to_next_level,
                level_progress=progress.progress,
                xp_last_7_days=xp7,
                xp_last_30_days=xp30,
            )
        )
    return result


async def xp_history(
    session: AsyncSession,
    user: User,
    now: datetime,
    *,
    limit: int,
    offset: int,
    date_from: date | None,
    date_to: date | None,
) -> XpHistoryOut:
    tz = effective_timezone(user, now)
    stmt = select(XpLedgerEntry).where(XpLedgerEntry.user_id == user.id)
    if date_from:
        stmt = stmt.where(XpLedgerEntry.created_at >= dates.day_bounds(tz, date_from)[0])
    if date_to:
        stmt = stmt.where(XpLedgerEntry.created_at < dates.day_bounds(tz, date_to)[1])
    stmt = stmt.order_by(XpLedgerEntry.created_at.desc(), XpLedgerEntry.id.desc()).offset(offset).limit(limit + 1)
    entries = (await session.execute(stmt)).scalars().all()
    has_more = len(entries) > limit
    return XpHistoryOut(
        items=[LedgerEntryOut.model_validate(e) for e in entries[:limit]],
        next_offset=offset + limit if has_more else None,
    )


async def statistics(
    session: AsyncSession,
    user: User,
    now: datetime,
    *,
    date_from: date | None,
    date_to: date | None,
) -> StatisticsOut:
    tz = effective_timezone(user, now)
    end_day = date_to or dates.local_date(tz, now)
    start_day = date_from or end_day - timedelta(days=29)
    if start_day > end_day:
        raise InvalidRequest("date_from must not be after date_to", code="invalid_period")
    if (end_day - start_day).days + 1 > MAX_STATISTICS_DAYS:
        raise InvalidRequest(f"The period cannot exceed {MAX_STATISTICS_DAYS} days", code="period_too_long")
    start, _ = dates.day_bounds(tz, start_day)
    _, end = dates.day_bounds(tz, end_day)

    local_day = cast(func.timezone(tz, XpLedgerEntry.created_at), Date)
    in_period = (
        XpLedgerEntry.user_id == user.id,
        XpLedgerEntry.created_at >= start,
        XpLedgerEntry.created_at < end,
    )
    # GROUP BY 1: grouping by the expression itself would bind the time zone twice
    # as two different parameters, which PostgreSQL treats as different expressions.
    by_day = {
        day: int(xp)
        for day, xp in await session.execute(
            select(local_day, func.sum(XpLedgerEntry.xp_amount)).where(*in_period).group_by(text("1"))
        )
    }
    by_attribute = {
        (attr or "none"): int(xp)
        for attr, xp in await session.execute(
            select(XpLedgerEntry.attribute_type, func.sum(XpLedgerEntry.xp_amount))
            .where(*in_period)
            .group_by(XpLedgerEntry.attribute_type)
        )
    }
    completed = await session.scalar(
        select(func.count()).where(
            QuestOccurrence.user_id == user.id,
            QuestOccurrence.status == OccurrenceStatus.COMPLETED,
            QuestOccurrence.completed_at >= start,
            QuestOccurrence.completed_at < end,
        )
    )
    skipped = await session.scalar(
        select(func.count()).where(
            QuestOccurrence.user_id == user.id,
            QuestOccurrence.status == OccurrenceStatus.SKIPPED,
            QuestOccurrence.skipped_at >= start,
            QuestOccurrence.skipped_at < end,
        )
    )
    days = [start_day + timedelta(days=i) for i in range((end_day - start_day).days + 1)]
    return StatisticsOut(
        date_from=start_day,
        date_to=end_day,
        timezone=tz,
        total_xp=sum(by_day.values()),
        quests_completed=completed or 0,
        quests_skipped=skipped or 0,
        xp_by_day=[DailyXp(date=d, xp=by_day.get(d, 0)) for d in days],
        xp_by_attribute=by_attribute,
    )
