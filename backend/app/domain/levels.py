"""Level curve: XP needed to go from level L to L+1 is round(base * L ** exponent).

With the default curve (100 * L^1.5) this gives 100, 283, 520, 800, 1118, ...,
3162 for L=10 and 8944 for L=20. Total XP decides the level; XP never resets.
"""

from bisect import bisect_right
from dataclasses import dataclass
from functools import lru_cache

from pydantic import BaseModel, Field


class LevelCurve(BaseModel, frozen=True):
    base: int = Field(default=100, gt=0)
    exponent: float = Field(default=1.5, gt=0)
    max_level: int = Field(default=500, ge=2)


def xp_to_next_level(level: int, curve: LevelCurve) -> int:
    """XP needed to go from `level` to `level + 1` (round half up)."""
    if level < 1:
        raise ValueError("level must be >= 1")
    return int(curve.base * level**curve.exponent + 0.5)


@lru_cache(maxsize=8)
def _thresholds(base: int, exponent: float, max_level: int) -> tuple[int, ...]:
    """thresholds[i] is the total XP needed to reach level i + 1."""
    curve = LevelCurve(base=base, exponent=exponent, max_level=max_level)
    totals = [0]
    for level in range(1, max_level):
        totals.append(totals[-1] + xp_to_next_level(level, curve))
    return tuple(totals)


def thresholds(curve: LevelCurve) -> tuple[int, ...]:
    return _thresholds(curve.base, curve.exponent, curve.max_level)


def total_xp_for_level(level: int, curve: LevelCurve) -> int:
    """Total XP needed to reach `level` (level 1 needs 0)."""
    if not 1 <= level <= curve.max_level:
        raise ValueError(f"level must be between 1 and {curve.max_level}")
    return thresholds(curve)[level - 1]


def level_for_xp(total_xp: int, curve: LevelCurve) -> int:
    if total_xp < 0:
        raise ValueError("total_xp must be >= 0")
    return bisect_right(thresholds(curve), total_xp)


def level_after_change(stored_level: int, old_total: int, new_total: int, curve: LevelCurve) -> int:
    """New stored level after the total XP changes.

    Gains: the level follows the curve but never goes below the stored level,
    so a later rebalance of the curve cannot take levels away.
    Losses (an undo of a mistaken completion): the player loses only the levels
    that this particular change crossed on the current curve.
    """
    if new_total >= old_total:
        return max(stored_level, level_for_xp(new_total, curve))
    crossed = level_for_xp(old_total, curve) - level_for_xp(new_total, curve)
    return max(1, stored_level - crossed)


@dataclass(frozen=True)
class LevelProgress:
    level: int
    total_xp: int
    level_start_xp: int
    next_level_xp: int | None
    xp_in_level: int
    xp_for_level: int | None
    xp_to_next_level: int | None
    progress: float


def level_progress(total_xp: int, level: int, curve: LevelCurve) -> LevelProgress:
    """Progress inside `level` (the stored level may be above the curve's level after a rebalance)."""
    start = total_xp_for_level(level, curve)
    if level >= curve.max_level:
        return LevelProgress(level, total_xp, start, None, max(0, total_xp - start), None, None, 1.0)
    next_total = total_xp_for_level(level + 1, curve)
    span = next_total - start
    in_level = min(max(0, total_xp - start), span)
    return LevelProgress(
        level=level,
        total_xp=total_xp,
        level_start_xp=start,
        next_level_xp=next_total,
        xp_in_level=in_level,
        xp_for_level=span,
        xp_to_next_level=max(0, next_total - total_xp),
        progress=round(in_level / span, 4),
    )
