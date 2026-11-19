import pytest

from app.domain.levels import (
    LevelCurve,
    level_after_change,
    level_for_xp,
    level_progress,
    total_xp_for_level,
    xp_to_next_level,
)

CURVE = LevelCurve()


@pytest.mark.parametrize(
    ("level", "expected"),
    [(1, 100), (2, 283), (3, 520), (4, 800), (5, 1118), (10, 3162), (20, 8944)],
)
def test_xp_to_next_level_follows_formula(level: int, expected: int) -> None:
    # 100 * 10 ** 1.5 = 3162.28 -> 3162; the table in the spec says 3163 (a typo).
    assert xp_to_next_level(level, CURVE) == expected


@pytest.mark.parametrize(("level", "total"), [(1, 0), (2, 100), (3, 383), (10, 11106), (20, 67135)])
def test_total_xp_for_level(level: int, total: int) -> None:
    assert total_xp_for_level(level, CURVE) == total


@pytest.mark.parametrize(
    ("xp", "level"),
    [(0, 1), (99, 1), (100, 2), (382, 2), (383, 3), (11105, 9), (11106, 10)],
)
def test_level_for_xp(xp: int, level: int) -> None:
    assert level_for_xp(xp, CURVE) == level


def test_gain_follows_curve() -> None:
    assert level_after_change(1, 90, 110, CURVE) == 2
    assert level_after_change(1, 0, 400, CURVE) == 3


def test_rebalance_never_takes_levels_away() -> None:
    harder = LevelCurve(base=200)
    # Level 3 was reached on the old curve; on the harder one 400 XP is only level 2.
    assert level_for_xp(400, harder) == 2
    assert level_after_change(3, 400, 410, harder) == 3


def test_undo_loses_only_the_levels_it_crossed() -> None:
    assert level_after_change(2, 110, 90, CURVE) == 1
    assert level_after_change(3, 400, 390, CURVE) == 3
    assert level_after_change(3, 400, 300, CURVE) == 2
    assert level_after_change(1, 50, 0, CURVE) == 1


def test_level_progress() -> None:
    progress = level_progress(150, 2, CURVE)
    assert progress.level_start_xp == 100
    assert progress.next_level_xp == 383
    assert progress.xp_in_level == 50
    assert progress.xp_for_level == 283
    assert progress.xp_to_next_level == 233
    assert progress.progress == pytest.approx(50 / 283, abs=1e-4)


def test_level_progress_when_stored_level_is_above_curve() -> None:
    progress = level_progress(300, 3, CURVE)
    assert progress.xp_in_level == 0
    assert progress.xp_to_next_level == 903 - 300
