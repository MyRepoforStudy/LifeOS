"""Habits: daily completion with XP, same-day undo, streaks and streak freezes.

Lock order (same as quests): habit row -> habit log row -> player profile.
"""

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domain import dates
from app.domain.enums import (
    CATEGORY_DEFAULT_ATTRIBUTE,
    AttributeType,
    HabitFrequency,
    HabitLogStatus,
    LedgerReason,
    LedgerSource,
    XpLimitReason,
)
from app.domain.rewards import RewardRules, split_xp
from app.domain.streaks import Schedule, compute_streak, done_this_week
from app.errors import Conflict, NotFound
from app.models import Habit, HabitLog, User, XpLedgerEntry, new_id
from app.schemas import (
    HabitCompletionOut,
    HabitCreateIn,
    HabitDayOut,
    HabitDetailOut,
    HabitOut,
    HabitUndoOut,
    HabitUpdateIn,
    StreakOut,
)
from app.services.achievements import unlock_new
from app.services.cycles import resolve_goal
from app.services.game_config import GameSettings
from app.services.player import effective_timezone
from app.services.xp import LedgerDraft, XpChange, apply_xp, lock_profile, player_xp_out

HISTORY_DAYS = 35
HISTORY_WEEKS = 10


def schedule_of(habit: Habit) -> Schedule:
    return Schedule(
        frequency=HabitFrequency(habit.frequency),
        starts_on=habit.starts_on,
        weekdays=frozenset(habit.weekdays or ()),
        times_per_week=habit.times_per_week or 1,
    )


def _month_bounds(day: date) -> tuple[date, date]:
    start = day.replace(day=1)
    end = (start + timedelta(days=32)).replace(day=1)
    return start, end


class _Logs:
    """Done and frozen days of one habit."""

    def __init__(self) -> None:
        self.done: set[date] = set()
        self.frozen: set[date] = set()

    def freezes_in_month(self, day: date) -> int:
        start, end = _month_bounds(day)
        return sum(1 for frozen_day in self.frozen if start <= frozen_day < end)


async def _load_logs(session: AsyncSession, habit_ids: list[uuid.UUID]) -> dict[uuid.UUID, _Logs]:
    logs = {habit_id: _Logs() for habit_id in habit_ids}
    if not habit_ids:
        return logs
    rows = await session.execute(
        select(HabitLog.habit_id, HabitLog.completed_on, HabitLog.status).where(
            HabitLog.habit_id.in_(habit_ids),
            HabitLog.status.in_([HabitLogStatus.DONE, HabitLogStatus.FROZEN]),
        )
    )
    for habit_id, day, status in rows:
        bucket = logs[habit_id].done if status == HabitLogStatus.DONE else logs[habit_id].frozen
        bucket.add(day)
    return logs


def habit_out(habit: Habit, logs: _Logs, today: date, rules: RewardRules) -> HabitOut:
    schedule = schedule_of(habit)
    streak = compute_streak(schedule, logs.done, logs.frozen, today)
    weekly = schedule.unit == "week"
    freezes_left = max(0, rules.streak_freezes_per_month - logs.freezes_in_month(today))
    return HabitOut(
        id=habit.id,
        title=habit.title,
        description=habit.description,
        category=habit.category,
        attribute_types=[AttributeType(a) for a in habit.attribute_types],
        frequency=HabitFrequency(habit.frequency),
        weekdays=habit.weekdays,
        times_per_week=habit.times_per_week,
        xp_reward=habit.xp_reward,
        is_active=habit.is_active,
        goal_id=habit.goal_id,
        starts_on=habit.starts_on,
        created_at=habit.created_at,
        required_today=weekly or schedule.is_required(today),
        done_today=today in logs.done,
        week_done=done_this_week(logs.done, today) if weekly else None,
        streak=StreakOut(
            unit=streak.unit, current=streak.current, best=streak.best, last_completed_on=streak.last_completed_on
        ),
        freezes_left=freezes_left if habit.is_active else 0,
        freezable=streak.freezable if habit.is_active and freezes_left > 0 else [],
    )


def _history(habit: Habit, logs: _Logs, today: date) -> list[HabitDayOut]:
    schedule = schedule_of(habit)
    days: list[HabitDayOut] = []
    if schedule.unit == "week":
        current = dates.week_start(today)
        for i in range(HISTORY_WEEKS - 1, -1, -1):
            week = current - timedelta(days=7 * i)
            count = sum(1 for d in logs.done if week <= d <= week + timedelta(days=6))
            if week + timedelta(days=6) < schedule.starts_on:
                status = "before_start"
            elif count >= schedule.times_per_week:
                status = "done"
            elif week in logs.frozen:
                status = "frozen"
            elif week == current or week == dates.week_start(schedule.starts_on):
                status = "open"
            else:
                status = "missed"
            days.append(HabitDayOut(date=week, status=status))
        return days
    for i in range(HISTORY_DAYS - 1, -1, -1):
        day = today - timedelta(days=i)
        if day < schedule.starts_on:
            status = "before_start"
        elif day in logs.done:
            status = "done"
        elif day in logs.frozen:
            status = "frozen"
        elif not schedule.is_required(day):
            status = "rest"
        elif day == today:
            status = "open"
        else:
            status = "missed"
        days.append(HabitDayOut(date=day, status=status))
    return days


async def _get_owned_habit(session: AsyncSession, user_id: uuid.UUID, habit_id: uuid.UUID, *, lock: bool) -> Habit:
    stmt = select(Habit).where(Habit.id == habit_id, Habit.user_id == user_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    habit = await session.scalar(stmt)
    if habit is None:
        raise NotFound("Habit not found", code="habit_not_found")
    return habit


def _today(user: User, now: datetime) -> date:
    return dates.local_date(effective_timezone(user, now), now)


async def _view(session: AsyncSession, habit: Habit, user: User, now: datetime, rules: RewardRules) -> HabitOut:
    logs = (await _load_logs(session, [habit.id]))[habit.id]
    return habit_out(habit, logs, _today(user, now), rules)


# --- create / read / update -----------------------------------------------------------


async def create_habit(
    session: AsyncSession, user: User, data: HabitCreateIn, now: datetime, game: GameSettings
) -> HabitOut:
    if data.attribute_types is not None:
        attributes = list(data.attribute_types)
    else:
        default = CATEGORY_DEFAULT_ATTRIBUTE[data.category]
        attributes = [default] if default else []
    goal_id = (await resolve_goal(session, user.id, data.goal_id)).id if data.goal_id else None
    habit = Habit(
        id=new_id(),
        user_id=user.id,
        title=data.title,
        description=data.description,
        category=data.category.value,
        attribute_types=[a.value for a in attributes],
        frequency=data.frequency.value,
        weekdays=data.weekdays,
        times_per_week=data.times_per_week,
        xp_reward=game.rewards.habit,
        goal_id=goal_id,
        starts_on=_today(user, now),
        is_active=True,
    )
    session.add(habit)
    await session.flush()
    await session.refresh(habit)
    return habit_out(habit, _Logs(), habit.starts_on, game.rewards)


async def list_habits(
    session: AsyncSession, user: User, now: datetime, game: GameSettings, *, include_archived: bool
) -> list[HabitOut]:
    stmt = select(Habit).where(Habit.user_id == user.id)
    if not include_archived:
        stmt = stmt.where(Habit.is_active.is_(True))
    habits = list((await session.scalars(stmt.order_by(Habit.created_at))).all())
    logs = await _load_logs(session, [h.id for h in habits])
    today = _today(user, now)
    return [habit_out(h, logs[h.id], today, game.rewards) for h in habits]


async def get_habit_detail(
    session: AsyncSession, user: User, habit_id: uuid.UUID, now: datetime, game: GameSettings
) -> HabitDetailOut:
    habit = await _get_owned_habit(session, user.id, habit_id, lock=False)
    logs = (await _load_logs(session, [habit.id]))[habit.id]
    today = _today(user, now)
    view = habit_out(habit, logs, today, game.rewards)
    return HabitDetailOut(**view.model_dump(), history=_history(habit, logs, today))


async def update_habit(
    session: AsyncSession, user: User, habit_id: uuid.UUID, data: HabitUpdateIn, now: datetime, game: GameSettings
) -> HabitOut:
    habit = await _get_owned_habit(session, user.id, habit_id, lock=True)
    fields = data.model_fields_set
    if "title" in fields and data.title is not None:
        habit.title = data.title
    if "description" in fields:
        habit.description = data.description
    if "goal_id" in fields:
        habit.goal_id = (await resolve_goal(session, user.id, data.goal_id)).id if data.goal_id else None
    await session.flush()
    await session.refresh(habit)
    return await _view(session, habit, user, now, game.rewards)


async def archive_habit(session: AsyncSession, user: User, habit_id: uuid.UUID, now: datetime) -> None:
    """Archive instead of delete: the XP and the streak history stay."""
    habit = await _get_owned_habit(session, user.id, habit_id, lock=True)
    habit.is_active = False
    habit.archived_at = now
    await session.flush()


# --- complete / undo / freeze ---------------------------------------------------------


async def _lock_log(session: AsyncSession, user_id: uuid.UUID, habit_id: uuid.UUID, day: date) -> HabitLog:
    await session.execute(
        pg_insert(HabitLog)
        .values(id=new_id(), user_id=user_id, habit_id=habit_id, completed_on=day, status=HabitLogStatus.UNDONE.value)
        .on_conflict_do_nothing(index_elements=["habit_id", "completed_on"])
    )
    log = await session.scalar(
        select(HabitLog)
        .where(HabitLog.habit_id == habit_id, HabitLog.completed_on == day)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert log is not None
    return log


def _require_active(habit: Habit) -> None:
    if not habit.is_active:
        raise Conflict("The habit is archived", code="habit_archived")


async def complete_habit(
    session: AsyncSession, user: User, habit_id: uuid.UUID, now: datetime, game: GameSettings
) -> HabitCompletionOut:
    habit = await _get_owned_habit(session, user.id, habit_id, lock=True)
    _require_active(habit)
    today = _today(user, now)
    schedule = schedule_of(habit)
    if schedule.unit == "day" and not schedule.is_required(today):
        raise Conflict("The habit is not planned for today", code="not_scheduled_today")

    log = await _lock_log(session, user.id, habit.id, today)
    if log.status == HabitLogStatus.DONE:
        raise Conflict("The habit is already done today", code="already_completed")

    profile = await lock_profile(session, user.id)
    rewarded_today = await session.scalar(
        select(func.count()).where(
            HabitLog.user_id == user.id,
            HabitLog.completed_on == today,
            HabitLog.status == HabitLogStatus.DONE,
            HabitLog.xp_awarded > 0,
        )
    )
    limited = (rewarded_today or 0) >= game.rewards.habit_daily_limit
    xp = 0 if limited else habit.xp_reward

    log.status = HabitLogStatus.DONE.value
    log.completed_at = now
    log.xp_awarded = xp
    log.completion_count += 1

    drafts = [
        LedgerDraft(
            event_key=f"habit:{habit.id}:{today.isoformat()}:{log.completion_count}:{attr or '-'}",
            source_type=LedgerSource.HABIT.value,
            source_id=habit.id,
            occurrence_date=today,
            attribute_type=attr.value if attr else None,
            xp_amount=amount,
            reason=LedgerReason.HABIT_COMPLETED.value,
            description=habit.title,
        )
        for attr, amount in split_xp(xp, [AttributeType(a) for a in habit.attribute_types])
    ]
    first = await apply_xp(session, profile, drafts, game.level_curve, now)
    unlocked = await unlock_new(session, user, profile, now, game)
    change = XpChange(first.total_before, profile.total_xp, first.level_before, profile.current_level)
    await session.flush()
    return HabitCompletionOut(
        habit=await _view(session, habit, user, now, game.rewards),
        xp_awarded=xp,
        xp_limit_reason=XpLimitReason.HABIT_DAILY_LIMIT if limited else None,
        player=player_xp_out(change, game.level_curve),
        achievements_unlocked=unlocked,
    )


async def undo_habit(
    session: AsyncSession, user: User, habit_id: uuid.UUID, now: datetime, game: GameSettings
) -> HabitUndoOut:
    """Undo today's completion with compensating ledger entries."""
    habit = await _get_owned_habit(session, user.id, habit_id, lock=True)
    today = _today(user, now)
    log = await session.scalar(
        select(HabitLog)
        .where(HabitLog.habit_id == habit.id, HabitLog.completed_on == today, HabitLog.status == HabitLogStatus.DONE)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if log is None:
        raise Conflict("There is no completion today to undo", code="not_completed")

    profile = await lock_profile(session, user.id)
    reversal = aliased(XpLedgerEntry)
    entries = (
        await session.scalars(
            select(XpLedgerEntry).where(
                XpLedgerEntry.user_id == user.id,
                XpLedgerEntry.source_type == LedgerSource.HABIT.value,
                XpLedgerEntry.source_id == habit.id,
                XpLedgerEntry.occurrence_date == today,
                XpLedgerEntry.xp_amount > 0,
                ~exists().where(reversal.reverses_id == XpLedgerEntry.id),
            )
        )
    ).all()
    drafts = [
        LedgerDraft(
            event_key=f"undo:{entry.id}",
            source_type=LedgerSource.HABIT_UNDO.value,
            source_id=habit.id,
            occurrence_date=today,
            attribute_type=entry.attribute_type,
            xp_amount=-entry.xp_amount,
            reason=LedgerReason.HABIT_COMPLETION_UNDONE.value,
            description=habit.title,
            reverses_id=entry.id,
        )
        for entry in entries
    ]
    change = await apply_xp(session, profile, drafts, game.level_curve, now)
    log.status = HabitLogStatus.UNDONE.value
    log.completed_at = None
    log.xp_awarded = 0
    await session.flush()
    return HabitUndoOut(
        habit=await _view(session, habit, user, now, game.rewards),
        xp_reverted=-change.delta,
        player=player_xp_out(change, game.level_curve),
    )


async def freeze_missed(
    session: AsyncSession, user: User, habit_id: uuid.UUID, day: date, now: datetime, game: GameSettings
) -> HabitOut:
    """Cover a missed day (week) so the streak goes on; no XP is given."""
    habit = await _get_owned_habit(session, user.id, habit_id, lock=True)
    _require_active(habit)
    logs = (await _load_logs(session, [habit.id]))[habit.id]
    today = _today(user, now)
    streak = compute_streak(schedule_of(habit), logs.done, logs.frozen, today)
    if day not in streak.freezable:
        raise Conflict("This day cannot be frozen", code="not_freezable")
    if logs.freezes_in_month(day) >= game.rewards.streak_freezes_per_month:
        raise Conflict("No freezes left for that month", code="no_freezes_left")
    log = await _lock_log(session, user.id, habit.id, day)
    if log.status == HabitLogStatus.DONE:
        raise Conflict("This day is already done", code="already_completed")
    log.status = HabitLogStatus.FROZEN.value
    await session.flush()
    return await _view(session, habit, user, now, game.rewards)
