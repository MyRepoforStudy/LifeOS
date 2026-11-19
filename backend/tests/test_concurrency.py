"""Spec scenario 12: concurrent completions never lose or duplicate XP."""

import asyncio

from tests.conftest import Player


async def test_parallel_completions_of_different_quests(player: Player, db) -> None:
    quests = [await player.create_quest(title=f"task {i}", category="career") for i in range(10)]
    responses = await asyncio.gather(*(player.complete(q["id"]) for q in quests))
    assert [r.status_code for r in responses] == [200] * 10
    assert await player.total_xp() == 200
    assert (await player.attributes())["career"] == 200
    assert (await db("SELECT count(*) FROM xp_ledger"))[0][0] == 10


async def test_parallel_completions_of_the_same_quest(player: Player) -> None:
    quest = await player.create_quest(difficulty="hard")
    responses = await asyncio.gather(*(player.complete(quest["id"]) for _ in range(5)))
    assert sorted(r.status_code for r in responses) == [200, 409, 409, 409, 409]
    assert await player.total_xp() == 40


async def test_parallel_duplicates_with_one_idempotency_key(player: Player) -> None:
    quest = await player.create_quest(difficulty="hard")
    responses = await asyncio.gather(*(player.complete(quest["id"], key="retry-storm") for _ in range(4)))
    assert [r.status_code for r in responses] == [200] * 4
    assert sum(r.headers.get("Idempotent-Replayed") == "true" for r in responses) == 3
    assert await player.total_xp() == 40


async def test_daily_limit_holds_under_concurrency(player: Player) -> None:
    quests = [await player.create_quest(title=f"tiny {i}", difficulty="simple") for i in range(8)]
    responses = await asyncio.gather(*(player.complete(q["id"]) for q in quests))
    assert all(r.status_code == 200 for r in responses)
    assert sorted(r.json()["xp_awarded"] for r in responses) == [0, 0, 0, 10, 10, 10, 10, 10]
    assert await player.total_xp() == 50
