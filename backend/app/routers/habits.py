import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse, Response

from app.deps import CurrentUser, NowDep, SessionDep
from app.idempotency import run_idempotent
from app.schemas import (
    HabitCompletionOut,
    HabitCreateIn,
    HabitDetailOut,
    HabitFreezeIn,
    HabitOut,
    HabitUndoOut,
    HabitUpdateIn,
    StreakOut,
)
from app.services import habits as habit_service
from app.services.game_config import load_game_settings

router = APIRouter(prefix="/habits", tags=["habits"])

IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]


@router.get("", response_model=list[HabitOut])
async def list_habits(
    user: CurrentUser, session: SessionDep, now: NowDep, include_archived: bool = False
) -> list[HabitOut]:
    async with session.begin():
        game = await load_game_settings(session)
        return await habit_service.list_habits(session, user, now, game, include_archived=include_archived)


@router.post("", response_model=HabitOut, status_code=status.HTTP_201_CREATED)
async def create_habit(
    data: HabitCreateIn,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    now: NowDep,
    idempotency_key: IdempotencyKey = None,
) -> JSONResponse:
    """The XP per completion (15 by default) is fixed when the habit is created."""

    async def action() -> tuple[int, HabitOut]:
        game = await load_game_settings(session)
        return status.HTTP_201_CREATED, await habit_service.create_habit(session, user, data, now, game)

    return await run_idempotent(request, session, user.id, idempotency_key, action)


@router.get("/{habit_id}", response_model=HabitDetailOut)
async def get_habit(habit_id: uuid.UUID, user: CurrentUser, session: SessionDep, now: NowDep) -> HabitDetailOut:
    async with session.begin():
        game = await load_game_settings(session)
        return await habit_service.get_habit_detail(session, user, habit_id, now, game)


@router.get("/{habit_id}/streak", response_model=StreakOut)
async def get_streak(habit_id: uuid.UUID, user: CurrentUser, session: SessionDep, now: NowDep) -> StreakOut:
    async with session.begin():
        game = await load_game_settings(session)
        return (await habit_service.get_habit_detail(session, user, habit_id, now, game)).streak


@router.patch("/{habit_id}", response_model=HabitOut)
async def update_habit(
    habit_id: uuid.UUID, data: HabitUpdateIn, user: CurrentUser, session: SessionDep, now: NowDep
) -> HabitOut:
    async with session.begin():
        game = await load_game_settings(session)
        return await habit_service.update_habit(session, user, habit_id, data, now, game)


@router.delete("/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_habit(habit_id: uuid.UUID, user: CurrentUser, session: SessionDep, now: NowDep) -> Response:
    """Archives the habit; earned XP and the history stay."""
    async with session.begin():
        await habit_service.archive_habit(session, user, habit_id, now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{habit_id}/complete", response_model=HabitCompletionOut)
async def complete_habit(
    habit_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    now: NowDep,
    idempotency_key: IdempotencyKey = None,
) -> JSONResponse:
    """Mark the habit done for today (local date). XP is awarded once per day."""

    async def action() -> tuple[int, HabitCompletionOut]:
        game = await load_game_settings(session)
        return status.HTTP_200_OK, await habit_service.complete_habit(session, user, habit_id, now, game)

    return await run_idempotent(request, session, user.id, idempotency_key, action)


@router.post("/{habit_id}/undo", response_model=HabitUndoOut)
async def undo_habit(
    habit_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    now: NowDep,
    idempotency_key: IdempotencyKey = None,
) -> JSONResponse:
    async def action() -> tuple[int, HabitUndoOut]:
        game = await load_game_settings(session)
        return status.HTTP_200_OK, await habit_service.undo_habit(session, user, habit_id, now, game)

    return await run_idempotent(request, session, user.id, idempotency_key, action)


@router.post("/{habit_id}/freeze", response_model=HabitOut)
async def freeze_missed_day(
    habit_id: uuid.UUID,
    data: HabitFreezeIn,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    now: NowDep,
    idempotency_key: IdempotencyKey = None,
) -> JSONResponse:
    """Cover a missed day (a week for weekly habits) so the streak is kept. 2 per month by default."""

    async def action() -> tuple[int, HabitOut]:
        game = await load_game_settings(session)
        return status.HTTP_200_OK, await habit_service.freeze_missed(session, user, habit_id, data.day, now, game)

    return await run_idempotent(request, session, user.id, idempotency_key, action)
