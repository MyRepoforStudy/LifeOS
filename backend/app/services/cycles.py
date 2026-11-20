"""Life cycles (spec section 10): a period of any length with goals, pause, a final report and a reward.

- At most one open (active or paused) cycle per player; a unique index guards it.
- Pausing moves the end date forward by the paused days (docs/decisions.md, item 13).
- Goals are manual or counted from the quests and habits linked to them.
- Summing up after the end date gives 200 XP x the share of goals done; finishing
  early is allowed but gives no reward, so short throwaway cycles cannot farm XP.
- The report is stored as a snapshot and never recalculated.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import dates
from app.domain.enums import (
    OPEN_CYCLE_STATUSES,
    Activity,
    AttributeType,
    CycleDisplayStatus,
    CycleStatus,
    GoalMetric,
    HabitLogStatus,
    LedgerReason,
    LedgerSource,
    OccurrenceStatus,
)
from app.domain.levels import LevelCurve, level_for_xp
from app.errors import Conflict, InvalidRequest, NotFound
from app.models import (
    Achievement,
    CycleGoal,
    Habit,
    HabitLog,
    LifeCycle,
    Quest,
    QuestOccurrence,
    User,
    UserAchievement,
    XpLedgerEntry,
    new_id,
)
from app.schemas import (
    CycleCompletionOut,
    CycleCreateIn,
    CycleOut,
    CycleReport,
    CycleSummaryOut,
    CycleUpdateIn,
    GoalCreateIn,
    GoalOut,
    GoalUpdateIn,
    Recommendation,
    ReportAchievement,
    ReportAttribute,
    ReportGoal,
)
from app.services.achievements import unlock_new
from app.services.game_config import GameSettings
from app.services.player import effective_timezone
from app.services.xp import LedgerDraft, XpChange, apply_xp, lock_profile, player_xp_out

MAX_START_AHEAD_DAYS = 30
MAX_GOALS = 10


@dataclass(frozen=True)
class _Period:
    first_day: date
    last_day: date  # inclusive
    start: datetime  # UTC
    end: datetime  # UTC, exclusive


@dataclass(frozen=True)
class _GoalValue:
    current: int
    linked_quests: int
    linked_habits: int


def _today(user: User, now: datetime) -> date:
    return dates.local_date(effective_timezone(user, now), now)


def _reference_day(cycle: LifeCycle, tz: str, today: date) -> date:
    """The day the cycle is looked at: today, or the day it was closed."""
    if cycle.status in (CycleStatus.COMPLETED, CycleStatus.CANCELLED) and cycle.completed_at:
        return dates.local_date(tz, cycle.completed_at)
    return today


def _period(cycle: LifeCycle, tz: str, day: date) -> _Period | None:
    last = min(day, cycle.ends_on)
    if last < cycle.starts_on:
        return None
    return _Period(
        first_day=cycle.starts_on,
        last_day=last,
        start=dates.day_bounds(tz, cycle.starts_on)[0],
        end=dates.day_bounds(tz, last)[1],
    )


def _current_pause(cycle: LifeCycle, day: date) -> int:
    if cycle.status == CycleStatus.PAUSED and cycle.paused_on:
        return max(0, (day - cycle.paused_on).days)
    return 0


def _day_number(cycle: LifeCycle, day: date) -> int:
    last = min(day, cycle.ends_on)
    if last < cycle.starts_on:
        return 0
    lived = (last - cycle.starts_on).days + 1 - cycle.paused_days - _current_pause(cycle, day)
    return max(0, min(cycle.duration_days, lived))


def _display_status(cycle: LifeCycle, today: date) -> CycleDisplayStatus:
    if cycle.status == CycleStatus.COMPLETED:
        return CycleDisplayStatus.COMPLETED
    if cycle.status == CycleStatus.CANCELLED:
        return CycleDisplayStatus.CANCELLED
    if cycle.status == CycleStatus.PAUSED:
        return CycleDisplayStatus.PAUSED
    if today < cycle.starts_on:
        return CycleDisplayStatus.PLANNED
    if today > cycle.ends_on:
        return CycleDisplayStatus.FINISHED
    return CycleDisplayStatus.ACTIVE


async def _goals(session: AsyncSession, cycle_id: uuid.UUID) -> list[CycleGoal]:
    return list(
        (
            await session.scalars(
                select(CycleGoal).where(CycleGoal.cycle_id == cycle_id).order_by(CycleGoal.sort_order, CycleGoal.created_at)
            )
        ).all()
    )


async def _goal_values(
    session: AsyncSession, goals: list[CycleGoal], period: _Period | None
) -> dict[uuid.UUID, _GoalValue]:
    ids = [g.id for g in goals]
    if not ids:
        return {}
    linked_quests = dict(
        (
            await session.execute(
                select(Quest.goal_id, func.count())
                .where(Quest.goal_id.in_(ids), Quest.deleted_at.is_(None))
                .group_by(Quest.goal_id)
            )
        ).all()
    )
    linked_habits = dict(
        (await session.execute(select(Habit.goal_id, func.count()).where(Habit.goal_id.in_(ids)).group_by(Habit.goal_id))).all()
    )
    quest_counts: dict[uuid.UUID, int] = {}
    quest_minutes: dict[uuid.UUID, int] = {}
    habit_counts: dict[uuid.UUID, int] = {}
    if period is not None:
        rows = await session.execute(
            select(Quest.goal_id, func.count(), func.coalesce(func.sum(QuestOccurrence.minutes_credited), 0))
            .select_from(QuestOccurrence)
            .join(Quest, Quest.id == QuestOccurrence.quest_id)
            .where(
                Quest.goal_id.in_(ids),
                QuestOccurrence.status == OccurrenceStatus.COMPLETED,
                QuestOccurrence.completed_at >= period.start,
                QuestOccurrence.completed_at < period.end,
            )
            .group_by(Quest.goal_id)
        )
        for goal_id, count, minutes in rows:
            quest_counts[goal_id] = int(count)
            quest_minutes[goal_id] = int(minutes)
        habit_counts = {
            goal_id: int(count)
            for goal_id, count in await session.execute(
                select(Habit.goal_id, func.count())
                .select_from(HabitLog)
                .join(Habit, Habit.id == HabitLog.habit_id)
                .where(
                    Habit.goal_id.in_(ids),
                    HabitLog.status == HabitLogStatus.DONE,
                    HabitLog.completed_on >= period.first_day,
                    HabitLog.completed_on <= period.last_day,
                )
                .group_by(Habit.goal_id)
            )
        }
    values = {}
    for goal in goals:
        if goal.metric == GoalMetric.COMPLETIONS:
            current = quest_counts.get(goal.id, 0) + habit_counts.get(goal.id, 0)
        elif goal.metric == GoalMetric.MINUTES:
            current = quest_minutes.get(goal.id, 0)
        else:
            current = goal.current_value
        values[goal.id] = _GoalValue(current, int(linked_quests.get(goal.id, 0)), int(linked_habits.get(goal.id, 0)))
    return values


def _goal_out(goal: CycleGoal, value: _GoalValue) -> GoalOut:
    return GoalOut(
        id=goal.id,
        title=goal.title,
        category=goal.category,
        metric=GoalMetric(goal.metric),
        target_value=goal.target_value,
        current_value=value.current,
        unit=goal.unit,
        progress=round(min(1.0, value.current / goal.target_value), 4),
        done=value.current >= goal.target_value,
        linked_quests=value.linked_quests,
        linked_habits=value.linked_habits,
    )


async def _xp_in_period(session: AsyncSession, user_id: uuid.UUID, period: _Period | None) -> int:
    if period is None:
        return 0
    value = await session.scalar(
        select(func.coalesce(func.sum(XpLedgerEntry.xp_amount), 0)).where(
            XpLedgerEntry.user_id == user_id,
            XpLedgerEntry.source_type != LedgerSource.CYCLE.value,
            XpLedgerEntry.created_at >= period.start,
            XpLedgerEntry.created_at < period.end,
        )
    )
    return int(value or 0)


async def cycle_view(session: AsyncSession, user: User, cycle: LifeCycle, now: datetime) -> CycleOut:
    tz = effective_timezone(user, now)
    today = _today(user, now)
    day = _reference_day(cycle, tz, today)
    goals = await _goals(session, cycle.id)
    report = CycleReport.model_validate(cycle.report) if cycle.report else None
    if report is not None:
        # A completed cycle shows its snapshot, not today's numbers.
        goal_views = [
            GoalOut(
                id=goal.id,
                title=item.title,
                category=goal.category,
                metric=item.metric,
                target_value=item.target_value,
                current_value=item.current_value,
                unit=item.unit,
                progress=round(min(1.0, item.current_value / item.target_value), 4),
                done=item.done,
                linked_quests=0,
                linked_habits=0,
            )
            for goal, item in zip(goals, report.goals, strict=False)
        ]
        xp_in_cycle = report.xp_total
    else:
        period = _period(cycle, tz, day)
        values = await _goal_values(session, goals, period)
        goal_views = [_goal_out(goal, values[goal.id]) for goal in goals]
        xp_in_cycle = await _xp_in_period(session, user.id, period)
    day_number = _day_number(cycle, day)
    open_cycle = cycle.status in OPEN_CYCLE_STATUSES
    return CycleOut(
        id=cycle.id,
        title=cycle.title,
        description=cycle.description,
        duration_days=cycle.duration_days,
        starts_on=cycle.starts_on,
        ends_on=cycle.ends_on + timedelta(days=_current_pause(cycle, today)),
        status=_display_status(cycle, today),
        day_number=day_number,
        days_left=max(0, cycle.duration_days - day_number) if open_cycle else 0,
        time_progress=round(day_number / cycle.duration_days, 4),
        paused_on=cycle.paused_on,
        paused_days=cycle.paused_days,
        goals=goal_views,
        goals_done=sum(1 for g in goal_views if g.done),
        goals_total=len(goal_views),
        xp_in_cycle=xp_in_cycle,
        reached_end=open_cycle and cycle.status == CycleStatus.ACTIVE and today >= cycle.ends_on,
        finished_early=cycle.finished_early,
        completed_at=cycle.completed_at,
        xp_awarded=cycle.xp_awarded,
        report=report,
    )


# --- lookups --------------------------------------------------------------------------


async def _get_cycle(session: AsyncSession, user_id: uuid.UUID, cycle_id: uuid.UUID, *, lock: bool) -> LifeCycle:
    stmt = select(LifeCycle).where(LifeCycle.id == cycle_id, LifeCycle.user_id == user_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    cycle = await session.scalar(stmt)
    if cycle is None:
        raise NotFound("Cycle not found", code="cycle_not_found")
    return cycle


async def _get_open_cycle(session: AsyncSession, user_id: uuid.UUID, cycle_id: uuid.UUID) -> LifeCycle:
    cycle = await _get_cycle(session, user_id, cycle_id, lock=True)
    if cycle.status not in OPEN_CYCLE_STATUSES:
        raise Conflict("The cycle is already closed", code="cycle_closed")
    return cycle


async def resolve_goal(session: AsyncSession, user_id: uuid.UUID, goal_id: uuid.UUID) -> CycleGoal:
    """A goal a quest or habit may be linked to: the player's, in an open cycle."""
    row = (
        await session.execute(
            select(CycleGoal, LifeCycle.status)
            .join(LifeCycle, LifeCycle.id == CycleGoal.cycle_id)
            .where(CycleGoal.id == goal_id, CycleGoal.user_id == user_id)
        )
    ).first()
    if row is None:
        raise NotFound("Goal not found", code="goal_not_found")
    goal, status = row
    if status not in OPEN_CYCLE_STATUSES:
        raise Conflict("The goal belongs to a closed cycle", code="cycle_closed")
    return goal


# --- create / read / update -----------------------------------------------------------


async def create_cycle(session: AsyncSession, user: User, data: CycleCreateIn, now: datetime) -> CycleOut:
    today = _today(user, now)
    starts_on = data.starts_on or today
    if starts_on < today or starts_on > today + timedelta(days=MAX_START_AHEAD_DAYS):
        raise InvalidRequest(
            f"The cycle must start between today and {MAX_START_AHEAD_DAYS} days ahead", code="invalid_start_date"
        )
    open_cycle = await session.scalar(
        select(LifeCycle.id).where(LifeCycle.user_id == user.id, LifeCycle.status.in_(list(OPEN_CYCLE_STATUSES)))
    )
    if open_cycle:
        raise Conflict("Finish or cancel the current cycle first", code="cycle_already_open")
    cycle = LifeCycle(
        id=new_id(),
        user_id=user.id,
        title=data.title,
        description=data.description,
        duration_days=data.duration_days,
        starts_on=starts_on,
        ends_on=starts_on + timedelta(days=data.duration_days - 1),
        status=CycleStatus.ACTIVE.value,
    )
    session.add(cycle)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise Conflict("Finish or cancel the current cycle first", code="cycle_already_open") from exc
    session.add_all(_new_goal(user.id, cycle.id, goal, index) for index, goal in enumerate(data.goals))
    await session.flush()
    await session.refresh(cycle)
    return await cycle_view(session, user, cycle, now)


def _new_goal(user_id: uuid.UUID, cycle_id: uuid.UUID, data: GoalCreateIn, index: int) -> CycleGoal:
    return CycleGoal(
        id=new_id(),
        user_id=user_id,
        cycle_id=cycle_id,
        title=data.title,
        category=data.category.value,
        metric=data.metric.value,
        target_value=data.target_value,
        current_value=0,
        unit=data.unit or None,
        sort_order=index,
    )


async def list_cycles(session: AsyncSession, user: User, now: datetime) -> list[CycleSummaryOut]:
    cycles = (
        await session.scalars(
            select(LifeCycle).where(LifeCycle.user_id == user.id).order_by(LifeCycle.starts_on.desc(), LifeCycle.created_at.desc())
        )
    ).all()
    result = []
    for cycle in cycles:
        view = await cycle_view(session, user, cycle, now)
        result.append(
            CycleSummaryOut(
                id=view.id,
                title=view.title,
                status=view.status,
                starts_on=view.starts_on,
                ends_on=view.ends_on,
                duration_days=view.duration_days,
                goals_done=view.goals_done,
                goals_total=view.goals_total,
                xp_awarded=view.xp_awarded,
            )
        )
    return result


async def get_cycle(session: AsyncSession, user: User, cycle_id: uuid.UUID, now: datetime) -> CycleOut:
    return await cycle_view(session, user, await _get_cycle(session, user.id, cycle_id, lock=False), now)


async def get_current_cycle(session: AsyncSession, user: User, now: datetime) -> CycleOut | None:
    cycle = await session.scalar(
        select(LifeCycle).where(LifeCycle.user_id == user.id, LifeCycle.status.in_(list(OPEN_CYCLE_STATUSES)))
    )
    return await cycle_view(session, user, cycle, now) if cycle else None


async def update_cycle(
    session: AsyncSession, user: User, cycle_id: uuid.UUID, data: CycleUpdateIn, now: datetime
) -> CycleOut:
    cycle = await _get_open_cycle(session, user.id, cycle_id)
    if "title" in data.model_fields_set and data.title:
        cycle.title = data.title
    if "description" in data.model_fields_set:
        cycle.description = data.description
    await session.flush()
    return await cycle_view(session, user, cycle, now)


async def add_goal(
    session: AsyncSession, user: User, cycle_id: uuid.UUID, data: GoalCreateIn, now: datetime
) -> CycleOut:
    cycle = await _get_open_cycle(session, user.id, cycle_id)
    goals = await _goals(session, cycle.id)
    if len(goals) >= MAX_GOALS:
        raise Conflict(f"A cycle can have at most {MAX_GOALS} goals", code="too_many_goals")
    session.add(_new_goal(user.id, cycle.id, data, len(goals)))
    await session.flush()
    return await cycle_view(session, user, cycle, now)


async def _get_goal(session: AsyncSession, cycle: LifeCycle, goal_id: uuid.UUID) -> CycleGoal:
    goal = await session.scalar(
        select(CycleGoal).where(CycleGoal.id == goal_id, CycleGoal.cycle_id == cycle.id).with_for_update()
    )
    if goal is None:
        raise NotFound("Goal not found", code="goal_not_found")
    return goal


async def update_goal(
    session: AsyncSession, user: User, cycle_id: uuid.UUID, goal_id: uuid.UUID, data: GoalUpdateIn, now: datetime
) -> CycleOut:
    cycle = await _get_open_cycle(session, user.id, cycle_id)
    goal = await _get_goal(session, cycle, goal_id)
    fields = data.model_fields_set
    if "title" in fields and data.title:
        goal.title = data.title
    if "target_value" in fields and data.target_value is not None:
        goal.target_value = data.target_value
    if "unit" in fields:
        goal.unit = data.unit or None
    if "current_value" in fields and data.current_value is not None:
        if goal.metric != GoalMetric.MANUAL:
            raise InvalidRequest("This goal is counted from linked quests and habits", code="goal_not_manual")
        goal.current_value = data.current_value
    await session.flush()
    return await cycle_view(session, user, cycle, now)


async def delete_goal(
    session: AsyncSession, user: User, cycle_id: uuid.UUID, goal_id: uuid.UUID, now: datetime
) -> CycleOut:
    """Linked quests and habits stay; they just lose the link."""
    cycle = await _get_open_cycle(session, user.id, cycle_id)
    goal = await _get_goal(session, cycle, goal_id)
    await session.delete(goal)
    await session.flush()
    return await cycle_view(session, user, cycle, now)


# --- pause / resume / complete / cancel -----------------------------------------------


def _resume(cycle: LifeCycle, today: date) -> None:
    days = _current_pause(cycle, today)
    cycle.paused_days += days
    cycle.ends_on = cycle.ends_on + timedelta(days=days)
    cycle.paused_on = None
    cycle.status = CycleStatus.ACTIVE.value


async def pause_cycle(session: AsyncSession, user: User, cycle_id: uuid.UUID, now: datetime) -> CycleOut:
    cycle = await _get_open_cycle(session, user.id, cycle_id)
    today = _today(user, now)
    if cycle.status != CycleStatus.ACTIVE or today < cycle.starts_on or today > cycle.ends_on:
        raise Conflict("Only a running cycle can be paused", code="cycle_not_running")
    cycle.status = CycleStatus.PAUSED.value
    cycle.paused_on = today
    await session.flush()
    return await cycle_view(session, user, cycle, now)


async def resume_cycle(session: AsyncSession, user: User, cycle_id: uuid.UUID, now: datetime) -> CycleOut:
    cycle = await _get_open_cycle(session, user.id, cycle_id)
    if cycle.status != CycleStatus.PAUSED:
        raise Conflict("The cycle is not paused", code="cycle_not_paused")
    _resume(cycle, _today(user, now))
    await session.flush()
    return await cycle_view(session, user, cycle, now)


async def cancel_cycle(session: AsyncSession, user: User, cycle_id: uuid.UUID, now: datetime) -> None:
    """Cancelled cycles stay in the history without a report or reward."""
    cycle = await _get_open_cycle(session, user.id, cycle_id)
    cycle.status = CycleStatus.CANCELLED.value
    cycle.completed_at = now
    await session.flush()


async def complete_cycle(
    session: AsyncSession, user: User, cycle_id: uuid.UUID, now: datetime, game: GameSettings
) -> CycleCompletionOut:
    cycle = await _get_open_cycle(session, user.id, cycle_id)
    today = _today(user, now)
    if cycle.status == CycleStatus.PAUSED:
        _resume(cycle, today)
    if today < cycle.starts_on:
        raise Conflict("The cycle has not started yet; cancel it instead", code="cycle_not_started")
    profile = await lock_profile(session, user.id)

    reached_end = today >= cycle.ends_on
    report = await _build_report(session, user, cycle, now, game.level_curve)
    xp = 0
    if reached_end and report.goals_total > 0:
        xp = int(game.rewards.cycle_completion * report.goals_done / report.goals_total + 0.5)
    report = report.model_copy(update={"finished_early": not reached_end, "cycle_xp": xp})

    cycle.status = CycleStatus.COMPLETED.value
    cycle.completed_at = now
    cycle.finished_early = not reached_end
    cycle.xp_awarded = xp
    cycle.report = report.model_dump(mode="json")
    await session.flush()

    drafts = []
    if xp > 0:
        drafts.append(
            LedgerDraft(
                event_key=f"cycle:{cycle.id}",
                source_type=LedgerSource.CYCLE.value,
                source_id=cycle.id,
                occurrence_date=cycle.ends_on,
                attribute_type=None,
                xp_amount=xp,
                reason=LedgerReason.CYCLE_COMPLETED.value,
                description=cycle.title,
            )
        )
    first = await apply_xp(session, profile, drafts, game.level_curve, now)
    unlocked = await unlock_new(session, user, profile, now, game)
    change = XpChange(first.total_before, profile.total_xp, first.level_before, profile.current_level)
    await session.flush()
    return CycleCompletionOut(
        cycle=await cycle_view(session, user, cycle, now),
        xp_awarded=xp,
        player=player_xp_out(change, game.level_curve),
        achievements_unlocked=unlocked,
    )


# --- report ---------------------------------------------------------------------------


async def _build_report(
    session: AsyncSession, user: User, cycle: LifeCycle, now: datetime, curve: LevelCurve
) -> CycleReport:
    tz = effective_timezone(user, now)
    today = _today(user, now)
    period = _period(cycle, tz, today)
    goals = await _goals(session, cycle.id)
    values = await _goal_values(session, goals, period)
    report_goals = [
        ReportGoal(
            title=goal.title,
            metric=GoalMetric(goal.metric),
            target_value=goal.target_value,
            current_value=values[goal.id].current,
            unit=goal.unit,
            done=values[goal.id].current >= goal.target_value,
        )
        for goal in goals
    ]
    goals_done = sum(1 for g in report_goals if g.done)

    xp_total = await _xp_in_period(session, user.id, period)
    before: dict[str, int] = {}
    gained: dict[str, int] = {}
    learning_minutes = workouts = quests_completed = habit_checkins = active_days = 0
    achievements: list[ReportAchievement] = []
    if period is not None:
        before = {
            attr: int(xp)
            for attr, xp in await session.execute(
                select(XpLedgerEntry.attribute_type, func.sum(XpLedgerEntry.xp_amount))
                .where(
                    XpLedgerEntry.user_id == user.id,
                    XpLedgerEntry.attribute_type.is_not(None),
                    XpLedgerEntry.created_at < period.start,
                )
                .group_by(XpLedgerEntry.attribute_type)
            )
        }
        gained = {
            attr: int(xp)
            for attr, xp in await session.execute(
                select(XpLedgerEntry.attribute_type, func.sum(XpLedgerEntry.xp_amount))
                .where(
                    XpLedgerEntry.user_id == user.id,
                    XpLedgerEntry.attribute_type.is_not(None),
                    XpLedgerEntry.created_at >= period.start,
                    XpLedgerEntry.created_at < period.end,
                )
                .group_by(XpLedgerEntry.attribute_type)
            )
        }
        completed_in_period = (
            QuestOccurrence.user_id == user.id,
            QuestOccurrence.status == OccurrenceStatus.COMPLETED,
            QuestOccurrence.completed_at >= period.start,
            QuestOccurrence.completed_at < period.end,
        )
        quests_completed, learning_minutes = (
            await session.execute(
                select(func.count(), func.coalesce(func.sum(QuestOccurrence.minutes_credited), 0)).where(
                    *completed_in_period
                )
            )
        ).one()
        workouts = await session.scalar(
            select(func.count())
            .select_from(QuestOccurrence)
            .join(Quest, Quest.id == QuestOccurrence.quest_id)
            .where(*completed_in_period, Quest.activity == Activity.WORKOUT)
        )
        habit_checkins = await session.scalar(
            select(func.count()).where(
                HabitLog.user_id == user.id,
                HabitLog.status == HabitLogStatus.DONE,
                HabitLog.completed_on >= period.first_day,
                HabitLog.completed_on <= period.last_day,
            )
        )
        active_days = await session.scalar(
            text(
                """
                SELECT count(*) FROM (
                    SELECT (completed_at AT TIME ZONE :tz)::date AS day
                    FROM quest_occurrences
                    WHERE user_id = :user_id AND status = 'completed'
                      AND completed_at >= :start AND completed_at < :end
                    UNION
                    SELECT completed_on FROM habit_logs
                    WHERE user_id = :user_id AND status = 'done'
                      AND completed_on BETWEEN :first_day AND :last_day
                ) AS days
                """
            ),
            {
                "tz": tz,
                "user_id": user.id,
                "start": period.start,
                "end": period.end,
                "first_day": period.first_day,
                "last_day": period.last_day,
            },
        )
        achievements = [
            ReportAchievement(code=code, title=title, rarity=rarity)
            for code, title, rarity in await session.execute(
                select(Achievement.code, Achievement.title, Achievement.rarity)
                .join(UserAchievement, UserAchievement.achievement_id == Achievement.id)
                .where(
                    UserAchievement.user_id == user.id,
                    UserAchievement.unlocked_at >= period.start,
                    UserAchievement.unlocked_at < period.end,
                )
                .order_by(UserAchievement.unlocked_at)
            )
        ]

    attributes = [
        ReportAttribute(
            attribute_type=attr,
            xp_gained=gained.get(attr.value, 0),
            level_before=level_for_xp(max(0, before.get(attr.value, 0)), curve),
            level_after=level_for_xp(max(0, before.get(attr.value, 0) + gained.get(attr.value, 0)), curve),
        )
        for attr in AttributeType
    ]
    lived_days = _day_number(cycle, today) or 1
    return CycleReport(
        starts_on=cycle.starts_on,
        ends_on=cycle.ends_on,
        duration_days=cycle.duration_days,
        paused_days=cycle.paused_days,
        finished_early=today < cycle.ends_on,
        goals=report_goals,
        goals_done=goals_done,
        goals_total=len(report_goals),
        xp_total=xp_total,
        attributes=attributes,
        learning_minutes=int(learning_minutes or 0),
        workouts=int(workouts or 0),
        quests_completed=int(quests_completed or 0),
        habit_checkins=int(habit_checkins or 0),
        active_days=int(active_days or 0),
        achievements=achievements,
        cycle_xp=0,
        recommendations=_recommend(goals, values, report_goals, int(active_days or 0), lived_days, cycle),
    )


def _recommend(
    goals: list[CycleGoal],
    values: dict[uuid.UUID, _GoalValue],
    report_goals: list[ReportGoal],
    active_days: int,
    lived_days: int,
    cycle: LifeCycle,
) -> list[Recommendation]:
    """Rule-based hints for the next cycle (AI comes later, docs/decisions.md item 14)."""
    hints: list[Recommendation] = []
    total = len(report_goals)
    done = sum(1 for g in report_goals if g.done)
    if total == 0:
        hints.append(Recommendation(code="add_goals"))
    elif done == total:
        hints.append(Recommendation(code="raise_bar"))
    elif done / total < 0.5:
        hints.append(Recommendation(code="fewer_goals", params={"done": done, "total": total}))
    stalled = [g for g in goals if values[g.id].current == 0][:2]
    hints.extend(Recommendation(code="stalled_goal", params={"title": g.title}) for g in stalled)
    unlinked = [
        g
        for g in goals
        if g.metric != GoalMetric.MANUAL
        and values[g.id].linked_quests + values[g.id].linked_habits == 0
        and g not in stalled
    ][:2]
    hints.extend(Recommendation(code="link_goal", params={"title": g.title}) for g in unlinked)
    if lived_days >= 7 and active_days / lived_days < 0.5:
        hints.append(Recommendation(code="smaller_daily_plan", params={"active_days": active_days, "days": lived_days}))
    if cycle.paused_days > cycle.duration_days // 4:
        hints.append(Recommendation(code="shorter_cycle", params={"paused_days": cycle.paused_days}))
    return hints[:5]
