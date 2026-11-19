"""Quest engine: creation, completion, skip and undo.

Lock order for every write path: quest row -> occurrence row -> player profile.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domain import dates
from app.domain.enums import (
    CATEGORY_DEFAULT_ATTRIBUTE,
    LATE_COMPLETION_TYPES,
    ONE_OFF_TYPES,
    Activity,
    AttributeType,
    Difficulty,
    EffectiveQuestStatus,
    LedgerReason,
    LedgerSource,
    OccurrenceStatus,
    QuestStatus,
    QuestType,
    XpLimitReason,
)
from app.domain.rewards import RewardRules, quest_reward, scaled_learning_reward, split_xp
from app.errors import Conflict, InvalidRequest, NotFound
from app.models import Quest, QuestOccurrence, User, XpLedgerEntry, new_id
from app.schemas import (
    ChecklistItem,
    CompletionOut,
    OccurrenceOut,
    QuestCreateIn,
    QuestDetailOut,
    QuestListOut,
    QuestOut,
    QuestUpdateIn,
    SkipOut,
    UndoOut,
)
from app.services.game_config import GameSettings
from app.services.player import effective_timezone
from app.services.xp import LedgerDraft, apply_xp, lock_profile, player_xp_out

# --- time windows ---------------------------------------------------------------------


def current_occurrence_date(quest: Quest, tz: str, now: datetime) -> date | None:
    """The occurrence that can be completed or skipped right now, or None."""
    if quest.deleted_at is not None or quest.status == QuestStatus.CANCELLED or now < quest.starts_at:
        return None
    today = dates.local_date(tz, now)
    if quest.is_recurring:
        if quest.due_at is not None and now > quest.due_at:
            return None
        if quest.quest_type == QuestType.WEEKLY:
            return dates.week_start(today)
        if quest.weekdays and today.isoweekday() not in quest.weekdays:
            return None
        return today
    anchor = quest.anchor_date
    if quest.quest_type == QuestType.DAILY:
        return anchor if today == anchor else None
    if quest.quest_type == QuestType.WEEKLY:
        return anchor if dates.week_start(today) == dates.week_start(anchor) else None
    if quest.due_at is not None and now > quest.due_at and quest.quest_type not in LATE_COMPLETION_TYPES:
        return None
    return anchor


def _display_occurrence_date(quest: Quest, tz: str, now: datetime) -> date | None:
    """Which occurrence to show: the current one, or the only one of a one-off quest."""
    if not quest.is_recurring:
        return quest.anchor_date
    return current_occurrence_date(quest, tz, now)


def effective_status(
    quest: Quest, occurrence: QuestOccurrence | None, tz: str, now: datetime
) -> EffectiveQuestStatus:
    if quest.deleted_at is not None or quest.status == QuestStatus.CANCELLED:
        return EffectiveQuestStatus.CANCELLED
    if not quest.is_recurring:
        if quest.status == QuestStatus.COMPLETED:
            return EffectiveQuestStatus.COMPLETED
        if quest.status == QuestStatus.SKIPPED:
            return EffectiveQuestStatus.SKIPPED
        if now < quest.starts_at:
            return EffectiveQuestStatus.PENDING
        if current_occurrence_date(quest, tz, now) is None:
            return EffectiveQuestStatus.EXPIRED
        return EffectiveQuestStatus.ACTIVE
    if now < quest.starts_at:
        return EffectiveQuestStatus.PENDING
    if quest.due_at is not None and now > quest.due_at:
        return EffectiveQuestStatus.EXPIRED
    if occurrence is not None and occurrence.status == OccurrenceStatus.COMPLETED:
        return EffectiveQuestStatus.COMPLETED
    if occurrence is not None and occurrence.status == OccurrenceStatus.SKIPPED:
        return EffectiveQuestStatus.SKIPPED
    return EffectiveQuestStatus.ACTIVE


def _actionable_date(quest: Quest, tz: str, now: datetime) -> date:
    if quest.status == QuestStatus.CANCELLED:
        raise Conflict("The quest is cancelled", code="quest_cancelled")
    if now < quest.starts_at:
        raise Conflict("The quest has not started yet", code="quest_not_started")
    occurrence_date = current_occurrence_date(quest, tz, now)
    if occurrence_date is None:
        ended = quest.due_at is not None and now > quest.due_at
        if quest.is_recurring and not ended:
            raise Conflict("The quest is not scheduled for today", code="not_scheduled_today")
        raise Conflict("The quest has expired", code="quest_expired")
    return occurrence_date


# --- views ----------------------------------------------------------------------------


def quest_out(quest: Quest, occurrence: QuestOccurrence | None, tz: str, now: datetime) -> QuestOut:
    shown_date = _display_occurrence_date(quest, tz, now)
    shown = occurrence if occurrence is not None and occurrence.occurrence_date == shown_date else None
    return QuestOut(
        id=quest.id,
        title=quest.title,
        description=quest.description,
        quest_type=QuestType(quest.quest_type),
        category=quest.category,
        attribute_types=[AttributeType(a) for a in quest.attribute_types],
        activity=Activity(quest.activity),
        difficulty=Difficulty(quest.difficulty),
        target_minutes=quest.target_minutes,
        xp_reward=quest.xp_reward,
        status=effective_status(quest, shown, tz, now),
        is_recurring=quest.is_recurring,
        weekdays=quest.weekdays,
        priority=quest.priority,
        checklist=[ChecklistItem(**item) for item in quest.checklist],
        starts_at=quest.starts_at,
        due_at=quest.due_at,
        completed_at=quest.completed_at,
        created_at=quest.created_at,
        updated_at=quest.updated_at,
        current_occurrence_date=current_occurrence_date(quest, tz, now),
        current_occurrence=OccurrenceOut.model_validate(shown) if shown else None,
    )


async def _occurrences_for_display(
    session: AsyncSession, quests: list[Quest], tz: str, now: datetime
) -> dict[uuid.UUID, QuestOccurrence]:
    wanted = {q.id: d for q in quests if (d := _display_occurrence_date(q, tz, now)) is not None}
    if not wanted:
        return {}
    rows = await session.execute(
        select(QuestOccurrence).where(
            QuestOccurrence.quest_id.in_(list(wanted.keys())),
            QuestOccurrence.occurrence_date.in_(sorted(set(wanted.values()))),
        )
    )
    return {o.quest_id: o for o in rows.scalars() if wanted.get(o.quest_id) == o.occurrence_date}


async def _get_owned_quest(session: AsyncSession, user_id: uuid.UUID, quest_id: uuid.UUID, *, lock: bool) -> Quest:
    stmt = select(Quest).where(Quest.id == quest_id, Quest.user_id == user_id, Quest.deleted_at.is_(None))
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    quest = await session.scalar(stmt)
    if quest is None:
        # The same answer for "missing" and "belongs to someone else".
        raise NotFound("Quest not found", code="quest_not_found")
    return quest


async def _quest_view(session: AsyncSession, quest: Quest, tz: str, now: datetime) -> QuestOut:
    occurrences = await _occurrences_for_display(session, [quest], tz, now)
    return quest_out(quest, occurrences.get(quest.id), tz, now)


# --- create / read / update / delete ---------------------------------------------------


async def create_quest(
    session: AsyncSession, user: User, data: QuestCreateIn, now: datetime, game: GameSettings
) -> QuestOut:
    rules = game.rewards
    tz = effective_timezone(user, now)
    if data.activity == Activity.LEARNING:
        minutes = data.target_minutes or 0
        if minutes < rules.learning_block_minutes:
            raise InvalidRequest(
                f"Learning quests need at least {rules.learning_block_minutes} minutes",
                code="target_minutes_too_small",
            )
        if minutes > rules.learning_daily_cap_minutes:
            raise InvalidRequest(
                f"Learning quests can plan at most {rules.learning_daily_cap_minutes} minutes",
                code="target_minutes_too_large",
            )
    starts_at = data.starts_at or now
    if data.due_at is not None and data.due_at <= starts_at:
        raise InvalidRequest("due_at must be after starts_at", code="invalid_due_at")

    if data.attribute_types is not None:
        attributes = list(data.attribute_types)
    else:
        default = CATEGORY_DEFAULT_ATTRIBUTE[data.category]
        attributes = [default] if default else []

    quest = Quest(
        id=new_id(),
        user_id=user.id,
        title=data.title,
        description=data.description,
        quest_type=data.quest_type.value,
        category=data.category.value,
        attribute_types=[a.value for a in attributes],
        activity=data.activity.value,
        difficulty=data.difficulty.value,
        target_minutes=data.target_minutes,
        xp_reward=quest_reward(
            rules,
            quest_type=data.quest_type,
            activity=data.activity,
            difficulty=data.difficulty,
            target_minutes=data.target_minutes,
        ),
        status=QuestStatus.ACTIVE.value,
        is_recurring=(
            data.is_recurring if data.is_recurring is not None else data.quest_type not in ONE_OFF_TYPES
        ),
        weekdays=data.weekdays,
        priority=data.priority,
        checklist=[item.model_dump() for item in data.checklist],
        starts_at=starts_at,
        anchor_date=dates.local_date(tz, starts_at),
        due_at=data.due_at,
    )
    session.add(quest)
    await session.flush()
    await session.refresh(quest)
    return quest_out(quest, None, tz, now)


async def list_quests(
    session: AsyncSession,
    user: User,
    now: datetime,
    *,
    quest_type: QuestType | None,
    status: EffectiveQuestStatus | None,
    today_only: bool,
    limit: int,
    offset: int,
) -> QuestListOut:
    stmt = select(Quest).where(Quest.user_id == user.id, Quest.deleted_at.is_(None))
    if quest_type is not None:
        stmt = stmt.where(Quest.quest_type == quest_type.value)
    stmt = stmt.order_by(Quest.priority.desc(), Quest.created_at.desc())
    quests = list((await session.execute(stmt)).scalars())
    tz = effective_timezone(user, now)
    occurrences = await _occurrences_for_display(session, quests, tz, now)
    views = [quest_out(q, occurrences.get(q.id), tz, now) for q in quests]
    if today_only:
        views = [v for v in views if _relevant_today(v, tz, now)]
    if status is not None:
        views = [v for v in views if v.status == status]
    return QuestListOut(items=views[offset : offset + limit], total=len(views))


def _relevant_today(view: QuestOut, tz: str, now: datetime) -> bool:
    """Today's list: everything actionable now, plus one-off quests finished today."""
    if view.current_occurrence_date is None:
        return False
    if view.is_recurring or view.status == EffectiveQuestStatus.ACTIVE:
        return True
    occurrence = view.current_occurrence
    finished_at = occurrence and (occurrence.completed_at or occurrence.skipped_at)
    return bool(finished_at) and dates.local_date(tz, finished_at) == dates.local_date(tz, now)


async def get_quest_detail(session: AsyncSession, user: User, quest_id: uuid.UUID, now: datetime) -> QuestDetailOut:
    quest = await _get_owned_quest(session, user.id, quest_id, lock=False)
    tz = effective_timezone(user, now)
    history = list(
        (
            await session.execute(
                select(QuestOccurrence)
                .where(QuestOccurrence.quest_id == quest.id)
                .order_by(QuestOccurrence.occurrence_date.desc())
                .limit(60)
            )
        ).scalars()
    )
    shown_date = _display_occurrence_date(quest, tz, now)
    shown = next((o for o in history if o.occurrence_date == shown_date), None)
    view = quest_out(quest, shown, tz, now)
    return QuestDetailOut(**view.model_dump(), occurrences=[OccurrenceOut.model_validate(o) for o in history])


async def update_quest(
    session: AsyncSession, user: User, quest_id: uuid.UUID, data: QuestUpdateIn, now: datetime
) -> QuestOut:
    quest = await _get_owned_quest(session, user.id, quest_id, lock=True)
    fields = data.model_fields_set
    if "title" in fields:
        if data.title is None:
            raise InvalidRequest("title cannot be empty", code="title_required")
        quest.title = data.title
    if "description" in fields:
        quest.description = data.description
    if "priority" in fields:
        if data.priority is None:
            raise InvalidRequest("priority cannot be empty", code="priority_required")
        quest.priority = data.priority
    if "due_at" in fields:
        if data.due_at is not None and data.due_at <= quest.starts_at:
            raise InvalidRequest("due_at must be after starts_at", code="invalid_due_at")
        quest.due_at = data.due_at
    if "weekdays" in fields:
        if not (quest.quest_type == QuestType.DAILY and quest.is_recurring):
            raise InvalidRequest("weekdays apply only to recurring daily quests", code="weekdays_not_applicable")
        quest.weekdays = data.weekdays
    if "checklist" in fields:
        quest.checklist = [item.model_dump() for item in data.checklist or []]
    await session.flush()
    await session.refresh(quest)
    return await _quest_view(session, quest, effective_timezone(user, now), now)


async def delete_quest(session: AsyncSession, user: User, quest_id: uuid.UUID, now: datetime) -> None:
    """Soft delete. Earned XP stays: the ledger is never touched."""
    quest = await _get_owned_quest(session, user.id, quest_id, lock=True)
    quest.deleted_at = now
    if quest.status == QuestStatus.ACTIVE:
        quest.status = QuestStatus.CANCELLED.value
    await session.flush()


# --- complete / skip / undo -----------------------------------------------------------


async def _lock_occurrence(
    session: AsyncSession, user_id: uuid.UUID, quest_id: uuid.UUID, occurrence_date: date
) -> QuestOccurrence:
    await session.execute(
        pg_insert(QuestOccurrence)
        .values(id=new_id(), user_id=user_id, quest_id=quest_id, occurrence_date=occurrence_date)
        .on_conflict_do_nothing(index_elements=["quest_id", "occurrence_date"])
    )
    occurrence = await session.scalar(
        select(QuestOccurrence)
        .where(QuestOccurrence.quest_id == quest_id, QuestOccurrence.occurrence_date == occurrence_date)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert occurrence is not None
    return occurrence


@dataclass(frozen=True)
class _Award:
    xp: int
    minutes_credited: int | None
    limit_reason: XpLimitReason | None


async def _compute_award(
    session: AsyncSession, user_id: uuid.UUID, quest: Quest, tz: str, now: datetime, rules: RewardRules
) -> _Award:
    """XP for this completion after daily limits. Call with the profile locked."""
    day_start, day_end = dates.day_bounds(tz, dates.local_date(tz, now))
    completed_today = (
        QuestOccurrence.user_id == user_id,
        QuestOccurrence.status == OccurrenceStatus.COMPLETED,
        QuestOccurrence.completed_at >= day_start,
        QuestOccurrence.completed_at < day_end,
    )

    if quest.activity == Activity.LEARNING:
        target = quest.target_minutes or 0
        used = await session.scalar(
            select(func.coalesce(func.sum(QuestOccurrence.minutes_credited), 0)).where(*completed_today)
        )
        credited = max(0, min(target, rules.learning_daily_cap_minutes - int(used or 0)))
        xp = scaled_learning_reward(quest.xp_reward, target, credited, rules)
        return _Award(xp, credited, XpLimitReason.LEARNING_DAILY_CAP if credited < target else None)

    is_simple_task = (
        quest.activity == Activity.TASK
        and quest.difficulty == Difficulty.SIMPLE
        and quest.quest_type != QuestType.WEEKLY
    )
    if is_simple_task:
        rewarded_simple = await session.scalar(
            select(func.count())
            .select_from(QuestOccurrence)
            .join(Quest, Quest.id == QuestOccurrence.quest_id)
            .where(
                *completed_today,
                QuestOccurrence.xp_awarded > 0,
                Quest.activity == Activity.TASK,
                Quest.difficulty == Difficulty.SIMPLE,
                Quest.quest_type != QuestType.WEEKLY,
            )
        )
        if (rewarded_simple or 0) >= rules.simple_task_daily_limit:
            return _Award(0, None, XpLimitReason.SIMPLE_TASK_DAILY_LIMIT)

    return _Award(quest.xp_reward, None, None)


async def complete_quest(
    session: AsyncSession, user: User, quest_id: uuid.UUID, now: datetime, game: GameSettings
) -> CompletionOut:
    quest = await _get_owned_quest(session, user.id, quest_id, lock=True)
    tz = effective_timezone(user, now)
    occurrence_date = _actionable_date(quest, tz, now)
    occurrence = await _lock_occurrence(session, user.id, quest.id, occurrence_date)
    if occurrence.status == OccurrenceStatus.COMPLETED:
        raise Conflict("The quest is already completed for this period", code="already_completed")

    profile = await lock_profile(session, user.id)
    award = await _compute_award(session, user.id, quest, tz, now, game.rewards)

    occurrence.status = OccurrenceStatus.COMPLETED.value
    occurrence.completed_at = now
    occurrence.skipped_at = None
    occurrence.xp_awarded = award.xp
    occurrence.minutes_credited = award.minutes_credited
    occurrence.completion_count += 1
    if not quest.is_recurring:
        quest.status = QuestStatus.COMPLETED.value
        quest.completed_at = now

    attributes = [AttributeType(a) for a in quest.attribute_types]
    drafts = [
        LedgerDraft(
            event_key=f"quest:{quest.id}:{occurrence_date.isoformat()}:{occurrence.completion_count}:{attr or '-'}",
            source_type=LedgerSource.QUEST.value,
            source_id=quest.id,
            occurrence_date=occurrence_date,
            attribute_type=attr.value if attr else None,
            xp_amount=amount,
            reason=LedgerReason.QUEST_COMPLETED.value,
            description=quest.title,
        )
        for attr, amount in split_xp(award.xp, attributes)
    ]
    change = await apply_xp(session, profile, drafts, game.level_curve, now)
    await session.flush()
    await session.refresh(quest)
    await session.refresh(occurrence)
    return CompletionOut(
        quest=quest_out(quest, occurrence, tz, now),
        occurrence=OccurrenceOut.model_validate(occurrence),
        xp_awarded=award.xp,
        xp_limit_reason=award.limit_reason,
        player=player_xp_out(change, game.level_curve),
    )


async def skip_quest(session: AsyncSession, user: User, quest_id: uuid.UUID, now: datetime) -> SkipOut:
    """Skipping is recorded but never costs XP."""
    quest = await _get_owned_quest(session, user.id, quest_id, lock=True)
    tz = effective_timezone(user, now)
    occurrence_date = _actionable_date(quest, tz, now)
    occurrence = await _lock_occurrence(session, user.id, quest.id, occurrence_date)
    if occurrence.status == OccurrenceStatus.COMPLETED:
        raise Conflict("Undo the completion before skipping", code="already_completed")
    if occurrence.status == OccurrenceStatus.SKIPPED:
        raise Conflict("The quest is already skipped for this period", code="already_skipped")
    occurrence.status = OccurrenceStatus.SKIPPED.value
    occurrence.skipped_at = now
    if not quest.is_recurring:
        quest.status = QuestStatus.SKIPPED.value
    await session.flush()
    await session.refresh(quest)
    await session.refresh(occurrence)
    return SkipOut(quest=quest_out(quest, occurrence, tz, now), occurrence=OccurrenceOut.model_validate(occurrence))


async def undo_completion(
    session: AsyncSession, user: User, quest_id: uuid.UUID, now: datetime, game: GameSettings
) -> UndoOut:
    """Undo a mistaken completion on the same local day with compensating ledger entries."""
    quest = await _get_owned_quest(session, user.id, quest_id, lock=True)
    tz = effective_timezone(user, now)
    occurrence = await session.scalar(
        select(QuestOccurrence)
        .where(QuestOccurrence.quest_id == quest.id, QuestOccurrence.status == OccurrenceStatus.COMPLETED)
        .order_by(QuestOccurrence.completed_at.desc())
        .limit(1)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if occurrence is None or occurrence.completed_at is None:
        raise Conflict("There is no completion to undo", code="not_completed")
    if dates.local_date(tz, occurrence.completed_at) != dates.local_date(tz, now):
        raise Conflict("A completion can be undone only on the same day", code="undo_window_expired")

    profile = await lock_profile(session, user.id)
    reversal = aliased(XpLedgerEntry)
    entries = (
        await session.execute(
            select(XpLedgerEntry).where(
                XpLedgerEntry.user_id == user.id,
                XpLedgerEntry.source_type == LedgerSource.QUEST.value,
                XpLedgerEntry.source_id == quest.id,
                XpLedgerEntry.occurrence_date == occurrence.occurrence_date,
                XpLedgerEntry.xp_amount > 0,
                ~exists().where(reversal.reverses_id == XpLedgerEntry.id),
            )
        )
    ).scalars()
    drafts = [
        LedgerDraft(
            event_key=f"undo:{entry.id}",
            source_type=LedgerSource.QUEST_UNDO.value,
            source_id=quest.id,
            occurrence_date=entry.occurrence_date,
            attribute_type=entry.attribute_type,
            xp_amount=-entry.xp_amount,
            reason=LedgerReason.QUEST_COMPLETION_UNDONE.value,
            description=quest.title,
            reverses_id=entry.id,
        )
        for entry in entries
    ]
    change = await apply_xp(session, profile, drafts, game.level_curve, now)

    occurrence.status = OccurrenceStatus.PENDING.value
    occurrence.completed_at = None
    occurrence.xp_awarded = 0
    occurrence.minutes_credited = None
    if not quest.is_recurring:
        quest.status = QuestStatus.ACTIVE.value
        quest.completed_at = None
    await session.flush()
    await session.refresh(quest)
    await session.refresh(occurrence)
    return UndoOut(
        quest=quest_out(quest, occurrence, tz, now),
        occurrence=OccurrenceOut.model_validate(occurrence),
        xp_reverted=-change.delta,
        player=player_xp_out(change, game.level_curve),
    )
