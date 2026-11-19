"""Spec scenario 11: a retry after a network error does not create duplicate events."""

import uuid

from tests.conftest import Player, PlayerFactory


async def test_retry_with_the_same_key_replays_the_response(player: Player, db) -> None:
    quest = await player.create_quest(difficulty="hard")
    key = str(uuid.uuid4())

    first = await player.complete(quest["id"], key=key)
    retry = await player.complete(quest["id"], key=key)
    assert first.status_code == retry.status_code == 200
    assert retry.headers.get("Idempotent-Replayed") == "true"
    assert retry.json() == first.json()
    assert await player.total_xp() == 40
    assert (await db("SELECT count(*) FROM xp_ledger"))[0][0] == 1


async def test_key_cannot_be_reused_for_another_request(player: Player) -> None:
    one = await player.create_quest()
    two = await player.create_quest()
    key = "same-key"
    assert (await player.complete(one["id"], key=key)).status_code == 200
    reused = await player.complete(two["id"], key=key)
    assert reused.status_code == 422
    assert reused.json()["error"]["code"] == "idempotency_key_reused"


async def test_create_retry_does_not_duplicate_the_quest(player: Player) -> None:
    body = {"title": "Read 20 pages", "quest_type": "daily", "category": "learning"}
    first = await player.post("/quests", body, key="create-1")
    retry = await player.post("/quests", body, key="create-1")
    assert first.status_code == retry.status_code == 201
    assert retry.json()["id"] == first.json()["id"]
    assert (await player.get("/quests")).json()["total"] == 1


async def test_failed_request_does_not_burn_the_key(player: Player) -> None:
    quest = await player.create_quest()
    assert (await player.complete(quest["id"])).status_code == 200
    # Fails (already completed): nothing is stored under the key.
    assert (await player.complete(quest["id"], key="k")).status_code == 409
    assert (await player.post(f"/quests/{quest['id']}/undo")).status_code == 200
    assert (await player.complete(quest["id"], key="k")).status_code == 200


async def test_keys_belong_to_one_user(make_player: PlayerFactory) -> None:
    alice, bob = await make_player(), await make_player()
    alice_quest, bob_quest = await alice.create_quest(), await bob.create_quest()
    assert (await alice.complete(alice_quest["id"], key="shared")).status_code == 200
    bob_result = await bob.complete(bob_quest["id"], key="shared")
    assert bob_result.status_code == 200
    assert bob_result.headers.get("Idempotent-Replayed") is None
