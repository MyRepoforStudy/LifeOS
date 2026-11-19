from typing import Any

import pytest

from tests.conftest import Clock, Player, PlayerFactory


async def create_habit(player: Player, **fields: Any) -> dict[str, Any]:
    response = await player.post("/habits", {"title": "English 30 min", "category": "learning", **fields})
    assert response.status_code == 201, response.text
    return response.json()


def code(response) -> str:
    return response.json()["error"]["code"]


async def test_completion_gives_xp_and_grows_the_streak(player: Player, clock: Clock) -> None:
    habit = await create_habit(player)
    assert habit["xp_reward"] == 15
    assert habit["attribute_types"] == ["intelligence"]

    first = await player.post(f"/habits/{habit['id']}/complete")
    assert first.status_code == 200
    body = first.json()
    assert body["xp_awarded"] == 15
    assert body["habit"]["done_today"] is True
    assert body["habit"]["streak"]["current"] == 1
    assert code(await player.post(f"/habits/{habit['id']}/complete")) == "already_completed"

    clock.advance(days=1)
    second = (await player.post(f"/habits/{habit['id']}/complete")).json()
    assert second["habit"]["streak"]["current"] == 2
    assert await player.total_xp() == 30
    assert (await player.attributes())["intelligence"] == 30


async def test_missed_day_and_freeze(player: Player, clock: Clock) -> None:
    habit = await create_habit(player)
    path = f"/habits/{habit['id']}"
    await player.post(f"{path}/complete")  # Wed 18
    clock.advance(days=1)
    await player.post(f"{path}/complete")  # Thu 19
    clock.advance(days=2)  # Sat 21: Fri 20 was missed

    view = (await player.get(path)).json()
    assert view["streak"]["current"] == 0
    assert view["streak"]["best"] == 2
    assert view["freezable"] == ["2026-11-20"]
    statuses = {d["date"]: d["status"] for d in view["history"]}
    assert statuses["2026-11-20"] == "missed"
    assert statuses["2026-11-21"] == "open"

    frozen = await player.post(f"{path}/freeze", {"day": "2026-11-20"})
    assert frozen.status_code == 200
    assert frozen.json()["streak"]["current"] == 2
    assert frozen.json()["freezes_left"] == 1

    done = (await player.post(f"{path}/complete")).json()
    assert done["habit"]["streak"]["current"] == 3
    assert await player.total_xp() == 45  # a freeze gives no XP


async def test_freeze_rules(player: Player, clock: Clock) -> None:
    habit = await create_habit(player)
    path = f"/habits/{habit['id']}"
    await player.post(f"{path}/complete")  # Wed 18
    clock.advance(days=4)  # Sun 22: 19, 20 and 21 missed

    assert code(await player.post(f"{path}/freeze", {"day": "2026-11-18"})) == "not_freezable"  # done
    assert code(await player.post(f"{path}/freeze", {"day": "2026-11-22"})) == "not_freezable"  # today
    assert (await player.post(f"{path}/freeze", {"day": "2026-11-19"})).status_code == 200
    assert (await player.post(f"{path}/freeze", {"day": "2026-11-20"})).status_code == 200
    third = await player.post(f"{path}/freeze", {"day": "2026-11-21"})
    assert third.status_code == 409
    assert code(third) in {"no_freezes_left", "not_freezable"}
    assert (await player.get(path)).json()["freezes_left"] == 0


async def test_weekday_habit_only_on_planned_days(player: Player) -> None:
    mondays = await create_habit(player, frequency="weekdays", weekdays=[1])
    assert mondays["required_today"] is False  # START is a Wednesday
    assert code(await player.post(f"/habits/{mondays['id']}/complete")) == "not_scheduled_today"


async def test_weekly_habit_counts_completions_in_the_week(player: Player, clock: Clock) -> None:
    gym = await create_habit(player, title="Gym", category="health", frequency="weekly", times_per_week=2)
    await player.post(f"/habits/{gym['id']}/complete")
    clock.advance(days=1)
    body = (await player.post(f"/habits/{gym['id']}/complete")).json()
    assert body["habit"]["week_done"] == 2
    assert body["habit"]["streak"] == {**body["habit"]["streak"], "unit": "week", "current": 1}


async def test_undo_on_the_same_day(player: Player, db) -> None:
    habit = await create_habit(player)
    path = f"/habits/{habit['id']}"
    await player.post(f"{path}/complete")
    undo = await player.post(f"{path}/undo")
    assert undo.status_code == 200
    assert undo.json()["xp_reverted"] == 15
    assert undo.json()["habit"]["done_today"] is False
    assert await player.total_xp() == 0
    assert code(await player.post(f"{path}/undo")) == "not_completed"
    assert (await player.post(f"{path}/complete")).json()["xp_awarded"] == 15
    rows = await db("SELECT xp_amount FROM xp_ledger ORDER BY created_at, xp_amount DESC")
    assert sorted(r[0] for r in rows) == [-15, 15, 15]


async def test_daily_limit_of_rewarded_habits(player: Player) -> None:
    habits = [await create_habit(player, title=f"habit {i}", category="other") for i in range(11)]
    results = [(await player.post(f"/habits/{h['id']}/complete")).json() for h in habits]
    assert [r["xp_awarded"] for r in results] == [15] * 10 + [0]
    assert results[-1]["xp_limit_reason"] == "habit_daily_limit"


async def test_archived_habit(player: Player) -> None:
    habit = await create_habit(player)
    await player.post(f"/habits/{habit['id']}/complete")
    assert (await player.delete(f"/habits/{habit['id']}")).status_code == 204
    assert (await player.get("/habits")).json() == []
    assert len((await player.get("/habits", include_archived="true")).json()) == 1
    assert code(await player.post(f"/habits/{habit['id']}/complete")) == "habit_archived"
    assert await player.total_xp() == 15


@pytest.mark.parametrize(
    "fields",
    [
        {"frequency": "weekdays"},
        {"frequency": "weekly"},
        {"frequency": "daily", "weekdays": [1, 2]},
        {"frequency": "daily", "times_per_week": 3},
        {"frequency": "weekly", "times_per_week": 8},
    ],
)
async def test_schedule_validation(player: Player, fields: dict[str, Any]) -> None:
    response = await player.post("/habits", {"title": "Bad", "category": "health", **fields})
    assert response.status_code == 422


async def test_habits_are_private(make_player: PlayerFactory) -> None:
    alice, bob = await make_player(), await make_player()
    habit = await create_habit(alice)
    assert (await bob.get(f"/habits/{habit['id']}")).status_code == 404
    assert (await bob.post(f"/habits/{habit['id']}/complete")).status_code == 404
    assert (await bob.post(f"/habits/{habit['id']}/freeze", {"day": "2026-11-17"})).status_code == 404
    assert (await bob.delete(f"/habits/{habit['id']}")).status_code == 404
    assert (await bob.get("/habits")).json() == []
