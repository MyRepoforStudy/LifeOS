from datetime import date, timedelta

from app.domain.enums import HabitFrequency
from app.domain.streaks import Schedule, compute_streak

MONDAY = date(2026, 11, 2)


def day(offset: int) -> date:
    return MONDAY + timedelta(days=offset)


def days(*offsets: int) -> set[date]:
    return {day(o) for o in offsets}


DAILY = Schedule(HabitFrequency.DAILY, MONDAY)


def test_consecutive_days_count() -> None:
    streak = compute_streak(DAILY, days(0, 1, 2), set(), day(2))
    assert (streak.unit, streak.current, streak.best) == ("day", 3, 3)
    assert streak.last_completed_on == day(2)


def test_today_is_still_open() -> None:
    assert compute_streak(DAILY, days(0, 1, 2), set(), day(3)).current == 3


def test_a_missed_day_ends_the_streak() -> None:
    streak = compute_streak(DAILY, days(0, 1, 3), set(), day(3))
    assert (streak.current, streak.best) == (1, 2)
    assert streak.freezable == [day(2)]


def test_a_frozen_day_keeps_the_streak_without_adding_to_it() -> None:
    streak = compute_streak(DAILY, days(0, 1, 3), days(2), day(3))
    assert streak.current == 3
    assert streak.freezable == []


def test_rest_days_of_a_weekday_habit_do_not_break_it() -> None:
    mon_wed_fri = Schedule(HabitFrequency.WEEKDAYS, MONDAY, weekdays=frozenset({1, 3, 5}))
    streak = compute_streak(mon_wed_fri, days(0, 2, 4, 7), set(), day(8))
    assert streak.current == 4


def test_weekly_habit_counts_weeks() -> None:
    twice = Schedule(HabitFrequency.WEEKLY, MONDAY, times_per_week=2)
    done = days(0, 3, 7, 9, 15)
    streak = compute_streak(twice, done, set(), day(16))
    assert (streak.unit, streak.current) == ("week", 2)

    later = compute_streak(twice, done, set(), day(22))
    assert (later.current, later.best) == (0, 2)
    assert later.freezable == [day(14)]
    assert compute_streak(twice, done, {day(14)}, day(22)).current == 2


def test_only_the_last_week_can_be_frozen() -> None:
    streak = compute_streak(DAILY, days(0), set(), day(20))
    assert streak.freezable == [day(13 + i) for i in range(7)]


def test_days_before_the_start_do_not_count() -> None:
    late_start = Schedule(HabitFrequency.DAILY, day(5))
    streak = compute_streak(late_start, days(5, 6), set(), day(6))
    assert streak.current == 2
    assert streak.freezable == []
