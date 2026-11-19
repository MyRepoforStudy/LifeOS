from fastapi import APIRouter

from app.deps import CurrentUser, NowDep, SessionDep
from app.schemas import AchievementOut
from app.services import achievements as achievement_service

router = APIRouter(prefix="/achievements", tags=["achievements"])


@router.get("", response_model=list[AchievementOut])
async def list_achievements(user: CurrentUser, session: SessionDep, now: NowDep) -> list[AchievementOut]:
    """The whole catalog with the player's progress; unlocked ones carry unlocked_at."""
    async with session.begin():
        return await achievement_service.list_achievements(session, user, now)


@router.get("/unlocked", response_model=list[AchievementOut])
async def list_unlocked(user: CurrentUser, session: SessionDep, now: NowDep) -> list[AchievementOut]:
    """Unlocked achievements, the most recent first."""
    async with session.begin():
        items = await achievement_service.list_achievements(session, user, now)
    unlocked = [item for item in items if item.unlocked_at is not None]
    return sorted(unlocked, key=lambda item: item.unlocked_at or now, reverse=True)
