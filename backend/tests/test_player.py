from datetime import UTC, datetime

from httpx import AsyncClient

from tests.conftest import API, Clock, Player


async def test_new_profile_starts_at_level_1_with_0_xp(player: Player) -> None:
    """Spec scenario 1."""
    profile = await player.profile()
    assert profile["level"] == 1
    assert profile["total_xp"] == 0
    assert profile["xp_in_level"] == 0
    assert profile["xp_to_next_level"] == 100
    assert profile["active_quests"] == 0
    assert profile["completed_quests"] == 0

    attributes = (await player.get("/player/attributes")).json()
    assert [a["attribute_type"] for a in attributes] == ["health", "intelligence", "career", "finance"]
    assert all(a["total_xp"] == 0 and a["level"] == 1 for a in attributes)


async def test_timezone_change_starts_at_next_local_midnight(player: Player, clock: Clock) -> None:
    response = await player.patch("/player/profile", {"timezone": "Asia/Tokyo"})
    assert response.status_code == 200
    body = response.json()
    assert body["timezone"] == "UTC"
    assert body["pending_timezone"] == "Asia/Tokyo"
    assert datetime.fromisoformat(body["pending_timezone_from"]) == datetime(2026, 11, 19, tzinfo=UTC)

    clock.now = datetime(2026, 11, 19, 0, 0, 1, tzinfo=UTC)
    profile = await player.profile()
    assert profile["timezone"] == "Asia/Tokyo"
    assert profile["pending_timezone"] is None


async def test_profile_update(player: Player) -> None:
    response = await player.patch(
        "/player/profile",
        {"display_name": "  Neo  ", "avatar_url": "https://example.com/a.png", "development_started_on": "2026-01-01"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Neo"
    assert body["avatar_url"] == "https://example.com/a.png"
    assert body["development_started_on"] == "2026-01-01"
    assert (await player.patch("/player/profile", {"timezone": "Nowhere/City"})).status_code == 422
    assert (await player.patch("/player/profile", {"total_xp": 1_000_000})).status_code == 422


async def test_xp_history_is_newest_first_and_paginated(player: Player, clock: Clock) -> None:
    for title in ("first", "second", "third"):
        quest = await player.create_quest(title=title)
        assert (await player.complete(quest["id"])).status_code == 200
        clock.advance(minutes=1)

    page = (await player.get("/player/xp-history", limit=2)).json()
    assert [item["description"] for item in page["items"]] == ["third", "second"]
    assert page["next_offset"] == 2
    rest = (await player.get("/player/xp-history", limit=2, offset=2)).json()
    assert [item["description"] for item in rest["items"]] == ["first"]
    assert rest["next_offset"] is None


async def test_statistics_group_xp_by_local_day(player: Player, clock: Clock) -> None:
    quest = await player.create_quest(quest_type="daily", category="learning", activity="learning", target_minutes=60)
    assert (await player.complete(quest["id"])).status_code == 200
    clock.advance(days=1)
    assert (await player.complete(quest["id"])).status_code == 200

    stats = (await player.get("/player/statistics", date_from="2026-11-17", date_to="2026-11-19")).json()
    assert stats["total_xp"] == 50
    assert stats["quests_completed"] == 2
    assert stats["xp_by_day"] == [
        {"date": "2026-11-17", "xp": 0},
        {"date": "2026-11-18", "xp": 25},
        {"date": "2026-11-19", "xp": 25},
    ]
    assert stats["xp_by_attribute"] == {"intelligence": 50}
    too_long = await player.get("/player/statistics", date_from="2024-01-01", date_to="2026-01-01")
    assert too_long.status_code == 422


async def test_level_table_comes_from_the_server(client: AsyncClient) -> None:
    table = (await client.get(f"{API}/config/levels", params={"up_to": 20})).json()
    rows = {row["level"]: row for row in table["levels"]}
    assert rows[1]["xp_to_next_level"] == 100
    assert rows[10]["xp_to_next_level"] == 3162
    assert rows[10]["total_xp_required"] == 11106
    assert rows[20]["total_xp_required"] == 67135
    rewards = (await client.get(f"{API}/config/rewards")).json()
    assert rewards["task_medium"] == 20
