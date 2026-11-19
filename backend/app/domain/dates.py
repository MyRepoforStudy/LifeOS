"""Local dates. Completions count by the user's local date, not by UTC."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones


def validate_timezone(name: str) -> str:
    if name not in _known_timezones():
        raise ValueError(f"Unknown time zone: {name}")
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown time zone: {name}") from exc
    return name


_ZONES: frozenset[str] | None = None


def _known_timezones() -> frozenset[str]:
    global _ZONES
    if _ZONES is None:
        _ZONES = frozenset(available_timezones())
    return _ZONES


def local_date(tz_name: str, at: datetime) -> date:
    return at.astimezone(ZoneInfo(tz_name)).date()


def day_bounds(tz_name: str, day: date) -> tuple[datetime, datetime]:
    """[start, end) of a local day, in UTC."""
    tz = ZoneInfo(tz_name)
    start = datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    return start, end


def next_local_midnight(tz_name: str, at: datetime) -> datetime:
    return day_bounds(tz_name, local_date(tz_name, at))[1]


def week_start(day: date) -> date:
    """Monday of the ISO week."""
    return day - timedelta(days=day.weekday())


def week_end(day: date) -> date:
    return week_start(day) + timedelta(days=6)
