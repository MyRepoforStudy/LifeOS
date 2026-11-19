"""Habit streaks, computed from the habit log (no stored counters that could drift).

Day-based habits (daily, chosen weekdays) count days; "N times per week" habits
count ISO weeks. Rules (docs/decisions.md, item 12):
- only required days (weeks) count; other days are rest days and never break a streak;
- today (the current week) is still open: not having done it yet breaks nothing;
- a frozen day (week) keeps the streak going without adding to it;
- anything else in the past without completion ends the streak.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from app.domain.dates import week_start
from app.domain.enums import HabitFrequency

FREEZE_WINDOW_DAYS = 7
FREEZE_WINDOW_WEEKS = 2


@dataclass(frozen=True)
class Schedule:
    frequency: HabitFrequency
    starts_on: date
    weekdays: frozenset[int] = frozenset()
    times_per_week: int = 1

    @property
    def unit(self) -> Literal["day", "week"]:
        return "week" if self.frequency is HabitFrequency.WEEKLY else "day"

    def is_required(self, day: date) -> bool:
        """Is this a day the habit is planned for (day-based habits)?"""
        if day < self.starts_on:
            return False
        if self.frequency is HabitFrequency.WEEKDAYS:
            return day.isoweekday() in self.weekdays
        return True


@dataclass(frozen=True)
class Streak:
    unit: Literal["day", "week"]
    current: int
    best: int
    last_completed_on: date | None
    # Past required days (weeks: their Mondays) that were missed and can still be frozen.
    freezable: list[date] = field(default_factory=list)


def _days(start: date, end: date) -> Iterable[date]:
    for offset in range((end - start).days + 1):
        yield start + timedelta(days=offset)


def compute_streak(schedule: Schedule, done: set[date], frozen: set[date], today: date) -> Streak:
    if schedule.unit == "week":
        return _weekly_streak(schedule, done, frozen, today)
    return _daily_streak(schedule, done, frozen, today)


def _daily_streak(schedule: Schedule, done: set[date], frozen: set[date], today: date) -> Streak:
    run = best = 0
    for day in _days(schedule.starts_on, today):
        if not schedule.is_required(day):
            continue
        if day in done:
            run += 1
            best = max(best, run)
        elif day in frozen or day == today:
            continue
        else:
            run = 0
    window_start = max(schedule.starts_on, today - timedelta(days=FREEZE_WINDOW_DAYS))
    freezable = [
        day
        for day in _days(window_start, today - timedelta(days=1))
        if schedule.is_required(day) and day not in done and day not in frozen
    ]
    return Streak("day", run, best, max(done, default=None), freezable)


def _weekly_streak(schedule: Schedule, done: set[date], frozen: set[date], today: date) -> Streak:
    first_week = week_start(schedule.starts_on)
    current_week = week_start(today)
    per_week: dict[date, int] = {}
    for day in done:
        per_week[week_start(day)] = per_week.get(week_start(day), 0) + 1

    run = best = 0
    missed: list[date] = []
    week = first_week
    while week <= current_week:
        count = per_week.get(week, 0)
        if count >= schedule.times_per_week:
            run += 1
            best = max(best, run)
        elif week in frozen or week == current_week or week == first_week:
            # The current week is still open; the first one may have started mid-week.
            pass
        else:
            run = 0
            missed.append(week)
        week += timedelta(days=7)
    window_start = current_week - timedelta(days=7 * FREEZE_WINDOW_WEEKS)
    freezable = [w for w in missed if w >= window_start]
    return Streak("week", run, best, max(done, default=None), freezable)


def done_this_week(done: set[date], today: date) -> int:
    start = week_start(today)
    return sum(1 for day in done if start <= day <= start + timedelta(days=6))
