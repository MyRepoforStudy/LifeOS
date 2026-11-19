from fastapi import APIRouter

from app.routers import achievements, auth, config, habits, player, quests

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(player.router)
api_router.include_router(quests.router)
api_router.include_router(habits.router)
api_router.include_router(achievements.router)
api_router.include_router(config.router)
