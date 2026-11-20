"""Adaptive Engine (spec section 11, scenario 9: a recommendation needs the player's consent)."""

from typing import Any

from tests.conftest import Clock, Player, PlayerFactory


def code(response) -> str:
    return response.json()["error"]["code"]


async def recommendations(player: Player) -> list[dict[str, Any]]:
    response = await player.get("/adaptive/recommendations")
    assert response.status_code == 200, response.text
    return response.json()


def pending(items: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    return next((r for r in items if r["status"] == "pending" and r["recommendation_type"] == kind), None)


async def overloaded_week(player: Player, clock: Clock) -> dict[str, Any]:
    """Wed 18 .. Tue 24 Nov: 7 of 19 planned units done; today is Wed 25."""
    task = await player.create_quest(title="Inbox zero", quest_type="daily")
    learning = await player.create_quest(
        title="Kubernetes", quest_type="daily", category="learning", activity="learning", target_minutes=60
    )
    optional = await player.create_quest(title="Tidy the garage", priority=1, due_at="2026-11-27T12:00:00Z")
    habit = (await player.post("/habits", {"title": "Stretching", "category": "health"})).json()

    async def day(*, task_done=False, learning_done=False, learning_skipped=False, habit_done=False) -> None:
        if task_done:
            assert (await player.complete(task["id"])).status_code == 200
        if learning_done:
            assert (await player.complete(learning["id"])).status_code == 200
        if learning_skipped:
            assert (await player.post(f"/quests/{learning['id']}/skip")).status_code == 200
        if habit_done:
            assert (await player.post(f"/habits/{habit['id']}/complete")).status_code == 200
        clock.advance(days=1)

    await day(task_done=True)  # Wed 18: the day of creation counts only for what was done
    await day(task_done=True, learning_done=True, habit_done=True)  # Thu 19
    await day(task_done=True, learning_skipped=True)  # Fri 20
    await day()  # Sat 21
    await day(habit_done=True)  # Sun 22
    await day()  # Mon 23
    await day(task_done=True)  # Tue 24
    return {"task": task, "learning": learning, "optional": optional, "habit": habit}


async def test_fresh_player_has_no_plan_and_no_advice(player: Player) -> None:
    summary = (await player.get("/adaptive/summary")).json()
    assert summary["week"]["planned"] == 0
    assert summary["week"]["rate"] is None
    assert summary["struggling"] == []
    assert await recommendations(player) == []


async def test_analysis_compares_the_plan_with_what_was_done(player: Player, clock: Clock) -> None:
    await overloaded_week(player, clock)
    summary = (await player.get("/adaptive/summary")).json()
    week = summary["week"]
    assert (week["first_day"], week["last_day"]) == ("2026-11-18", "2026-11-24")
    # Inbox zero 4 of 7, Kubernetes 1 of 6 (+1 skipped), Stretching 2 of 6.
    assert (week["planned"], week["done"], week["skipped"]) == (19, 7, 1)
    assert week["rate"] == round(7 / 19, 4)
    assert (week["quests_planned"], week["quests_done"]) == (13, 5)
    assert (week["habits_planned"], week["habits_done"]) == (6, 2)
    assert (week["learning_minutes_planned"], week["learning_minutes_done"]) == (360, 60)
    assert week["active_days"] == 5  # 18, 19, 20, 22, 24
    assert week["xp"] == await player.total_xp()
    categories = {c["category"]: (c["planned"], c["done"]) for c in week["categories"]}
    assert categories == {"learning": (6, 1), "health": (6, 2), "other": (7, 4)}
    assert summary["previous_week_rate"] is None  # nothing was planned before 18 Nov
    assert [item["title"] for item in summary["struggling"]] == ["Kubernetes", "Stretching"]


async def test_overload_is_only_a_suggestion_until_applied(player: Player, clock: Clock) -> None:
    created = await overloaded_week(player, clock)
    advice = pending(await recommendations(player), "overload")
    assert advice is not None
    assert advice["params"] == {"done": 7, "planned": 19, "rate": 37, "focus": "learning"}
    ops = [(c["op"], c["title"]) for c in advice["changes"]]
    assert ops == [
        ("quest_minutes", "Kubernetes"),
        ("habit_schedule", "Stretching"),
        ("quest_due", "Tidy the garage"),
    ]
    minutes, schedule, due = advice["changes"]
    assert (minutes["from_minutes"], minutes["to_minutes"]) == (60, 30)
    assert minutes["to_xp"] < minutes["from_xp"]
    assert (schedule["from_frequency"], schedule["to_times_per_week"]) == ("daily", 3)
    assert due["to_due"].startswith("2026-12-04T12:00:00")

    # Scenario 9: asking for advice changed nothing in the plan.
    learning = (await player.get(f"/quests/{created['learning']['id']}")).json()
    assert learning["target_minutes"] == 60
    assert (await recommendations(player))[0]["id"] == advice["id"]  # the same advice, not a new one

    # Apply only the first and the last change.
    path = f"/adaptive/recommendations/{advice['id']}/apply"
    response = await player.post(path, {"changes": [0, 2]}, key="apply-1")
    assert response.status_code == 200, response.text
    assert response.json()["applied"] == 2
    assert response.json()["recommendation"]["status"] == "applied"
    replay = await player.post(path, {"changes": [0, 2]}, key="apply-1")
    assert replay.headers.get("Idempotent-Replayed") == "true"

    learning = (await player.get(f"/quests/{created['learning']['id']}")).json()
    assert learning["target_minutes"] == 30
    assert learning["xp_reward"] == minutes["to_xp"]
    optional = (await player.get(f"/quests/{created['optional']['id']}")).json()
    assert optional["due_at"].startswith("2026-12-04T12:00:00")
    habits = (await player.get("/habits")).json()
    assert [(h["title"], h["frequency"]) for h in habits] == [("Stretching", "daily")]
    # The new plan starts today: the past week keeps the plan it had.
    week = (await player.get("/adaptive/summary")).json()["week"]
    assert (week["planned"], week["learning_minutes_planned"]) == (19, 360)

    assert code(await player.post(path, {"changes": [1]})) == "recommendation_closed"
    # An applied subject rests: the same advice does not come back at once.
    assert pending(await recommendations(player), "overload") is None


async def test_dismissed_advice_rests_for_a_week(player: Player, clock: Clock) -> None:
    created = await overloaded_week(player, clock)
    advice = pending(await recommendations(player), "overload")
    assert advice is not None
    dismissed = await player.post(f"/adaptive/recommendations/{advice['id']}/dismiss")
    assert dismissed.json()["status"] == "dismissed"
    assert (await player.get(f"/quests/{created['learning']['id']}")).json()["target_minutes"] == 60
    assert pending(await recommendations(player), "overload") is None

    clock.advance(days=8)  # another week with nothing done
    again = pending(await recommendations(player), "overload")
    assert again is not None
    assert again["id"] != advice["id"]


async def test_outdated_advice_changes_nothing(player: Player, clock: Clock) -> None:
    created = await overloaded_week(player, clock)
    advice = pending(await recommendations(player), "overload")
    assert advice is not None
    await player.delete(f"/quests/{created['learning']['id']}")

    response = await player.post(f"/adaptive/recommendations/{advice['id']}/apply")
    assert response.status_code == 409
    assert code(response) == "recommendation_outdated"
    habits = (await player.get("/habits")).json()
    assert habits[0]["frequency"] == "daily"  # all or nothing

    # Deleting keeps the past in the numbers but takes the quest off the struggling list.
    summary = (await player.get("/adaptive/summary")).json()
    assert summary["week"]["planned"] == 19
    assert [item["title"] for item in summary["struggling"]] == ["Stretching"]

    # The next look replaces it with advice that fits the plan as it is now.
    items = await recommendations(player)
    assert next(r for r in items if r["id"] == advice["id"])["status"] == "expired"
    fresh = pending(items, "overload")
    assert fresh is not None
    assert [c["op"] for c in fresh["changes"]] == ["habit_schedule", "quest_due"]


async def test_a_steady_plan_can_ask_for_more(player: Player, clock: Clock) -> None:
    quest = await player.create_quest(
        title="English", quest_type="daily", category="learning", activity="learning", target_minutes=60
    )
    for _ in range(14):
        assert (await player.complete(quest["id"])).status_code == 200
        clock.advance(days=1)

    summary = (await player.get("/adaptive/summary")).json()
    assert summary["previous_week_rate"] == 1.0  # a full week to compare with

    advice = pending(await recommendations(player), "too_easy")
    assert advice is not None
    assert advice["params"]["rate"] == 100
    change = advice["changes"][0]
    assert (change["op"], change["from_minutes"], change["to_minutes"]) == ("quest_minutes", 60, 90)

    applied = await player.post(f"/adaptive/recommendations/{advice['id']}/apply")
    assert applied.status_code == 200, applied.text
    updated = (await player.get(f"/quests/{quest['id']}")).json()
    assert updated["target_minutes"] == 90
    assert updated["xp_reward"] == change["to_xp"] > change["from_xp"]


async def test_a_quiet_stretch_offers_to_pause_the_cycle(player: Player, clock: Clock) -> None:
    cycle = (await player.post("/cycles", {"title": "Autumn", "duration_days": 30})).json()
    quest = await player.create_quest(title="Walk", quest_type="daily", category="health")
    for _ in range(6):
        await player.complete(quest["id"])
        clock.advance(days=1)
    clock.advance(days=3)  # three quiet days

    advice = pending(await recommendations(player), "rest")
    assert advice is not None
    assert advice["params"] == {"days": 3, "cycle": "Autumn"}
    assert advice["changes"] == [{"op": "cycle_pause", "cycle_id": cycle["id"], "title": "Autumn"}]
    assert pending(await recommendations(player), "overload") is None

    assert (await player.post(f"/adaptive/recommendations/{advice['id']}/apply")).status_code == 200
    assert (await player.get("/cycles/current")).json()["status"] == "paused"


async def test_a_habit_that_keeps_slipping_gets_a_lighter_schedule(player: Player, clock: Clock) -> None:
    quest = await player.create_quest(title="Plan the day", quest_type="daily")
    habit = (await player.post("/habits", {"title": "Meditate", "category": "health"})).json()
    for day in range(14):
        await player.complete(quest["id"])
        if day == 3:
            await player.post(f"/habits/{habit['id']}/complete")
        clock.advance(days=1)

    items = await recommendations(player)
    assert pending(items, "overload") is None
    advice = pending(items, "stalled_item")
    assert advice is not None
    assert advice["params"] == {"title": "Meditate", "kind": "habit", "done": 1, "planned": 13}
    assert advice["changes"][0]["to_times_per_week"] == 3

    assert (await player.post(f"/adaptive/recommendations/{advice['id']}/apply")).status_code == 200
    active = (await player.get("/habits")).json()
    assert [(h["title"], h["frequency"], h["times_per_week"]) for h in active] == [("Meditate", "weekly", 3)]
    archived = (await player.get("/habits", include_archived="true")).json()
    assert {h["id"]: h["is_active"] for h in archived}[habit["id"]] is False


async def test_recommendations_are_private(make_player: PlayerFactory, clock: Clock) -> None:
    alice, bob = await make_player(), await make_player()
    await overloaded_week(alice, clock)
    advice = pending(await recommendations(alice), "overload")
    assert advice is not None
    assert await recommendations(bob) == []
    for action in ("apply", "dismiss"):
        response = await bob.post(f"/adaptive/recommendations/{advice['id']}/{action}")
        assert response.status_code == 404
        assert code(response) == "recommendation_not_found"
    assert pending(await recommendations(alice), "overload") is not None


async def test_invalid_choice_of_changes(player: Player, clock: Clock) -> None:
    await overloaded_week(player, clock)
    advice = pending(await recommendations(player), "overload")
    assert advice is not None
    path = f"/adaptive/recommendations/{advice['id']}/apply"
    assert code(await player.post(path, {"changes": [7]})) == "invalid_changes"
    assert code(await player.post(path, {"changes": [0, 0]})) == "invalid_changes"
    assert code(await player.post(path, {"changes": []})) == "invalid_changes"
    assert (await player.post(path, {"changes": [-1]})).status_code == 422


async def test_weekly_plans_count_once_per_week(player: Player, clock: Clock) -> None:
    review = await player.create_quest(title="Weekly review", quest_type="weekly")
    run = (
        await player.post("/habits", {"title": "Run", "category": "health", "frequency": "weekly", "times_per_week": 3})
    ).json()

    async def run_today() -> None:
        assert (await player.post(f"/habits/{run['id']}/complete")).status_code == 200

    clock.advance(days=1)  # Thu 19
    await run_today()
    clock.advance(days=1)  # Fri 20
    await run_today()
    assert (await player.complete(review["id"])).status_code == 200
    clock.advance(days=4)  # Tue 24 ... Thu 26: three runs, no review this week
    for _ in range(3):
        await run_today()
        clock.advance(days=1)
    clock.advance(days=5)  # Wed 2 Dec

    summary = (await player.get("/adaptive/summary")).json()
    # The week of 23-29 Nov: the review missed, 3 of 3 runs.
    week = summary["week"]
    assert (week["planned"], week["done"]) == (4, 3)
    assert (week["habits_planned"], week["habits_done"]) == (3, 3)
    # The first week counts for the review (it was done) but not for the runs (2 of 3
    # in a week that started on a Wednesday).
    month = summary["month"]
    assert (month["planned"], month["done"]) == (5, 4)


async def test_a_new_schedule_does_not_rewrite_the_past(player: Player, clock: Clock) -> None:
    quest = await player.create_quest(title="Swim", quest_type="daily", category="health")
    for day in range(8):
        if day % 2 == 0:
            await player.complete(quest["id"])
        clock.advance(days=1)
    before = (await player.get("/adaptive/summary")).json()["week"]

    updated = await player.patch(f"/quests/{quest['id']}", {"weekdays": [6, 7]})
    assert updated.status_code == 200, updated.text
    await player.patch(f"/quests/{quest['id']}", {"weekdays": [6]})  # a second change the same day
    after = (await player.get("/adaptive/summary")).json()["week"]
    assert (after["planned"], after["done"]) == (before["planned"], before["done"]) == (7, 3)

    clock.advance(days=7)  # a week later only Saturdays are planned
    week = (await player.get("/adaptive/summary")).json()["week"]
    assert week["planned"] == 1
