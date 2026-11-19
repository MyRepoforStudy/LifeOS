from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import SessionDep
from app.domain.levels import total_xp_for_level, xp_to_next_level
from app.domain.rewards import RewardRules
from app.schemas import LevelRowOut, LevelTableOut
from app.services.game_config import load_game_settings

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/levels", response_model=LevelTableOut)
async def get_levels(session: SessionDep, up_to: Annotated[int, Query(ge=1, le=200)] = 50) -> LevelTableOut:
    """The level table, generated on the server from the current curve."""
    async with session.begin():
        curve = (await load_game_settings(session)).level_curve
    up_to = min(up_to, curve.max_level - 1)
    return LevelTableOut(
        base=curve.base,
        exponent=curve.exponent,
        levels=[
            LevelRowOut(
                level=level,
                xp_to_next_level=xp_to_next_level(level, curve),
                total_xp_required=total_xp_for_level(level, curve),
            )
            for level in range(1, up_to + 1)
        ],
    )


@router.get("/rewards", response_model=RewardRules)
async def get_rewards(session: SessionDep) -> RewardRules:
    async with session.begin():
        return (await load_game_settings(session)).rewards
