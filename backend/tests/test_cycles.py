"""Life cycles (spec section 10, scenario 8: a completed cycle keeps its history)."""

from collections.abc import AsyncIterator
from typing import Any

import pytest

from tests.conftest import Clock, Player, PlayerFactory


async def create_cycle(player: Player, **fields: Any) -> dict[str, Any]:
    response = await player.post("/cycles", {"title": "DevOps Growth", "duration_days": 30, **fields})
    assert response.status_code == 201, response.text
    return response.json()


def code(response) -> str:
    return response.json()["error"]["code"]


def manual(title: str, target: int = 1, **extra: Any) -> dict[str, Any]:
    return {"title": title, "category": "career", "target_value": target, **extra}


async def test_create_and_current(player: Player) -> None:
    cycle = await create_cycle(
        player,
        goals=[
            {"title": "Kubernetes", "category": "learning", "metric": "minutes", "target_value": 600},
            manual("CKA exam"),
        ],
    )
    assert cycle["status"] == "active"
    assert (cycle["starts_on"], cycle["ends_on"]) == ("2026-11-18", "2026-12-17")
    assert cycle["day_number"] == 1
    assert cycle["goals_total"] == 2
    assert cycle["goals"][1]["metric"] == "manual"
    assert (await player.get("/cycles/current")).json()["id"] == cycle["id"]
    assert code(await player.post("/cycles", {"title": "Second", "duration_days": 30})) == "cycle_already_open"


@pytest.mark.parametrize(
    ("fields", "status", "error"),
    [
        ({"duration_days": 5}, 422, "validation_error"),
        ({"duration_days": 400}, 422, "validation_error"),
        ({"starts_on": "2026-11-17"}, 422, "invalid_start_date"),
        ({"starts_on": "2027-01-01"}, 422, "invalid_start_date"),
    ],
)
async def test_validation(player: Player, fields: dict[str, Any], status: int, error: str) -> None:
    response = await player.post("/cycles", {"title": "Bad", "duration_days": 30, **fields})
    assert response.status_code == status
    assert code(response) == error


async def test_planned_cycle(player: Player, clock: Clock) -> None:
    cycle = await create_cycle(player, starts_on="2026-11-20")
    assert cycle["status"] == "planned"
    assert cycle["day_number"] == 0
    assert code(await player.post(f"/cycles/{cycle['id']}/pause")) == "cycle_not_running"
    clock.advance(days=2)
    assert (await player.get("/cycles/current")).json()["status"] == "active"


async def test_goal_progress_from_linked_quests_and_habits(player: Player) -> None:
    cycle = await create_cycle(
        player,
        goals=[
            {"title": "Kubernetes", "category": "learning", "metric": "minutes", "target_value": 120},
            {"title": "Workouts", "category": "health", "metric": "completions", "target_value": 3},
        ],
    )
    minutes_goal, workouts_goal = cycle["goals"]
    quest = await player.create_quest(
        title="K8s 60 min",
        quest_type="daily",
        category="learning",
        activity="learning",
        target_minutes=60,
        goal_id=minutes_goal["id"],
    )
    assert quest["goal_id"] == minutes_goal["id"]
    await player.complete(quest["id"])
    habit = (await player.post("/habits", {"title": "Gym", "category": "health", "goal_id": workouts_goal["id"]})).json()
    assert habit["goal_id"] == workouts_goal["id"]
    await player.post(f"/habits/{habit['id']}/complete")

    view = (await player.get(f"/cycles/{cycle['id']}")).json()
    goals = {g["title"]: g for g in view["goals"]}
    assert goals["Kubernetes"]["current_value"] == 60
    assert goals["Kubernetes"]["progress"] == 0.5
    assert goals["Kubernetes"]["linked_quests"] == 1
    assert goals["Workouts"]["current_value"] == 1
    assert goals["Workouts"]["linked_habits"] == 1
    assert view["xp_in_cycle"] == 25 + 15

    unlinked = await player.patch(f"/quests/{quest['id']}", {"goal_id": None})
    assert unlinked.json()["goal_id"] is None


async def test_manual_goals_and_editing(player: Player) -> None:
    cycle = await create_cycle(
        player,
        goals=[
            manual("Read 3 books", 3, unit="books"),
            {"title": "Auto", "category": "health", "metric": "completions", "target_value": 5},
        ],
    )
    path = f"/cycles/{cycle['id']}"
    books, auto = cycle["goals"]
    updated = (await player.patch(f"{path}/goals/{books['id']}", {"current_value": 2})).json()
    assert updated["goals"][0]["current_value"] == 2
    assert updated["goals"][0]["done"] is False
    assert code(await player.patch(f"{path}/goals/{auto['id']}", {"current_value": 3})) == "goal_not_manual"

    added = await player.post(f"{path}/goals", manual("Ship a project"))
    assert added.status_code == 201
    assert added.json()["goals_total"] == 3
    removed = await player.delete(f"{path}/goals/{auto['id']}")
    assert removed.json()["goals_total"] == 2


async def test_pause_moves_the_end_date(player: Player, clock: Clock) -> None:
    cycle = await create_cycle(player)
    path = f"/cycles/{cycle['id']}"
    clock.advance(days=2)  # Fri 20
    paused = (await player.post(f"{path}/pause")).json()
    assert paused["status"] == "paused"
    clock.advance(days=5)  # Wed 25
    assert (await player.get(path)).json()["ends_on"] == "2026-12-22"  # shown as if resumed now
    resumed = (await player.post(f"{path}/resume")).json()
    assert resumed["status"] == "active"
    assert resumed["ends_on"] == "2026-12-22"
    assert resumed["paused_days"] == 5
    assert resumed["day_number"] == 3  # 18, 19 and 25
    assert code(await player.post(f"{path}/resume")) == "cycle_not_paused"


async def test_completing_after_the_end_gives_the_reward(player: Player, clock: Clock) -> None:
    cycle = await create_cycle(player, duration_days=7, goals=[manual("A"), manual("B")])
    path = f"/cycles/{cycle['id']}"
    await player.patch(f"{path}/goals/{cycle['goals'][0]['id']}", {"current_value": 1})
    clock.advance(days=7)  # Wed 25; the cycle ended on Tue 24

    finished = (await player.get(path)).json()
    assert finished["status"] == "finished"
    assert finished["reached_end"] is True

    result = (await player.post(f"{path}/complete")).json()
    assert result["xp_awarded"] == 100  # 200 x 1/2 goals
    assert result["player"]["total_xp"] == 100
    cycle_view = result["cycle"]
    assert cycle_view["status"] == "completed"
    report = cycle_view["report"]
    assert (report["goals_done"], report["goals_total"]) == (1, 2)
    assert report["finished_early"] is False
    assert report["cycle_xp"] == 100
    assert {"code": "stalled_goal", "params": {"title": "B"}} in report["recommendations"]

    # Scenario 8: the history is kept and never changes again.
    assert code(await player.post(f"{path}/complete")) == "cycle_closed"
    assert code(await player.patch(f"{path}/goals/{cycle['goals'][1]['id']}", {"current_value": 1})) == "cycle_closed"
    assert (await player.get(path)).json()["report"] == report
    assert (await player.get("/cycles/current")).json() is None
    assert (await player.post("/cycles", {"title": "Next", "duration_days": 30})).status_code == 201


async def test_finishing_early_gives_no_reward(player: Player) -> None:
    cycle = await create_cycle(player, goals=[manual("A")])
    await player.patch(f"/cycles/{cycle['id']}/goals/{cycle['goals'][0]['id']}", {"current_value": 1})
    result = (await player.post(f"/cycles/{cycle['id']}/complete")).json()
    assert result["xp_awarded"] == 0
    assert result["cycle"]["finished_early"] is True
    assert result["cycle"]["report"]["goals_done"] == 1
    assert await player.total_xp() == 0


async def test_report_sums_up_the_period(player: Player, clock: Clock) -> None:
    cycle = await create_cycle(
        player,
        duration_days=7,
        goals=[{"title": "Workouts", "category": "health", "metric": "completions", "target_value": 2}],
    )
    workout = await player.create_quest(
        title="Workout", quest_type="daily", category="health", activity="workout", goal_id=cycle["goals"][0]["id"]
    )
    reading = (await player.post("/habits", {"title": "Read", "category": "learning"})).json()
    await player.complete(workout["id"])
    await player.post(f"/habits/{reading['id']}/complete")
    clock.advance(days=1)
    await player.complete(workout["id"])
    clock.advance(days=6)

    report = (await player.post(f"/cycles/{cycle['id']}/complete")).json()["cycle"]["report"]
    assert report["quests_completed"] == 2
    assert report["workouts"] == 2
    assert report["habit_checkins"] == 1
    assert report["active_days"] == 2
    assert report["xp_total"] == 30 + 15 + 30
    attributes = {a["attribute_type"]: a for a in report["attributes"]}
    assert attributes["health"]["xp_gained"] == 60
    assert attributes["intelligence"]["xp_gained"] == 15
    assert report["goals_done"] == 1
    assert report["cycle_xp"] == 200
    codes = [r["code"] for r in report["recommendations"]]
    assert "raise_bar" in codes
    assert "smaller_daily_plan" in codes  # active on 2 of 7 days


async def test_cancel(player: Player) -> None:
    cycle = await create_cycle(player)
    assert (await player.delete(f"/cycles/{cycle['id']}")).status_code == 204
    assert (await player.get("/cycles/current")).json() is None
    history = (await player.get("/cycles")).json()
    assert [(c["id"], c["status"]) for c in history] == [(cycle["id"], "cancelled")]
    assert (await player.post("/cycles", {"title": "Again", "duration_days": 30})).status_code == 201


async def test_goal_links_are_checked(make_player: PlayerFactory) -> None:
    alice, bob = await make_player(), await make_player()
    cycle = await create_cycle(alice, goals=[manual("A")])
    goal_id = cycle["goals"][0]["id"]
    foreign = await bob.post("/quests", {"title": "Steal", "quest_type": "personal", "category": "other", "goal_id": goal_id})
    assert foreign.status_code == 404
    assert code(foreign) == "goal_not_found"

    await alice.post(f"/cycles/{cycle['id']}/complete")
    closed = await alice.post("/habits", {"title": "Late", "category": "career", "goal_id": goal_id})
    assert code(closed) == "cycle_closed"


async def test_cycles_are_private(make_player: PlayerFactory) -> None:
    alice, bob = await make_player(), await make_player()
    cycle = await create_cycle(alice)
    path = f"/cycles/{cycle['id']}"
    assert (await bob.get(path)).status_code == 404
    assert (await bob.post(f"{path}/pause")).status_code == 404
    assert (await bob.post(f"{path}/complete")).status_code == 404
    assert (await bob.delete(path)).status_code == 404
    assert (await bob.get("/cycles")).json() == []


@pytest.fixture
async def achievements_on(db) -> AsyncIterator[None]:
    await db("UPDATE achievements SET is_active = true")
    yield
    await db("UPDATE achievements SET is_active = false")


async def test_first_cycle_achievement(player: Player, clock: Clock, achievements_on: None) -> None:
    cycle = await create_cycle(player, duration_days=7, goals=[manual("A")])
    await player.patch(f"/cycles/{cycle['id']}/goals/{cycle['goals'][0]['id']}", {"current_value": 1})
    clock.advance(days=7)
    result = (await player.post(f"/cycles/{cycle['id']}/complete")).json()
    assert result["xp_awarded"] == 200
    assert [a["code"] for a in result["achievements_unlocked"]] == ["first_cycle"]
    assert result["player"]["total_xp"] == 200 + 50
