"""ASGI entry point: uvicorn app.main:create_app --factory"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import Settings, get_settings
from app.db import create_engine, create_sessionmaker
from app.errors import install_error_handlers
from app.routers import api_router
from app.security import Passwords
from app.web import mount_web


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = create_engine(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()

    app = FastAPI(
        title="LifeOS RPG API",
        version="0.1.0",
        description="XP ledger, levels and quests of LifeOS RPG.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = create_sessionmaker(engine)
    app.state.passwords = Passwords(settings)

    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Idempotent-Replayed"],
    )
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        async with app.state.sessionmaker() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok"}

    # Last: the catch-all route of the web client must not shadow API routes.
    mount_web(app, settings.web_dist_dir)
    return app
