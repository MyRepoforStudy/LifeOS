"""Spec scenario 10: one user cannot read or change another user's data."""

from tests.conftest import PlayerFactory


async def test_users_cannot_touch_each_others_quests(make_player: PlayerFactory) -> None:
    alice = await make_player()
    bob = await make_player()
    quest = await alice.create_quest(title="Alice's secret", difficulty="hard")
    path = f"/quests/{quest['id']}"

    assert (await bob.get(path)).status_code == 404
    assert (await bob.patch(path, {"title": "hacked"})).status_code == 404
    assert (await bob.complete(quest["id"])).status_code == 404
    assert (await bob.post(f"{path}/skip")).status_code == 404
    assert (await bob.post(f"{path}/undo")).status_code == 404
    assert (await bob.delete(path)).status_code == 404

    assert (await bob.get("/quests")).json()["total"] == 0
    assert await bob.total_xp() == 0

    # Alice's quest is untouched and still hers to complete.
    assert (await alice.get(path)).json()["title"] == "Alice's secret"
    assert (await alice.complete(quest["id"])).status_code == 200
    assert (await bob.get("/player/xp-history")).json()["items"] == []
    assert (await alice.get("/player/xp-history")).json()["items"][0]["xp_amount"] == 40
