"""The API process serves the built web client (production mode)."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
async def web(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>LifeOS</title>", encoding="utf-8")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "sw.js").write_text("self.addEventListener('fetch', () => {})", encoding="utf-8")
    (dist / "manifest.webmanifest").write_text("{}", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("do not serve", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://unused:unused@localhost:1/unused",
        jwt_secret="test-secret-that-is-long-enough-for-hs256",
        web_dist_dir=dist,
    )
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    await app.state.engine.dispose()


async def test_index_and_client_routes(web: AsyncClient) -> None:
    for path in ("/", "/quests/123", "/habits"):
        response = await web.get(path)
        assert response.status_code == 200
        assert "<title>LifeOS</title>" in response.text
        assert response.headers["cache-control"] == "no-cache"


async def test_assets_are_cached_and_typed(web: AsyncClient) -> None:
    asset = await web.get("/assets/index-abc123.js")
    assert asset.status_code == 200
    assert asset.headers["content-type"].startswith("text/javascript")
    assert "immutable" in asset.headers["cache-control"]
    worker = await web.get("/sw.js")
    assert worker.headers["cache-control"] == "no-cache"
    manifest = await web.get("/manifest.webmanifest")
    assert manifest.headers["content-type"].startswith("application/manifest+json")


async def test_api_paths_are_not_swallowed(web: AsyncClient) -> None:
    missing = await web.get("/api/v1/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    levels = await web.get("/openapi.json")
    assert levels.status_code == 200
    assert "paths" in levels.json()


async def test_files_outside_the_build_are_not_served(web: AsyncClient) -> None:
    response = await web.get("/../secret.txt")
    assert "do not serve" not in response.text
    encoded = await web.get("/%2e%2e/secret.txt")
    assert "do not serve" not in encoded.text
