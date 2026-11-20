import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse

from app.deps import CurrentUser, NowDep, SessionDep
from app.idempotency import run_idempotent
from app.schemas import (
    AdaptiveRecommendationOut,
    AnalysisOut,
    RecommendationApplyIn,
    RecommendationApplyOut,
)
from app.services import adaptive as adaptive_service
from app.services.game_config import load_game_settings

router = APIRouter(prefix="/adaptive", tags=["adaptive"])

IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]


@router.get("/summary", response_model=AnalysisOut)
async def summary(user: CurrentUser, session: SessionDep, now: NowDep) -> AnalysisOut:
    """Plan against reality for the last 7 and 30 complete days (today is still open)."""
    async with session.begin():
        return await adaptive_service.get_analysis(session, user, now)


@router.get("/recommendations", response_model=list[AdaptiveRecommendationOut])
async def list_recommendations(
    user: CurrentUser, session: SessionDep, now: NowDep
) -> list[AdaptiveRecommendationOut]:
    """Pending recommendations first, then recent decisions.

    Asking refreshes them: new ones appear when the last days call for it, outdated
    ones expire. The plan itself changes only when a recommendation is applied.
    """
    async with session.begin():
        game = await load_game_settings(session)
        return await adaptive_service.list_recommendations(session, user, now, game)


@router.post("/recommendations/{recommendation_id}/apply", response_model=RecommendationApplyOut)
async def apply_recommendation(
    recommendation_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    now: NowDep,
    data: RecommendationApplyIn | None = None,
    idempotency_key: IdempotencyKey = None,
) -> JSONResponse:
    """Apply the chosen changes (all by default) together, or none if the plan has changed."""

    async def action() -> tuple[int, RecommendationApplyOut]:
        game = await load_game_settings(session)
        result = await adaptive_service.apply_recommendation(
            session, user, recommendation_id, data or RecommendationApplyIn(), now, game
        )
        return status.HTTP_200_OK, result

    return await run_idempotent(request, session, user.id, idempotency_key, action)


@router.post("/recommendations/{recommendation_id}/dismiss", response_model=AdaptiveRecommendationOut)
async def dismiss_recommendation(
    recommendation_id: uuid.UUID, user: CurrentUser, session: SessionDep, now: NowDep
) -> AdaptiveRecommendationOut:
    """Nothing changes; the same advice does not come back for a while."""
    async with session.begin():
        return await adaptive_service.dismiss_recommendation(session, user, recommendation_id, now)
