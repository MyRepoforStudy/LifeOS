from httpx import AsyncClient

from tests.conftest import API, Clock, Player, PlayerFactory


async def test_register_returns_tokens(client: AsyncClient) -> None:
    response = await client.post(
        f"{API}/auth/register",
        json={"email": "Hero@Example.com", "password": "long enough pass", "display_name": "Hero"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]


async def test_email_is_unique_case_insensitive(client: AsyncClient, player: Player) -> None:
    response = await client.post(
        f"{API}/auth/register",
        json={"email": player.email.upper(), "password": "another password", "display_name": "Twin"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


async def test_register_validates_input(client: AsyncClient) -> None:
    short = await client.post(f"{API}/auth/register", json={"email": "a@example.com", "password": "short", "display_name": "A"})
    assert short.status_code == 422
    zone = await client.post(
        f"{API}/auth/register",
        json={"email": "b@example.com", "password": "long enough pass", "display_name": "B", "timezone": "Mars/Base"},
    )
    assert zone.status_code == 422


async def test_login(client: AsyncClient, player: Player) -> None:
    ok = await client.post(f"{API}/auth/login", json={"email": player.email, "password": player.password})
    assert ok.status_code == 200
    wrong = await client.post(f"{API}/auth/login", json={"email": player.email, "password": "wrong password"})
    unknown = await client.post(f"{API}/auth/login", json={"email": "nobody@example.com", "password": "whatever"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["code"] == unknown.json()["error"]["code"] == "invalid_credentials"


async def test_protected_endpoints_need_a_valid_token(client: AsyncClient) -> None:
    assert (await client.get(f"{API}/player/profile")).status_code == 401
    bad = await client.get(f"{API}/player/profile", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_token"


async def test_refresh_rotation_and_reuse_detection(client: AsyncClient, player: Player) -> None:
    first = await client.post(f"{API}/auth/refresh", json={"refresh_token": player.refresh_token})
    assert first.status_code == 200
    rotated = first.json()["refresh_token"]
    assert rotated != player.refresh_token

    # The old token was rotated: presenting it again revokes the whole family.
    reused = await client.post(f"{API}/auth/refresh", json={"refresh_token": player.refresh_token})
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "refresh_token_reused"
    after = await client.post(f"{API}/auth/refresh", json={"refresh_token": rotated})
    assert after.status_code == 401


async def test_logout_revokes_refresh_token(client: AsyncClient, player: Player) -> None:
    assert (await client.post(f"{API}/auth/logout", json={"refresh_token": player.refresh_token})).status_code == 204
    response = await client.post(f"{API}/auth/refresh", json={"refresh_token": player.refresh_token})
    assert response.status_code == 401


async def test_refresh_token_expires(client: AsyncClient, player: Player, clock: Clock) -> None:
    clock.advance(days=31)
    response = await client.post(f"{API}/auth/refresh", json={"refresh_token": player.refresh_token})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "refresh_token_expired"


async def test_delete_account_removes_all_data(client: AsyncClient, make_player: PlayerFactory, db) -> None:
    hero = await make_player()
    quest = await hero.create_quest(difficulty="hard")
    assert (await hero.complete(quest["id"])).status_code == 200

    wrong = await hero.post("/account/delete", {"password": "not my password"})
    assert wrong.status_code == 401
    assert (await hero.post("/account/delete", {"password": hero.password})).status_code == 204

    login = await client.post(f"{API}/auth/login", json={"email": hero.email, "password": hero.password})
    assert login.status_code == 401
    for table in ("users", "player_profiles", "attributes", "xp_ledger", "quests", "quest_occurrences"):
        assert (await db(f"SELECT count(*) FROM {table}"))[0][0] == 0, table
