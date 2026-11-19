from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import CurrentUser, NowDep, SessionDep
from app.schemas import AttributeOut, ProfileOut, ProfileUpdateIn, StatisticsOut, XpHistoryOut
from app.services import player as player_service
from app.services.game_config import load_game_settings

router = APIRouter(prefix="/player", tags=["player"])


@router.get("/profile", response_model=ProfileOut)
async def get_profile(user: CurrentUser, session: SessionDep, now: NowDep) -> ProfileOut:
    async with session.begin():
        game = await load_game_settings(session)
        return await player_service.get_profile(session, user, now, game.level_curve)


@router.patch("/profile", response_model=ProfileOut)
async def update_profile(data: ProfileUpdateIn, user: CurrentUser, session: SessionDep, now: NowDep) -> ProfileOut:
    """A new time zone takes effect at the next local midnight."""
    async with session.begin():
        await player_service.update_profile(session, user, data, now)
        game = await load_game_settings(session)
        return await player_service.get_profile(session, user, now, game.level_curve)


@router.get("/attributes", response_model=list[AttributeOut])
async def get_attributes(user: CurrentUser, session: SessionDep, now: NowDep) -> list[AttributeOut]:
    async with session.begin():
        game = await load_game_settings(session)
        return await player_service.get_attributes(session, user, now, game.level_curve)


@router.get("/xp-history", response_model=XpHistoryOut)
async def get_xp_history(
    user: CurrentUser,
    session: SessionDep,
    now: NowDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    date_from: date | None = None,
    date_to: date | None = None,
) -> XpHistoryOut:
    async with session.begin():
        return await player_service.xp_history(
            session, user, now, limit=limit, offset=offset, date_from=date_from, date_to=date_to
        )


@router.get("/statistics", response_model=StatisticsOut)
async def get_statistics(
    user: CurrentUser,
    session: SessionDep,
    now: NowDep,
    date_from: date | None = None,
    date_to: date | None = None,
) -> StatisticsOut:
    """XP by local day and by attribute for a period (default: the last 30 days)."""
    async with session.begin():
        return await player_service.statistics(session, user, now, date_from=date_from, date_to=date_to)
