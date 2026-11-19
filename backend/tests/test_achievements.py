import asyncio
from collections.abc import AsyncIterator

import pytest

from tests.conftest import Clock, Player


@pytest.fixture
async def achievements_on(db) -> AsyncIterator[None]:
    await db("UPDATE achievements SET is_active = true")
    yield
    await db("UPDATE achievements SET is_active = false")


def codes(result: dict) -> list[str]:
    return sorted(a["code"] for a in result["achievements_unlocked"])


async def test_first_completion_unlocks_first_step_once(player: Player, achievements_on: None) -> None:
    """Spec scenario 5: an achievement is unlocked only once."""
    first = (await player.complete((await player.create_quest())["id"])).json()
    assert codes(first) == ["first_step"]
    assert first["achievements_unlocked"][0]["xp_reward"] == 25
    assert first["player"]["total_xp"] == 20 + 25

    second = (await player.complete((await player.create_quest())["id"])).json()
    assert codes(second) == []
    unlocked = (await player.get("/achievements/unlocked")).json()
    assert [a["code"] for a in unlocked] == ["first_step"]
    assert await player.total_xp() == 20 + 25 + 20


async def test_a_project_unlocks_several_achievements_and_a_level(player: Player, achievements_on: None) -> None:
    quest = await player.create_quest(difficulty="epic", category="career")
    result = (await player.complete(quest["id"])).json()
    assert codes(result) == ["first_project", "first_step"]
    assert result["player"]["total_xp"] == 100 + 25 + 50
    assert result["player"]["level"] == 2
    assert result["player"]["leveled_up"] is True


async def test_achievement_xp_can_unlock_a_level_achievement(player: Player, achievements_on: None, db) -> None:
    await db(
        "UPDATE achievements SET condition_config = CAST(:cfg AS jsonb) WHERE code = 'level_5'",
        cfg='{"type": "level", "level": 2}',
    )
    try:
        # The challenge gives 80 XP (level 1); first_step (+25) crosses 100 -> level 2 -> level_5 (+50).
        quest = await player.create_quest(difficulty="hard", quest_type="challenge", category="other")
        result = (await player.complete(quest["id"])).json()
    finally:
        await db(
            "UPDATE achievements SET condition_config = CAST(:cfg AS jsonb) WHERE code = 'level_5'",
            cfg='{"type": "level", "level": 5}',
        )
    assert result["xp_awarded"] == 80
    assert codes(result) == ["first_step", "level_5"]
    assert result["player"]["total_xp"] == 80 + 25 + 50


async def test_progress_is_reported(player: Player, achievements_on: None) -> None:
    habit = (await player.post("/habits", {"title": "Read 20 pages", "category": "learning"})).json()
    await player.post(f"/habits/{habit['id']}/complete")
    catalog = {a["code"]: a for a in (await player.get("/achievements")).json()}
    assert catalog["first_step"]["unlocked"] is True
    assert catalog["first_lesson"]["unlocked"] is True
    assert catalog["active_days_7"]["unlocked"] is False
    assert catalog["active_days_7"]["progress"] == {"current": 1, "target": 7}
    assert catalog["level_20"]["rarity"] == "legendary"


async def test_seven_day_streak(player: Player, clock: Clock, achievements_on: None) -> None:
    habit = (await player.post("/habits", {"title": "Run", "category": "health"})).json()
    unlocked: list[str] = []
    for _ in range(7):
        result = (await player.post(f"/habits/{habit['id']}/complete")).json()
        unlocked += codes(result)
        clock.advance(days=1)
    assert "streak_7" in unlocked
    assert "active_days_7" in unlocked
    assert unlocked.count("streak_7") == 1


async def test_undo_keeps_achievements(player: Player, achievements_on: None) -> None:
    quest = await player.create_quest()
    await player.complete(quest["id"])
    undo = (await player.post(f"/quests/{quest['id']}/undo")).json()
    assert undo["xp_reverted"] == 20
    assert await player.total_xp() == 25
    assert [a["code"] for a in (await player.get("/achievements/unlocked")).json()] == ["first_step"]


async def test_parallel_completions_unlock_once(player: Player, achievements_on: None, db) -> None:
    quests = [await player.create_quest(title=f"task {i}") for i in range(8)]
    results = await asyncio.gather(*(player.complete(q["id"]) for q in quests))
    assert all(r.status_code == 200 for r in results)
    all_codes = [c for r in results for c in codes(r.json())]
    assert all_codes == ["first_step"]
    assert await player.total_xp() == 8 * 20 + 25
    ledger_total = (await db("SELECT sum(xp_amount) FROM xp_ledger"))[0][0]
    assert ledger_total == 8 * 20 + 25
