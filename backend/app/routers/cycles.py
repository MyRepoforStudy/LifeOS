import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse, Response

from app.deps import CurrentUser, NowDep, SessionDep
from app.idempotency import run_idempotent
from app.schemas import (
    CycleCompletionOut,
    CycleCreateIn,
    CycleOut,
    CycleSummaryOut,
    CycleUpdateIn,
    GoalCreateIn,
    GoalUpdateIn,
)
from app.services import cycles as cycle_service
from app.services.game_config import load_game_settings

router = APIRouter(prefix="/cycles", tags=["cycles"])

IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]


@router.get("", response_model=list[CycleSummaryOut])
async def list_cycles(user: CurrentUser, session: SessionDep, now: NowDep) -> list[CycleSummaryOut]:
    """All cycles, the newest first: the open one and the history."""
    async with session.begin():
        return await cycle_service.list_cycles(session, user, now)


@router.post("", response_model=CycleOut, status_code=status.HTTP_201_CREATED)
async def create_cycle(
    data: CycleCreateIn,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    now: NowDep,
    idempotency_key: IdempotencyKey = None,
) -> JSONResponse:
    """Start a cycle of any length (7-366 days). Only one cycle can be open at a time."""

    async def action() -> tuple[int, CycleOut]:
        return status.HTTP_201_CREATED, await cycle_service.create_cycle(session, user, data, now)

    return await run_idempotent(request, session, user.id, idempotency_key, action)


@router.get("/current", response_model=CycleOut | None)
async def current_cycle(user: CurrentUser, session: SessionDep, now: NowDep) -> CycleOut | None:
    """The open (active or paused) cycle, or null."""
    async with session.begin():
        return await cycle_service.get_current_cycle(session, user, now)


@router.get("/{cycle_id}", response_model=CycleOut)
async def get_cycle(cycle_id: uuid.UUID, user: CurrentUser, session: SessionDep, now: NowDep) -> CycleOut:
    async with session.begin():
        return await cycle_service.get_cycle(session, user, cycle_id, now)


@router.patch("/{cycle_id}", response_model=CycleOut)
async def update_cycle(
    cycle_id: uuid.UUID, data: CycleUpdateIn, user: CurrentUser, session: SessionDep, now: NowDep
) -> CycleOut:
    async with session.begin():
        return await cycle_service.update_cycle(session, user, cycle_id, data, now)


@router.delete("/{cycle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_cycle(cycle_id: uuid.UUID, user: CurrentUser, session: SessionDep, now: NowDep) -> Response:
    """Cancel the open cycle: it stays in the history, without a report or reward."""
    async with session.begin():
        await cycle_service.cancel_cycle(session, user, cycle_id, now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{cycle_id}/goals", response_model=CycleOut, status_code=status.HTTP_201_CREATED)
async def add_goal(
    cycle_id: uuid.UUID, data: GoalCreateIn, user: CurrentUser, session: SessionDep, now: NowDep
) -> CycleOut:
    async with session.begin():
        return await cycle_service.add_goal(session, user, cycle_id, data, now)


@router.patch("/{cycle_id}/goals/{goal_id}", response_model=CycleOut)
async def update_goal(
    cycle_id: uuid.UUID, goal_id: uuid.UUID, data: GoalUpdateIn, user: CurrentUser, session: SessionDep, now: NowDep
) -> CycleOut:
    """current_value can be set only for manual goals; the others are counted."""
    async with session.begin():
        return await cycle_service.update_goal(session, user, cycle_id, goal_id, data, now)


@router.delete("/{cycle_id}/goals/{goal_id}", response_model=CycleOut)
async def delete_goal(
    cycle_id: uuid.UUID, goal_id: uuid.UUID, user: CurrentUser, session: SessionDep, now: NowDep
) -> CycleOut:
    async with session.begin():
        return await cycle_service.delete_goal(session, user, cycle_id, goal_id, now)


@router.post("/{cycle_id}/pause", response_model=CycleOut)
async def pause_cycle(cycle_id: uuid.UUID, user: CurrentUser, session: SessionDep, now: NowDep) -> CycleOut:
    """The paused days are added to the end date when the cycle resumes."""
    async with session.begin():
        return await cycle_service.pause_cycle(session, user, cycle_id, now)


@router.post("/{cycle_id}/resume", response_model=CycleOut)
async def resume_cycle(cycle_id: uuid.UUID, user: CurrentUser, session: SessionDep, now: NowDep) -> CycleOut:
    async with session.begin():
        return await cycle_service.resume_cycle(session, user, cycle_id, now)


@router.post("/{cycle_id}/complete", response_model=CycleCompletionOut)
async def complete_cycle(
    cycle_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    now: NowDep,
    idempotency_key: IdempotencyKey = None,
) -> JSONResponse:
    """Sum the cycle up: the report is saved as a snapshot. After the end date it gives
    200 XP x the share of goals done; finishing early gives no reward."""

    async def action() -> tuple[int, CycleCompletionOut]:
        game = await load_game_settings(session)
        return status.HTTP_200_OK, await cycle_service.complete_cycle(session, user, cycle_id, now, game)

    return await run_idempotent(request, session, user.id, idempotency_key, action)
