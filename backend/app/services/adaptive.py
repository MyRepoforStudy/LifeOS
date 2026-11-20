"""Adaptive Engine: activity analysis and plan recommendations (spec section 11).

Recommendations are refreshed whenever the player asks for them: at most one pending
recommendation per subject, and a subject that was dismissed or applied rests for a
while. Nothing in the plan changes until the player applies a recommendation; then the
chosen changes are made together, and only if the plan is still what the advice was
based on (otherwise "recommendation_outdated" and nothing changes).

Locks: applying takes the recommendation row first, then quest, habit and cycle rows.
The refresh takes no profile lock and updates only rows that are still pending, so it
never overwrites a decision made at the same moment.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, TypeAdapter
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import adaptive as engine
from app.domain import dates
from app.domain.adaptive import Slot, Tally, Window
from app.domain.enums import (
    OPEN_CYCLE_STATUSES,
    Activity,
    CycleStatus,
    Difficulty,
    HabitFrequency,
    HabitLogStatus,
    OccurrenceStatus,
    QuestCategory,
    QuestStatus,
    QuestType,
    RecommendationStatus,
    RecommendationType,
)
from app.domain.rewards import RewardRules, quest_reward
from app.errors import Conflict, InvalidRequest, NotFound
from app.models import (
    AdaptiveRecommendation,
    CycleGoal,
    Habit,
    HabitLog,
    LifeCycle,
    Quest,
    QuestOccurrence,
    User,
    XpLedgerEntry,
    new_id,
)
from app.schemas import (
    AdaptiveRecommendationOut,
    AnalysisOut,
    CategoryStatOut,
    CyclePauseChange,
    HabitScheduleChange,
    ItemStatOut,
    PlanChange,
    QuestDueChange,
    QuestMinutesChange,
    QuestWeekdaysChange,
    RecommendationApplyIn,
    RecommendationApplyOut,
    WindowOut,
)
from app.services.game_config import GameSettings
from app.services.habits import schedule_of
from app.services.player import effective_timezone
from app.services.quests import remember_plan

HORIZON_DAYS = 30
HISTORY_LIMIT = 20
STRUGGLING_SHOWN = 5
STRUGGLING_MIN_PLANNED = 3
MAX_EASIER = 3

_CHANGES = TypeAdapter(list[PlanChange])
_PENDING = RecommendationStatus.PENDING.value
_AR = AdaptiveRecommendation

# --- the plan of the last days ---------------------------------------------------------


@dataclass
class _Plan:
    today: date
    tz: str
    quests: dict[uuid.UUID, Quest]
    habits: dict[uuid.UUID, Habit]
    slots: list[Slot]
    active_days: set[date]
    xp_by_day: dict[date, int]

    def window(self, back_from: int, back_to: int = 1) -> Window:
        """The days from today - back_from to today - back_to, both included."""
        return engine.summarize(
            self.slots, self.today - timedelta(days=back_from), self.today - timedelta(days=back_to)
        )

    def done_days(self, item: str) -> list[date]:
        return [slot.day for slot in self.slots if slot.item == item and slot.done]


def _local(tz: str, at: datetime | None) -> date | None:
    return dates.local_date(tz, at) if at is not None else None


def _quest_slots(
    quest: Quest, occurrences: dict[tuple[uuid.UUID, date], QuestOccurrence], tz: str, first: date, last: date
) -> list[Slot]:
    # Deleting a quest cancels it. Its days before the deletion stay in the history,
    # like an archived habit's: the past does not change when the plan does.
    if quest.status == QuestStatus.CANCELLED and quest.deleted_at is None:
        return []
    item = f"quest:{quest.id}"
    deleted = _local(tz, quest.deleted_at)
    due = _local(tz, quest.due_at)
    learning = quest.activity == Activity.LEARNING
    history = sorted(quest.plan_history or [], key=lambda entry: entry["until"])

    def plan_on(day: date) -> tuple[list[int] | None, int]:
        """Weekdays and minutes of the plan in effect on that day."""
        for entry in history:
            if day.isoformat() <= entry["until"]:
                return entry.get("weekdays"), entry.get("target_minutes") or 0
        return quest.weekdays, quest.target_minutes or 0

    def slot(day: date, occurrence: QuestOccurrence | None, done: bool, skipped: bool) -> Slot:
        minutes = plan_on(day)[1]
        credited = minutes
        if occurrence is not None and occurrence.minutes_credited is not None:
            credited = occurrence.minutes_credited
        return Slot(
            item=item,
            kind="quest",
            category=quest.category,
            day=day,
            done=int(done),
            skipped=int(skipped),
            learning_planned=minutes if learning else 0,
            learning_done=credited if learning and done else 0,
        )

    def outcome(occurrence: QuestOccurrence | None) -> tuple[bool, bool]:
        status = occurrence.status if occurrence is not None else None
        return status == OccurrenceStatus.COMPLETED, status == OccurrenceStatus.SKIPPED

    slots: list[Slot] = []
    if quest.is_recurring and quest.quest_type == QuestType.DAILY:
        day = max(first, quest.anchor_date)
        end = min(last, due) if due is not None else last
        if deleted is not None:
            end = min(end, deleted)
        while day <= end:
            weekdays = plan_on(day)[0]
            if not weekdays or day.isoweekday() in weekdays:
                occurrence = occurrences.get((quest.id, day))
                done, skipped = outcome(occurrence)
                # The day of creation (or deletion) counts only when something was done.
                if done or skipped or day not in (quest.anchor_date, deleted):
                    slots.append(slot(day, occurrence, done, skipped))
            day += timedelta(days=1)
        return slots

    if quest.is_recurring and quest.quest_type == QuestType.WEEKLY:
        week = dates.week_start(first)
        while week + timedelta(days=6) <= last:
            week_end = week + timedelta(days=6)
            if week_end >= first and week_end >= quest.anchor_date:
                occurrence = occurrences.get((quest.id, week))
                done, skipped = outcome(occurrence)
                partial = (
                    dates.week_start(quest.anchor_date) == week
                    or (due is not None and due < week_end)
                    or (deleted is not None and deleted <= week_end)
                )
                if done or skipped or not partial:
                    slots.append(slot(week_end, occurrence, done, skipped))
            week += timedelta(days=7)
        return slots

    # One-off quests are planned for their deadline; without one there is no plan date.
    if due is not None:
        plan_day = due
    elif quest.quest_type == QuestType.DAILY:
        plan_day = quest.anchor_date
    elif quest.quest_type == QuestType.WEEKLY:
        plan_day = dates.week_start(quest.anchor_date) + timedelta(days=6)
    else:
        return []
    if not first <= plan_day <= last:
        return []
    done = quest.status == QuestStatus.COMPLETED
    skipped = quest.status == QuestStatus.SKIPPED
    if deleted is not None and deleted <= plan_day and not (done or skipped):
        return []
    return [slot(plan_day, occurrences.get((quest.id, quest.anchor_date)), done, skipped)]


def _habit_slots(habit: Habit, done: set[date], frozen: set[date], tz: str, first: date, last: date) -> list[Slot]:
    schedule = schedule_of(habit)
    item = f"habit:{habit.id}"
    archived = None if habit.is_active else _local(tz, habit.archived_at)
    slots: list[Slot] = []
    if schedule.unit == "day":
        day = max(first, schedule.starts_on)
        end = min(last, archived) if archived is not None else last
        while day <= end:
            if schedule.is_required(day) and day not in frozen:
                is_done = day in done
                if is_done or day not in (schedule.starts_on, archived):
                    slots.append(Slot(item=item, kind="habit", category=habit.category, day=day, done=int(is_done)))
            day += timedelta(days=1)
        return slots

    target = schedule.times_per_week
    week = dates.week_start(first)
    while week + timedelta(days=6) <= last:
        week_end = week + timedelta(days=6)
        count = sum(1 for day in done if week <= day <= week_end)
        partial = (
            week_end < schedule.starts_on
            or dates.week_start(schedule.starts_on) == week
            or (archived is not None and archived <= week_end)
        )
        if week_end >= first and week not in frozen and (count >= target or not partial) and week_end >= schedule.starts_on:
            slots.append(
                Slot(item=item, kind="habit", category=habit.category, day=week_end, planned=target, done=min(count, target))
            )
        week += timedelta(days=7)
    return slots


async def _habit_days(
    session: AsyncSession, habit_ids: list[uuid.UUID], first: date, last: date
) -> tuple[dict[uuid.UUID, set[date]], dict[uuid.UUID, set[date]]]:
    done: dict[uuid.UUID, set[date]] = {}
    frozen: dict[uuid.UUID, set[date]] = {}
    if not habit_ids:
        return done, frozen
    rows = await session.execute(
        select(HabitLog.habit_id, HabitLog.completed_on, HabitLog.status).where(
            HabitLog.habit_id.in_(habit_ids),
            HabitLog.completed_on >= first,
            HabitLog.completed_on <= last,
            HabitLog.status.in_([HabitLogStatus.DONE, HabitLogStatus.FROZEN]),
        )
    )
    for habit_id, day, status in rows:
        bucket = done if status == HabitLogStatus.DONE else frozen
        bucket.setdefault(habit_id, set()).add(day)
    return done, frozen


async def _active_days(
    session: AsyncSession, user_id: uuid.UUID, tz: str, since: datetime, until: datetime, first: date, last: date
) -> set[date]:
    """Days with a completed quest or habit (XP or not)."""
    local_day = func.date(func.timezone(tz, QuestOccurrence.completed_at))
    quest_days = await session.scalars(
        select(local_day)
        .distinct()
        .where(
            QuestOccurrence.user_id == user_id,
            QuestOccurrence.status == OccurrenceStatus.COMPLETED,
            QuestOccurrence.completed_at >= since,
            QuestOccurrence.completed_at < until,
        )
    )
    habit_days = await session.scalars(
        select(HabitLog.completed_on)
        .distinct()
        .where(
            HabitLog.user_id == user_id,
            HabitLog.status == HabitLogStatus.DONE,
            HabitLog.completed_on >= first,
            HabitLog.completed_on <= last,
        )
    )
    return set(quest_days.all()) | set(habit_days.all())


async def _xp_by_day(
    session: AsyncSession, user_id: uuid.UUID, tz: str, since: datetime, until: datetime
) -> dict[date, int]:
    local_day = func.date(func.timezone(tz, XpLedgerEntry.created_at))
    rows = await session.execute(
        select(local_day, func.sum(XpLedgerEntry.xp_amount))
        .where(
            XpLedgerEntry.user_id == user_id,
            XpLedgerEntry.created_at >= since,
            XpLedgerEntry.created_at < until,
        )
        .group_by(text("1"))
    )
    return {day: int(total or 0) for day, total in rows}


async def _load_plan(session: AsyncSession, user: User, now: datetime) -> _Plan:
    tz = effective_timezone(user, now)
    today = dates.local_date(tz, now)
    first = today - timedelta(days=HORIZON_DAYS)
    last = today - timedelta(days=1)
    since = dates.day_bounds(tz, first)[0]
    until = dates.day_bounds(tz, today)[0]
    # Weekly plans are placed on Sundays: look back one more week for their logs.
    logs_from = first - timedelta(days=6)

    quests = list(
        (
            await session.scalars(
                select(Quest).where(
                    Quest.user_id == user.id, or_(Quest.deleted_at.is_(None), Quest.deleted_at >= since)
                )
            )
        ).all()
    )
    occurrences: dict[tuple[uuid.UUID, date], QuestOccurrence] = {}
    if quests:
        rows = await session.scalars(
            select(QuestOccurrence).where(
                QuestOccurrence.quest_id.in_([quest.id for quest in quests]),
                QuestOccurrence.occurrence_date >= logs_from,
                QuestOccurrence.occurrence_date <= last,
            )
        )
        occurrences = {(o.quest_id, o.occurrence_date): o for o in rows}
    habits = list(
        (
            await session.scalars(
                select(Habit).where(
                    Habit.user_id == user.id, or_(Habit.is_active.is_(True), Habit.archived_at >= since)
                )
            )
        ).all()
    )
    done, frozen = await _habit_days(session, [habit.id for habit in habits], logs_from, last)

    slots: list[Slot] = []
    for quest in quests:
        slots.extend(_quest_slots(quest, occurrences, tz, first, last))
    for habit in habits:
        slots.extend(_habit_slots(habit, done.get(habit.id, set()), frozen.get(habit.id, set()), tz, first, last))
    return _Plan(
        today=today,
        tz=tz,
        quests={quest.id: quest for quest in quests},
        habits={habit.id: habit for habit in habits},
        slots=slots,
        active_days=await _active_days(session, user.id, tz, since, until, first, last),
        xp_by_day=await _xp_by_day(session, user.id, tz, since, until),
    )


# --- analysis --------------------------------------------------------------------------


def _window_out(plan: _Plan, window: Window) -> WindowOut:
    def in_window(day: date) -> bool:
        return window.first_day <= day <= window.last_day

    return WindowOut(
        days=window.days,
        first_day=window.first_day,
        last_day=window.last_day,
        planned=window.total.planned,
        done=window.total.done,
        skipped=window.total.skipped,
        rate=window.total.rate,
        quests_planned=window.quests.planned,
        quests_done=window.quests.done,
        habits_planned=window.habits.planned,
        habits_done=window.habits.done,
        learning_minutes_planned=window.learning_planned,
        learning_minutes_done=window.learning_done,
        active_days=sum(1 for day in plan.active_days if in_window(day)),
        xp=sum(xp for day, xp in plan.xp_by_day.items() if in_window(day)),
        categories=[
            CategoryStatOut(category=category, planned=tally.planned, done=tally.done, rate=tally.rate)
            for category in QuestCategory
            if (tally := window.categories.get(category.value)) is not None
        ],
    )


def _item_out(plan: _Plan, item: str, tally: Tally) -> ItemStatOut | None:
    """A quest or habit still in the plan; deleted and archived ones are left out."""
    kind, _, raw_id = item.partition(":")
    source: Quest | Habit | None = (
        plan.quests.get(uuid.UUID(raw_id)) if kind == "quest" else plan.habits.get(uuid.UUID(raw_id))
    )
    if source is None:
        return None
    if isinstance(source, Quest) and source.deleted_at is not None:
        return None
    if isinstance(source, Habit) and not source.is_active:
        return None
    return ItemStatOut(
        kind="quest" if kind == "quest" else "habit",
        id=source.id,
        title=source.title,
        category=QuestCategory(source.category),
        planned=tally.planned,
        done=tally.done,
        skipped=tally.skipped,
        rate=tally.rate,
    )


async def get_analysis(session: AsyncSession, user: User, now: datetime) -> AnalysisOut:
    plan = await _load_plan(session, user, now)
    fortnight = plan.window(14)
    struggling = sorted(
        (
            (item, tally)
            for item, tally in fortnight.items.items()
            if tally.planned >= STRUGGLING_MIN_PLANNED and (tally.rate or 0) < engine.STRUGGLING_RATE
        ),
        key=lambda pair: (-pair[1].missed, pair[0]),
    )
    items = [out for item, tally in struggling if (out := _item_out(plan, item, tally)) is not None]
    # A trend needs a real week to compare with, not a single day of a new plan.
    previous = plan.window(14, 8)
    enough = previous.total.planned >= engine.WEEK_MIN_PLANNED and previous.plan_days >= engine.WEEK_MIN_PLAN_DAYS
    return AnalysisOut(
        today=plan.today,
        week=_window_out(plan, plan.window(7)),
        month=_window_out(plan, plan.window(30)),
        previous_week_rate=previous.total.rate if enough else None,
        struggling=items[:STRUGGLING_SHOWN],
    )


# --- proposals -------------------------------------------------------------------------


@dataclass
class _Proposal:
    kind: RecommendationType
    key: str
    title: str
    description: str
    params: dict[str, Any]
    changes: list[BaseModel]


def _learning_reward(quest: Quest, minutes: int, rules: RewardRules) -> int:
    return quest_reward(
        rules,
        quest_type=QuestType(quest.quest_type),
        activity=Activity(quest.activity),
        difficulty=Difficulty(quest.difficulty),
        target_minutes=minutes,
    )


def _minutes_change(quest: Quest, minutes: int, rules: RewardRules) -> QuestMinutesChange:
    return QuestMinutesChange(
        quest_id=quest.id,
        title=quest.title,
        from_minutes=quest.target_minutes or 0,
        to_minutes=minutes,
        from_xp=quest.xp_reward,
        to_xp=_learning_reward(quest, minutes, rules),
    )


def _times_per_week(habit: Habit) -> int:
    if habit.frequency == HabitFrequency.WEEKLY:
        return habit.times_per_week or 1
    if habit.frequency == HabitFrequency.WEEKDAYS:
        return len(habit.weekdays or [])
    return 7


def _plannable_quest(quest: Quest | None) -> bool:
    return (
        quest is not None
        and quest.deleted_at is None
        and quest.status != QuestStatus.CANCELLED
        and quest.is_recurring
        and quest.quest_type == QuestType.DAILY
    )


def _lighten(plan: _Plan, item: str, rules: RewardRules) -> BaseModel | None:
    """The lighter version of one quest or habit, if there is one."""
    kind, _, raw_id = item.partition(":")
    if kind == "quest":
        quest = plan.quests.get(uuid.UUID(raw_id))
        if quest is None or not _plannable_quest(quest):
            return None
        if quest.activity == Activity.LEARNING and quest.target_minutes:
            minutes = engine.lighter_minutes(quest.target_minutes, rules.learning_block_minutes)
            if minutes is not None:
                return _minutes_change(quest, minutes, rules)
        weekdays = engine.lighter_weekdays(quest.weekdays, plan.done_days(item))
        if weekdays is None:
            return None
        return QuestWeekdaysChange(
            quest_id=quest.id,
            title=quest.title,
            from_weekdays=sorted(quest.weekdays) if quest.weekdays else None,
            to_weekdays=weekdays,
        )
    habit = plan.habits.get(uuid.UUID(raw_id))
    if habit is None or not habit.is_active:
        return None
    times = engine.lighter_times_per_week(_times_per_week(habit))
    if times is None:
        return None
    return HabitScheduleChange(
        habit_id=habit.id,
        title=habit.title,
        from_frequency=HabitFrequency(habit.frequency),
        from_weekdays=sorted(habit.weekdays) if habit.weekdays else None,
        from_times_per_week=habit.times_per_week,
        to_times_per_week=times,
    )


def _postponements(plan: _Plan, now: datetime) -> list[QuestDueChange]:
    """Optional (low priority) one-off quests due soon or recently overdue move a week on."""
    soonest = plan.today - timedelta(days=engine.POSTPONE_OVERDUE_DAYS)
    latest = plan.today + timedelta(days=engine.POSTPONE_AHEAD_DAYS)
    changes: list[QuestDueChange] = []
    candidates = [
        quest
        for quest in plan.quests.values()
        if quest.deleted_at is None
        and not quest.is_recurring
        and quest.priority == 1
        and quest.status == QuestStatus.ACTIVE
        and quest.due_at is not None
        and soonest <= dates.local_date(plan.tz, quest.due_at) <= latest
    ]
    for quest in sorted(candidates, key=lambda q: (q.due_at, q.title)):
        assert quest.due_at is not None
        changes.append(
            QuestDueChange(
                quest_id=quest.id,
                title=quest.title,
                from_due=quest.due_at,
                to_due=max(quest.due_at, now) + timedelta(days=engine.POSTPONE_DAYS),
            )
        )
    return changes[: engine.MAX_POSTPONED]


def _overload(plan: _Plan, week: Window, rules: RewardRules, now: datetime) -> _Proposal:
    struggling = sorted(
        (
            item
            for item, tally in week.items.items()
            if tally.planned >= engine.STRUGGLING_MIN_PLANNED and (tally.rate or 0) < engine.STRUGGLING_RATE
        ),
        key=lambda item: (-week.items[item].missed, item),
    )
    changes: list[BaseModel] = []
    for item in struggling:
        if len(changes) >= engine.MAX_CHANGES:
            break
        if (change := _lighten(plan, item, rules)) is not None:
            changes.append(change)
    changes.extend(_postponements(plan, now)[: max(0, engine.MAX_CHANGES - len(changes))])
    rate = engine.percent(week.total.rate)
    return _Proposal(
        kind=RecommendationType.OVERLOAD,
        key="overload",
        title="Lighten the plan",
        description=(
            f"{week.total.done} of {week.total.planned} planned items done in the last 7 days ({rate}%). "
            "A lighter plan is easier to keep."
        ),
        params={
            "done": week.total.done,
            "planned": week.total.planned,
            "rate": rate,
            "focus": engine.focus_category(week),
        },
        changes=changes,
    )


def _stalled(plan: _Plan, fortnight: Window, rules: RewardRules) -> list[_Proposal]:
    proposals: list[_Proposal] = []
    stalled = sorted(
        (
            (item, tally)
            for item, tally in fortnight.items.items()
            if tally.planned >= engine.STALLED_MIN_PLANNED and (tally.rate or 0) < engine.STALLED_RATE
        ),
        key=lambda pair: (-pair[1].missed, pair[0]),
    )
    for item, tally in stalled:
        if len(proposals) >= engine.MAX_STALLED:
            break
        change = _lighten(plan, item, rules)
        if change is None:
            continue
        title = getattr(change, "title", "")
        proposals.append(
            _Proposal(
                kind=RecommendationType.STALLED_ITEM,
                key=f"stalled:{item}",
                title=f"Make “{title}” easier",
                description=f"Done {tally.done} of {tally.planned} times in the last 14 days.",
                params={"title": title, "kind": item.partition(":")[0], "done": tally.done, "planned": tally.planned},
                changes=[change],
            )
        )
    return proposals


def _too_easy(plan: _Plan, fortnight: Window, rules: RewardRules) -> _Proposal:
    changes: list[BaseModel] = []
    learning = sorted(
        (q for q in plan.quests.values() if _plannable_quest(q) and q.activity == Activity.LEARNING and q.target_minutes),
        key=lambda q: (q.title, q.id),
    )
    for quest in learning:
        if len(changes) >= MAX_EASIER:
            break
        tally = fortnight.items.get(f"quest:{quest.id}")
        if tally is None or (tally.rate or 0) < engine.EASY_RATE or quest.target_minutes is None:
            continue
        minutes = engine.heavier_minutes(
            quest.target_minutes, rules.learning_block_minutes, rules.learning_daily_cap_minutes
        )
        if minutes is not None:
            changes.append(_minutes_change(quest, minutes, rules))
    rate = engine.percent(fortnight.total.rate)
    return _Proposal(
        kind=RecommendationType.TOO_EASY,
        key="too_easy",
        title="Raise the bar",
        description=f"{rate}% of the plan done in the last 14 days: the plan could ask for a little more.",
        params={"done": fortnight.total.done, "planned": fortnight.total.planned, "rate": rate},
        changes=changes,
    )


def _rest(plan: _Plan, cycle: LifeCycle | None) -> _Proposal | None:
    """A quiet stretch after an active time, while a cycle runs: offer to pause it."""
    if cycle is None or cycle.status != CycleStatus.ACTIVE or not cycle.starts_on <= plan.today <= cycle.ends_on:
        return None
    quiet_from = plan.today - timedelta(days=engine.REST_QUIET_DAYS)
    lookback_from = quiet_from - timedelta(days=engine.REST_LOOKBACK_DAYS)
    if any(quiet_from <= day < plan.today for day in plan.active_days):
        return None
    if sum(1 for day in plan.active_days if lookback_from <= day < quiet_from) < engine.REST_MIN_ACTIVE_DAYS:
        return None
    return _Proposal(
        kind=RecommendationType.REST,
        key=f"rest:cycle:{cycle.id}",
        title="Take a breather",
        description=(
            f"No activity in the last {engine.REST_QUIET_DAYS} days, and that is fine. "
            f"Pausing “{cycle.title}” moves its end date."
        ),
        params={"days": engine.REST_QUIET_DAYS, "cycle": cycle.title},
        changes=[CyclePauseChange(cycle_id=cycle.id, title=cycle.title)],
    )


def _proposals(plan: _Plan, cycle: LifeCycle | None, rules: RewardRules, now: datetime) -> list[_Proposal]:
    week = plan.window(7)
    fortnight = plan.window(14)
    proposals: list[_Proposal] = []
    if engine.is_overloaded(week):
        proposals.append(_overload(plan, week, rules, now))
    else:
        proposals.extend(_stalled(plan, fortnight, rules))
    if engine.is_too_easy(fortnight, week):
        proposals.append(_too_easy(plan, fortnight, rules))
    if (rest := _rest(plan, cycle)) is not None:
        proposals.append(rest)
    return proposals


# --- checking and applying changes -----------------------------------------------------


def _weekdays(value: list[int] | None) -> tuple[int, ...] | None:
    return tuple(sorted(value)) if value else None


async def _check(
    session: AsyncSession, user: User, change: BaseModel, today: date, *, lock: bool
) -> Quest | Habit | LifeCycle | None:
    """The row a change applies to, if it is still what the change expects."""
    if isinstance(change, QuestMinutesChange | QuestWeekdaysChange | QuestDueChange):
        stmt = select(Quest).where(
            Quest.id == change.quest_id, Quest.user_id == user.id, Quest.deleted_at.is_(None)
        )
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        quest = await session.scalar(stmt)
        if quest is None or quest.status == QuestStatus.CANCELLED:
            return None
        if isinstance(change, QuestMinutesChange):
            fits = quest.activity == Activity.LEARNING and quest.target_minutes == change.from_minutes
        elif isinstance(change, QuestWeekdaysChange):
            fits = _plannable_quest(quest) and _weekdays(quest.weekdays) == _weekdays(change.from_weekdays)
        else:
            fits = not quest.is_recurring and quest.status == QuestStatus.ACTIVE and quest.due_at == change.from_due
        return quest if fits else None
    if isinstance(change, HabitScheduleChange):
        habit_stmt = select(Habit).where(
            Habit.id == change.habit_id, Habit.user_id == user.id, Habit.is_active.is_(True)
        )
        if lock:
            habit_stmt = habit_stmt.with_for_update().execution_options(populate_existing=True)
        habit = await session.scalar(habit_stmt)
        fits = (
            habit is not None
            and habit.frequency == change.from_frequency
            and _weekdays(habit.weekdays) == _weekdays(change.from_weekdays)
            and habit.times_per_week == change.from_times_per_week
        )
        return habit if fits else None
    assert isinstance(change, CyclePauseChange)
    cycle_stmt = select(LifeCycle).where(LifeCycle.id == change.cycle_id, LifeCycle.user_id == user.id)
    if lock:
        cycle_stmt = cycle_stmt.with_for_update().execution_options(populate_existing=True)
    cycle = await session.scalar(cycle_stmt)
    if cycle is None or cycle.status != CycleStatus.ACTIVE or not cycle.starts_on <= today <= cycle.ends_on:
        return None
    return cycle


async def _goal_is_open(session: AsyncSession, goal_id: uuid.UUID) -> bool:
    found = await session.scalar(
        select(CycleGoal.id)
        .join(LifeCycle, LifeCycle.id == CycleGoal.cycle_id)
        .where(CycleGoal.id == goal_id, LifeCycle.status.in_([s.value for s in OPEN_CYCLE_STATUSES]))
    )
    return found is not None


async def _apply_change(
    session: AsyncSession,
    change: BaseModel,
    row: Quest | Habit | LifeCycle,
    now: datetime,
    today: date,
    game: GameSettings,
) -> None:
    if isinstance(change, QuestMinutesChange) and isinstance(row, Quest):
        remember_plan(row, today)
        row.target_minutes = change.to_minutes
        row.xp_reward = _learning_reward(row, change.to_minutes, game.rewards)
    elif isinstance(change, QuestWeekdaysChange) and isinstance(row, Quest):
        remember_plan(row, today)
        row.weekdays = change.to_weekdays
    elif isinstance(change, QuestDueChange) and isinstance(row, Quest):
        row.due_at = change.to_due
    elif isinstance(change, HabitScheduleChange) and isinstance(row, Habit):
        # The schedule of a habit never changes in place: its streak history depends on it.
        row.is_active = False
        row.archived_at = now
        goal_id = row.goal_id if row.goal_id and await _goal_is_open(session, row.goal_id) else None
        session.add(
            Habit(
                id=new_id(),
                user_id=row.user_id,
                title=row.title,
                description=row.description,
                category=row.category,
                attribute_types=list(row.attribute_types),
                frequency=HabitFrequency.WEEKLY.value,
                weekdays=None,
                times_per_week=change.to_times_per_week,
                xp_reward=game.rewards.habit,
                goal_id=goal_id,
                starts_on=today,
                is_active=True,
            )
        )
    elif isinstance(change, CyclePauseChange) and isinstance(row, LifeCycle):
        row.status = CycleStatus.PAUSED.value
        row.paused_on = today


def _lock_order(change: BaseModel) -> tuple[int, str]:
    """Quests, then habits, then the cycle; each kind by id."""
    if isinstance(change, QuestMinutesChange | QuestWeekdaysChange | QuestDueChange):
        return 0, str(change.quest_id)
    if isinstance(change, HabitScheduleChange):
        return 1, str(change.habit_id)
    return 2, ""


# --- stored recommendations ------------------------------------------------------------


def _out(rec: AdaptiveRecommendation) -> AdaptiveRecommendationOut:
    return AdaptiveRecommendationOut(
        id=rec.id,
        recommendation_type=RecommendationType(rec.recommendation_type),
        status=RecommendationStatus(rec.status),
        title=rec.title,
        description=rec.description,
        params=rec.params,
        changes=_CHANGES.validate_python(rec.suggested_changes),
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        applied_at=rec.applied_at,
        dismissed_at=rec.dismissed_at,
    )


async def _still_valid(session: AsyncSession, user: User, rec: AdaptiveRecommendation, today: date) -> bool:
    for change in _CHANGES.validate_python(rec.suggested_changes):
        if await _check(session, user, change, today, lock=False) is None:
            return False
    return True


async def _resting_keys(session: AsyncSession, user_id: uuid.UUID, now: datetime) -> set[str]:
    """Subjects dismissed or applied recently: they do not come back at once."""
    since = now - timedelta(days=max(engine.COOLDOWN_DAYS, engine.EASY_COOLDOWN_DAYS))
    rows = await session.execute(
        select(_AR.target_key, _AR.recommendation_type, _AR.applied_at, _AR.dismissed_at).where(
            _AR.user_id == user_id,
            _AR.status.in_([RecommendationStatus.APPLIED.value, RecommendationStatus.DISMISSED.value]),
            or_(_AR.applied_at >= since, _AR.dismissed_at >= since),
        )
    )
    resting: set[str] = set()
    for key, kind, applied_at, dismissed_at in rows:
        closed_at = applied_at or dismissed_at
        days = engine.COOLDOWN_DAYS
        if dismissed_at is not None and kind == RecommendationType.TOO_EASY:
            days = engine.EASY_COOLDOWN_DAYS
        if closed_at is not None and closed_at >= now - timedelta(days=days):
            resting.add(key)
    return resting


async def _sync(session: AsyncSession, user: User, proposals: list[_Proposal], today: date, now: datetime) -> None:
    stored = list(
        (
            await session.scalars(
                select(_AR).where(_AR.user_id == user.id, _AR.status == _PENDING).order_by(_AR.id)
            )
        ).all()
    )
    by_key = {proposal.key: proposal for proposal in proposals}
    kept: set[str] = set()
    expired: list[uuid.UUID] = []
    stale_before = now - timedelta(days=engine.PENDING_TTL_DAYS)
    for rec in stored:
        proposal = by_key.get(rec.target_key)
        if proposal is None or rec.created_at < stale_before or not await _still_valid(session, user, rec, today):
            expired.append(rec.id)
            continue
        kept.add(rec.target_key)
        # Fresh numbers; the changes the player may be reading stay as they are.
        if rec.params != proposal.params or rec.description != proposal.description:
            await session.execute(
                update(_AR)
                .where(_AR.id == rec.id, _AR.status == _PENDING)
                .values(params=proposal.params, title=proposal.title, description=proposal.description, updated_at=now)
            )
    if expired:
        await session.execute(
            update(_AR)
            .where(_AR.id.in_(expired), _AR.status == _PENDING)
            .values(status=RecommendationStatus.EXPIRED.value, expired_at=now, updated_at=now)
        )
    resting = await _resting_keys(session, user.id, now)
    for proposal in proposals:
        if proposal.key in kept or proposal.key in resting:
            continue
        await session.execute(
            pg_insert(_AR)
            .values(
                id=new_id(),
                user_id=user.id,
                recommendation_type=proposal.kind.value,
                target_key=proposal.key,
                title=proposal.title,
                description=proposal.description,
                params=proposal.params,
                suggested_changes=[change.model_dump(mode="json") for change in proposal.changes],
                status=_PENDING,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "target_key"], index_where=text("status = 'pending'"))
        )


async def _running_cycle(session: AsyncSession, user_id: uuid.UUID) -> LifeCycle | None:
    return await session.scalar(
        select(LifeCycle).where(
            LifeCycle.user_id == user_id, LifeCycle.status.in_([s.value for s in OPEN_CYCLE_STATUSES])
        )
    )


async def list_recommendations(
    session: AsyncSession, user: User, now: datetime, game: GameSettings
) -> list[AdaptiveRecommendationOut]:
    """Refresh the recommendations, then return the pending ones and recent decisions."""
    plan = await _load_plan(session, user, now)
    cycle = await _running_cycle(session, user.id)
    await _sync(session, user, _proposals(plan, cycle, game.rewards, now), plan.today, now)
    pending = (
        await session.scalars(
            select(_AR)
            .where(_AR.user_id == user.id, _AR.status == _PENDING)
            .order_by(_AR.created_at.desc(), _AR.id)
            .execution_options(populate_existing=True)
        )
    ).all()
    history = (
        await session.scalars(
            select(_AR)
            .where(_AR.user_id == user.id, _AR.status != _PENDING)
            .order_by(_AR.updated_at.desc(), _AR.id)
            .limit(HISTORY_LIMIT)
            .execution_options(populate_existing=True)
        )
    ).all()
    return [_out(rec) for rec in [*pending, *history]]


async def _get_owned(
    session: AsyncSession, user_id: uuid.UUID, recommendation_id: uuid.UUID
) -> AdaptiveRecommendation:
    rec = await session.scalar(
        select(_AR)
        .where(_AR.id == recommendation_id, _AR.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if rec is None:
        raise NotFound("Recommendation not found", code="recommendation_not_found")
    if rec.status != _PENDING:
        raise Conflict("The recommendation is already closed", code="recommendation_closed")
    return rec


async def apply_recommendation(
    session: AsyncSession,
    user: User,
    recommendation_id: uuid.UUID,
    data: RecommendationApplyIn,
    now: datetime,
    game: GameSettings,
) -> RecommendationApplyOut:
    """Make the chosen changes together, or none of them (spec scenario 9: only on consent)."""
    rec = await _get_owned(session, user.id, recommendation_id)
    changes = _CHANGES.validate_python(rec.suggested_changes)
    if not changes:
        raise Conflict("This recommendation has no changes to apply", code="nothing_to_apply")
    chosen = data.changes if data.changes is not None else list(range(len(changes)))
    if not chosen or len(set(chosen)) != len(chosen) or max(chosen) >= len(changes):
        raise InvalidRequest("Choose changes of this recommendation by their index", code="invalid_changes")

    today = dates.local_date(effective_timezone(user, now), now)
    selected = sorted((changes[index] for index in chosen), key=_lock_order)
    checked: list[tuple[BaseModel, Quest | Habit | LifeCycle]] = []
    for change in selected:
        row = await _check(session, user, change, today, lock=True)
        if row is None:
            raise Conflict("The plan has changed since this recommendation", code="recommendation_outdated")
        checked.append((change, row))
    for change, row in checked:
        await _apply_change(session, change, row, now, today, game)

    rec.status = RecommendationStatus.APPLIED.value
    rec.applied_at = now
    rec.updated_at = now
    await session.flush()
    return RecommendationApplyOut(recommendation=_out(rec), applied=len(checked))


async def dismiss_recommendation(
    session: AsyncSession, user: User, recommendation_id: uuid.UUID, now: datetime
) -> AdaptiveRecommendationOut:
    rec = await _get_owned(session, user.id, recommendation_id)
    rec.status = RecommendationStatus.DISMISSED.value
    rec.dismissed_at = now
    rec.updated_at = now
    await session.flush()
    return _out(rec)
