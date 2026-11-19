from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import START, Clock, Player


def error_code(response) -> str:
    return response.json()["error"]["code"]


# --- creation --------------------------------------------------------------------------


async def test_reward_is_computed_by_the_server(player: Player) -> None:
    medium = await player.create_quest(title="Write report", category="career")
    assert medium["xp_reward"] == 20
    assert medium["attribute_types"] == ["career"]
    learning = await player.create_quest(
        title="DevOps", quest_type="daily", category="learning", activity="learning", target_minutes=60
    )
    assert learning["xp_reward"] == 25
    assert learning["attribute_types"] == ["intelligence"]
    assert learning["is_recurring"] is True

    cheat = await player.post("/quests", {"title": "Cheat", "quest_type": "personal", "category": "other", "xp_reward": 9999})
    assert cheat.status_code == 422


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"quest_type": "personal", "is_recurring": True}, "validation_error"),
        ({"quest_type": "daily", "activity": "learning"}, "validation_error"),
        ({"quest_type": "daily", "activity": "learning", "target_minutes": 20}, "target_minutes_too_small"),
        ({"quest_type": "daily", "activity": "learning", "target_minutes": 300}, "target_minutes_too_large"),
        ({"quest_type": "personal", "weekdays": [1]}, "validation_error"),
        ({"quest_type": "daily", "weekdays": [0, 8]}, "validation_error"),
    ],
)
async def test_invalid_quests_are_rejected(player: Player, body: dict, code: str) -> None:
    response = await player.post("/quests", {"title": "Bad", "category": "learning", **body})
    assert response.status_code == 422
    assert error_code(response) == code


# --- completion: spec scenarios 2, 3, 4, 6 -----------------------------------------------


async def test_completion_awards_xp_once(player: Player) -> None:
    """Spec scenarios 2 and 3."""
    quest = await player.create_quest(category="career", difficulty="hard")
    first = await player.complete(quest["id"])
    assert first.status_code == 200
    body = first.json()
    assert body["xp_awarded"] == 40
    assert body["quest"]["status"] == "completed"
    assert body["player"]["total_xp"] == 40

    again = await player.complete(quest["id"])
    assert again.status_code == 409
    assert error_code(again) == "already_completed"
    assert await player.total_xp() == 40
    assert (await player.attributes())["career"] == 40


async def test_level_up_at_threshold(player: Player) -> None:
    """Spec scenario 4: 100 XP is the threshold of level 2."""
    first = (await player.complete((await player.create_quest(difficulty="epic"))["id"])).json()
    assert first["xp_awarded"] == 100
    assert first["player"]["level"] == 2
    assert first["player"]["previous_level"] == 1
    assert first["player"]["leveled_up"] is True

    second = (await player.complete((await player.create_quest(difficulty="epic"))["id"])).json()
    assert second["player"]["total_xp"] == 200
    assert second["player"]["level"] == 2
    assert second["player"]["leveled_up"] is False
    assert second["player"]["xp_to_next_level"] == 183


async def test_skip_never_removes_xp(player: Player) -> None:
    """Spec scenario 6."""
    done = await player.create_quest(difficulty="medium")
    await player.complete(done["id"])
    skipped = await player.create_quest(difficulty="hard")

    response = await player.post(f"/quests/{skipped['id']}/skip")
    assert response.status_code == 200
    assert response.json()["quest"]["status"] == "skipped"
    assert await player.total_xp() == 20
    assert error_code(await player.post(f"/quests/{skipped['id']}/skip")) == "already_skipped"
    assert error_code(await player.post(f"/quests/{done['id']}/skip")) == "already_completed"

    # A skipped quest can still be done later.
    late = await player.complete(skipped["id"])
    assert late.status_code == 200
    assert await player.total_xp() == 60


# --- time windows ----------------------------------------------------------------------


async def test_daily_quest_repeats_every_day(player: Player, clock: Clock) -> None:
    quest = await player.create_quest(quest_type="daily", category="health", activity="workout")
    assert (await player.complete(quest["id"])).json()["xp_awarded"] == 30
    assert error_code(await player.complete(quest["id"])) == "already_completed"

    clock.advance(days=1)
    listed = (await player.get(f"/quests/{quest['id']}")).json()
    assert listed["status"] == "active"
    assert listed["current_occurrence_date"] == "2026-11-19"
    assert (await player.complete(quest["id"])).status_code == 200
    assert await player.total_xp() == 60

    detail = (await player.get(f"/quests/{quest['id']}")).json()
    assert [o["occurrence_date"] for o in detail["occurrences"]] == ["2026-11-19", "2026-11-18"]


async def test_daily_quest_respects_weekdays(player: Player) -> None:
    mondays = await player.create_quest(quest_type="daily", category="health", weekdays=[1])
    assert mondays["current_occurrence_date"] is None  # START is a Wednesday
    assert error_code(await player.complete(mondays["id"])) == "not_scheduled_today"


async def test_daily_quest_uses_local_date(make_player, clock: Clock) -> None:
    tokyo = await make_player(timezone="Asia/Tokyo")
    quest = await tokyo.create_quest(quest_type="daily", category="health")
    clock.now = datetime(2026, 11, 18, 14, 59, tzinfo=UTC)  # 23:59 in Tokyo
    assert (await tokyo.complete(quest["id"])).json()["occurrence"]["occurrence_date"] == "2026-11-18"
    clock.now = datetime(2026, 11, 18, 15, 1, tzinfo=UTC)  # 00:01 the next day in Tokyo
    assert (await tokyo.complete(quest["id"])).json()["occurrence"]["occurrence_date"] == "2026-11-19"


async def test_weekly_quest_once_per_iso_week(player: Player, clock: Clock) -> None:
    quest = await player.create_quest(quest_type="weekly", category="health")
    assert (await player.complete(quest["id"])).json()["xp_awarded"] == 100
    clock.advance(days=3)  # Saturday, same week
    assert error_code(await player.complete(quest["id"])) == "already_completed"
    clock.advance(days=2)  # Monday of the next week
    response = await player.complete(quest["id"])
    assert response.json()["occurrence"]["occurrence_date"] == "2026-11-23"


async def test_one_off_daily_quest_expires_after_its_day(player: Player, clock: Clock) -> None:
    quest = await player.create_quest(quest_type="daily", category="other", is_recurring=False)
    clock.advance(days=1)
    assert error_code(await player.complete(quest["id"])) == "quest_expired"
    assert (await player.get(f"/quests/{quest['id']}")).json()["status"] == "expired"


async def test_deadlines(player: Player, clock: Clock) -> None:
    due = (START + timedelta(hours=2)).isoformat()
    challenge = await player.create_quest(quest_type="challenge", difficulty="hard", due_at=due)
    personal = await player.create_quest(quest_type="personal", difficulty="hard", due_at=due)
    clock.advance(hours=3)
    assert error_code(await player.complete(challenge["id"])) == "quest_expired"
    # Personal quests may be finished late.
    assert (await player.complete(personal["id"])).status_code == 200


async def test_future_quest_is_pending(player: Player) -> None:
    quest = await player.create_quest(starts_at=(START + timedelta(days=1)).isoformat())
    assert quest["status"] == "pending"
    assert error_code(await player.complete(quest["id"])) == "quest_not_started"


# --- anti-farming --------------------------------------------------------------------


async def test_only_five_simple_tasks_per_day_give_xp(player: Player, clock: Clock) -> None:
    quests = [await player.create_quest(title=f"tiny {i}", difficulty="simple") for i in range(6)]
    results = [(await player.complete(q["id"])).json() for q in quests]
    assert [r["xp_awarded"] for r in results] == [10, 10, 10, 10, 10, 0]
    assert results[-1]["xp_limit_reason"] == "simple_task_daily_limit"

    clock.advance(days=1)
    tomorrow = await player.create_quest(title="tiny tomorrow", difficulty="simple")
    assert (await player.complete(tomorrow["id"])).json()["xp_awarded"] == 10


async def test_learning_minutes_are_capped_per_day(player: Player) -> None:
    def learning(minutes: int, title: str):
        return player.create_quest(
            title=title, quest_type="daily", category="learning", activity="learning", target_minutes=minutes
        )

    blocks = [await learning(60, f"block {i}") for i in range(3)]
    for quest in blocks:
        assert (await player.complete(quest["id"])).json()["xp_awarded"] == 25
    long_one = await learning(90, "long")  # only 60 of 90 minutes fit under 240
    partial = (await player.complete(long_one["id"])).json()
    assert partial["occurrence"]["minutes_credited"] == 60
    assert partial["xp_awarded"] == 25
    assert partial["xp_limit_reason"] == "learning_daily_cap"
    extra = (await player.complete((await learning(30, "extra"))["id"])).json()
    assert extra["xp_awarded"] == 0


async def test_xp_is_split_between_attributes(player: Player, db) -> None:
    quest = await player.create_quest(
        title="Terraform course", category="learning", attribute_types=["intelligence", "career"], difficulty="hard"
    )
    await player.complete(quest["id"])
    assert await player.attributes() == {"health": 0, "intelligence": 20, "career": 20, "finance": 0}
    rows = await db("SELECT attribute_type, xp_amount FROM xp_ledger ORDER BY attribute_type")
    assert [tuple(r) for r in rows] == [("career", 20), ("intelligence", 20)]


# --- undo, delete, edit ----------------------------------------------------------------


async def test_undo_on_the_same_day(player: Player, db) -> None:
    quest = await player.create_quest(category="finance", difficulty="epic")
    await player.complete(quest["id"])
    undo = await player.post(f"/quests/{quest['id']}/undo")
    assert undo.status_code == 200
    body = undo.json()
    assert body["xp_reverted"] == 100
    assert body["player"]["total_xp"] == 0
    assert body["player"]["level"] == 1
    assert body["quest"]["status"] == "active"
    assert (await player.attributes())["finance"] == 0

    rows = await db("SELECT xp_amount, reverses_id IS NOT NULL FROM xp_ledger ORDER BY xp_amount DESC")
    assert [tuple(r) for r in rows] == [(100, False), (-100, True)]
    assert error_code(await player.post(f"/quests/{quest['id']}/undo")) == "not_completed"

    # Completing again is a new event: XP is counted once in total.
    assert (await player.complete(quest["id"])).json()["xp_awarded"] == 100
    assert await player.total_xp() == 100


async def test_undo_is_not_possible_the_next_day(player: Player, clock: Clock) -> None:
    quest = await player.create_quest()
    await player.complete(quest["id"])
    clock.advance(days=1)
    assert error_code(await player.post(f"/quests/{quest['id']}/undo")) == "undo_window_expired"
    assert await player.total_xp() == 20


async def test_deleting_a_quest_keeps_its_xp(player: Player) -> None:
    quest = await player.create_quest(difficulty="hard")
    await player.complete(quest["id"])
    assert (await player.delete(f"/quests/{quest['id']}")).status_code == 204
    assert (await player.get(f"/quests/{quest['id']}")).status_code == 404
    assert (await player.get("/quests")).json()["total"] == 0
    assert await player.total_xp() == 40


async def test_only_descriptive_fields_can_be_edited(player: Player) -> None:
    quest = await player.create_quest(title="Old", difficulty="simple")
    edited = await player.patch(f"/quests/{quest['id']}", {"title": "New", "checklist": [{"title": "step 1"}]})
    assert edited.status_code == 200
    assert edited.json()["title"] == "New"
    assert edited.json()["checklist"] == [{"title": "step 1", "done": False}]
    assert (await player.patch(f"/quests/{quest['id']}", {"difficulty": "epic"})).status_code == 422
    assert (await player.patch(f"/quests/{quest['id']}", {"xp_reward": 500})).status_code == 422


async def test_today_scope(player: Player, clock: Clock) -> None:
    daily = await player.create_quest(title="daily", quest_type="daily", category="health")
    await player.create_quest(title="mondays", quest_type="daily", category="health", weekdays=[1])
    personal = await player.create_quest(title="personal")
    await player.complete(personal["id"])

    titles = {q["title"] for q in (await player.get("/quests", scope="today")).json()["items"]}
    assert titles == {"daily", "personal"}
    clock.advance(days=1)
    titles = {q["title"] for q in (await player.get("/quests", scope="today")).json()["items"]}
    assert titles == {"daily"}
    assert daily["id"] in {q["id"] for q in (await player.get("/quests", status="active")).json()["items"]}


# --- ledger integrity ------------------------------------------------------------------


async def test_ledger_is_append_only(player: Player, db) -> None:
    await player.complete((await player.create_quest())["id"])
    with pytest.raises(Exception, match="append-only"):
        await db("UPDATE xp_ledger SET xp_amount = 1000")
    with pytest.raises(Exception, match="append-only"):
        await db("DELETE FROM xp_ledger")


async def test_totals_match_the_ledger(player: Player, db) -> None:
    for difficulty, category in (("hard", "career"), ("simple", "other"), ("epic", "health")):
        await player.complete((await player.create_quest(difficulty=difficulty, category=category))["id"])
    undo_target = await player.create_quest(difficulty="medium", category="finance")
    await player.complete(undo_target["id"])
    await player.post(f"/quests/{undo_target['id']}/undo")

    ledger_total = (await db("SELECT coalesce(sum(xp_amount), 0) FROM xp_ledger"))[0][0]
    profile_total = (await db("SELECT total_xp FROM player_profiles"))[0][0]
    attribute_total = (await db("SELECT sum(total_xp) FROM attributes"))[0][0]
    unassigned = (await db("SELECT coalesce(sum(xp_amount), 0) FROM xp_ledger WHERE attribute_type IS NULL"))[0][0]
    assert ledger_total == profile_total == 150
    assert attribute_total + unassigned == ledger_total
