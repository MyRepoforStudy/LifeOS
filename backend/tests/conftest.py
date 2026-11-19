"""Integration tests run against a real PostgreSQL database (TEST_DATABASE_URL).

The schema is rebuilt with Alembic once per run; every test ends with TRUNCATE.
Business time comes from a controllable clock (the get_now dependency).
"""

import asyncio
import itertools
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import BACKEND_DIR, Settings
from app.deps import get_now
from app.main import create_app

API = "/api/v1"
# Wednesday; the ISO week starts on Monday 2026-11-16.
START = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
TABLES = (
    "users, refresh_tokens, player_profiles, attributes, xp_ledger, quests, quest_occurrences, idempotency_keys"
)


def _test_database_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or dotenv_values(BACKEND_DIR / ".env").get("TEST_DATABASE_URL")


async def _execute(url: str, *statements: str) -> None:
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.begin() as conn:
        for statement in statements:
            await conn.execute(text(statement))
    await engine.dispose()


@pytest.fixture(scope="session")
def database_url() -> str:
    url = _test_database_url()
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set; run scripts/devdb.ps1 init")
    database = make_url(url).database or ""
    if not database.endswith("_test"):
        pytest.exit(f"Refusing to wipe database {database!r}: the test database name must end with _test")
    asyncio.run(_execute(url, "DROP SCHEMA public CASCADE", "CREATE SCHEMA public"))
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["database_url"] = url
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")
    return url


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url=database_url,
        database_pool="null",
        jwt_secret="test-secret-that-is-long-enough-for-hs256",
        argon2_time_cost=1,
        argon2_memory_cost=1024,
        argon2_parallelism=1,
    )


@dataclass
class Clock:
    now: datetime = field(default_factory=lambda: START)

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
async def app(settings: Settings, clock: Clock) -> AsyncIterator[Any]:
    application = create_app(settings)
    application.dependency_overrides[get_now] = lambda: clock.now
    yield application
    await application.state.engine.dispose()
    await _execute(settings.database_url, f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")


@pytest.fixture
async def client(app: Any) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture
async def db(settings: Settings) -> AsyncIterator[Callable[..., Awaitable[Any]]]:
    """Run raw SQL against the test database: await db("SELECT ...", param=value)."""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)

    async def run(sql: str, **params: Any) -> Any:
        async with engine.begin() as conn:
            result = await conn.execute(text(sql), params)
            return result.all() if result.returns_rows else None

    yield run
    await engine.dispose()


@dataclass
class Player:
    client: AsyncClient
    access_token: str
    refresh_token: str
    email: str
    password: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    async def get(self, path: str, **params: Any) -> Response:
        return await self.client.get(API + path, headers=self.auth, params=params or None)

    async def post(self, path: str, json: Any = None, key: str | None = None) -> Response:
        headers = dict(self.auth)
        if key is not None:
            headers["Idempotency-Key"] = key
        return await self.client.post(API + path, json=json, headers=headers)

    async def patch(self, path: str, json: Any) -> Response:
        return await self.client.patch(API + path, json=json, headers=self.auth)

    async def delete(self, path: str) -> Response:
        return await self.client.delete(API + path, headers=self.auth)

    async def create_quest(self, **fields: Any) -> dict[str, Any]:
        body = {"title": "Quest", "quest_type": "personal", "category": "other", **fields}
        response = await self.post("/quests", body)
        assert response.status_code == 201, response.text
        return response.json()

    async def complete(self, quest_id: str, key: str | None = None) -> Response:
        return await self.post(f"/quests/{quest_id}/complete", key=key)

    async def profile(self) -> dict[str, Any]:
        response = await self.get("/player/profile")
        assert response.status_code == 200, response.text
        return response.json()

    async def total_xp(self) -> int:
        return (await self.profile())["total_xp"]

    async def attributes(self) -> dict[str, int]:
        response = await self.get("/player/attributes")
        assert response.status_code == 200, response.text
        return {a["attribute_type"]: a["total_xp"] for a in response.json()}


PlayerFactory = Callable[..., Awaitable[Player]]


@pytest.fixture
def make_player(client: AsyncClient) -> PlayerFactory:
    counter = itertools.count(1)

    async def factory(timezone: str = "UTC") -> Player:
        n = next(counter)
        email, password = f"player{n}@example.com", "correct horse battery staple"
        response = await client.post(
            f"{API}/auth/register",
            json={"email": email, "password": password, "display_name": f"Player {n}", "timezone": timezone},
        )
        assert response.status_code == 201, response.text
        tokens = response.json()
        return Player(client, tokens["access_token"], tokens["refresh_token"], email, password)

    return factory


@pytest.fixture
async def player(make_player: PlayerFactory) -> Player:
    return await make_player()
