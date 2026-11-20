"""Adaptive Engine rules (spec section 11), free of the database.

The plan is compared with what was done over complete local days: today is still
open and never counts as a miss. Every planned unit is a Slot: a day of a daily quest
or habit, or a whole week of a weekly one (placed on its Sunday).
"""

import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

# Spec 11.2: under 40% of the plan for several days -> lighten it; 90%+ -> harder.
OVERLOAD_RATE = 0.40
EASY_RATE = 0.90
# Enough plan to judge a week: at least this many units over at least 3 days.
WEEK_MIN_PLANNED = 6
WEEK_MIN_PLAN_DAYS = 3
# Raising the bar needs two steady weeks.
EASY_MIN_PLANNED = 10
EASY_MIN_WEEK_PLANNED = 4
# An item done less often than this is worth lightening when the plan is overloaded.
STRUGGLING_RATE = 0.5
STRUGGLING_MIN_PLANNED = 2
# One item that keeps being missed although the plan as a whole is fine.
STALLED_RATE = 0.25
STALLED_MIN_PLANNED = 5
MAX_STALLED = 2
# A quiet stretch during a running cycle: offer a pause (spec 11.4).
REST_QUIET_DAYS = 3
REST_LOOKBACK_DAYS = 14
REST_MIN_ACTIVE_DAYS = 3

MAX_CHANGES = 5
MAX_POSTPONED = 3
POSTPONE_DAYS = 7
# Optional (low priority) one-off quests due this soon, or overdue this long, move on.
POSTPONE_AHEAD_DAYS = 3
POSTPONE_OVERDUE_DAYS = 7
LIGHT_TIMES_PER_WEEK = 3

# A dismissed or applied recommendation does not come back about the same thing at once.
COOLDOWN_DAYS = 7
EASY_COOLDOWN_DAYS = 14
# Numbers older than this are stale: the recommendation expires and may be made again.
PENDING_TTL_DAYS = 14

# Spread over the week when there is no history to go by.
_WEEKDAY_PREFERENCE = (1, 3, 5, 2, 4, 6, 7)


@dataclass(frozen=True)
class Slot:
    item: str  # "quest:<id>" or "habit:<id>"
    kind: Literal["quest", "habit"]
    category: str
    day: date
    planned: int = 1
    done: int = 0
    skipped: int = 0
    learning_planned: int = 0  # minutes
    learning_done: int = 0


@dataclass
class Tally:
    planned: int = 0
    done: int = 0
    skipped: int = 0

    def add(self, slot: Slot) -> None:
        self.planned += slot.planned
        self.done += slot.done
        self.skipped += slot.skipped

    @property
    def missed(self) -> int:
        return self.planned - self.done

    @property
    def rate(self) -> float | None:
        return round(self.done / self.planned, 4) if self.planned else None


@dataclass
class Window:
    first_day: date
    last_day: date
    total: Tally = field(default_factory=Tally)
    quests: Tally = field(default_factory=Tally)
    habits: Tally = field(default_factory=Tally)
    categories: dict[str, Tally] = field(default_factory=dict)
    items: dict[str, Tally] = field(default_factory=dict)
    learning_planned: int = 0
    learning_done: int = 0
    plan_days: int = 0

    @property
    def days(self) -> int:
        return (self.last_day - self.first_day).days + 1


def summarize(slots: Iterable[Slot], first_day: date, last_day: date) -> Window:
    window = Window(first_day, last_day)
    days: set[date] = set()
    for slot in slots:
        if not first_day <= slot.day <= last_day:
            continue
        days.add(slot.day)
        window.total.add(slot)
        (window.quests if slot.kind == "quest" else window.habits).add(slot)
        window.categories.setdefault(slot.category, Tally()).add(slot)
        window.items.setdefault(slot.item, Tally()).add(slot)
        window.learning_planned += slot.learning_planned
        window.learning_done += slot.learning_done
    window.plan_days = len(days)
    return window


def is_overloaded(week: Window) -> bool:
    rate = week.total.rate
    return (
        week.total.planned >= WEEK_MIN_PLANNED
        and week.plan_days >= WEEK_MIN_PLAN_DAYS
        and rate is not None
        and rate < OVERLOAD_RATE
    )


def is_too_easy(fortnight: Window, week: Window) -> bool:
    return (
        fortnight.total.planned >= EASY_MIN_PLANNED
        and (fortnight.total.rate or 0) >= EASY_RATE
        and week.total.planned >= EASY_MIN_WEEK_PLANNED
        and (week.total.rate or 0) >= EASY_RATE
    )


def focus_category(window: Window) -> str | None:
    """The area with the most misses: where the plan is heaviest."""
    missed = {category: tally for category, tally in window.categories.items() if tally.missed > 0}
    if not missed:
        return None
    return max(missed, key=lambda category: (missed[category].missed, missed[category].planned))


def lighter_minutes(minutes: int, block: int) -> int | None:
    """About half the plan, in whole blocks: 120 -> 60, 90 -> 60, 60 -> 30, 30 -> None."""
    target = max(block, math.ceil(minutes / 2 / block) * block)
    return target if target < minutes else None


def heavier_minutes(minutes: int, block: int, cap: int) -> int | None:
    """One more block, up to the daily learning cap."""
    target = min(cap, minutes + block)
    return target if target > minutes else None


def lighter_weekdays(current: list[int] | None, done_days: Iterable[date]) -> list[int] | None:
    """Keep 3 days a week, the ones that worked best so far."""
    days = sorted(current) if current else list(range(1, 8))
    if len(days) <= LIGHT_TIMES_PER_WEEK:
        return None
    done = Counter(day.isoweekday() for day in done_days)
    ranked = sorted(days, key=lambda weekday: (-done[weekday], _WEEKDAY_PREFERENCE.index(weekday)))
    return sorted(ranked[:LIGHT_TIMES_PER_WEEK])


def lighter_times_per_week(times_per_week: int) -> int | None:
    """About half as often, at most 3 times a week: daily -> 3, 5 -> 3, 3 -> 2, 2 -> 1."""
    target = max(1, min(LIGHT_TIMES_PER_WEEK, math.ceil(times_per_week / 2)))
    return target if target < times_per_week else None


def percent(rate: float | None) -> int:
    return round((rate or 0) * 100)
