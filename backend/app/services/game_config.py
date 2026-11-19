from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.levels import LevelCurve
from app.domain.rewards import RewardRules
from app.models import GameConfig

REWARDS_KEY = "rewards"
LEVEL_CURVE_KEY = "level_curve"


@dataclass(frozen=True)
class GameSettings:
    rewards: RewardRules
    level_curve: LevelCurve


async def load_game_settings(session: AsyncSession) -> GameSettings:
    """Balance settings from the game_config table; missing keys fall back to defaults."""
    rows = (await session.execute(select(GameConfig))).scalars().all()
    values = {row.key: row.value for row in rows}
    return GameSettings(
        rewards=RewardRules(**values.get(REWARDS_KEY, {})),
        level_curve=LevelCurve(**values.get(LEVEL_CURVE_KEY, {})),
    )
