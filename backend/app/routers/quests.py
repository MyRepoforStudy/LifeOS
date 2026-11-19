import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import JSONResponse, Response

from app.deps import CurrentUser, NowDep, SessionDep
from app.domain.enums import EffectiveQuestStatus, QuestType
from app.idempotency import run_idempotent
from app.schemas import (
    CompletionOut,
    QuestCreateIn,
    QuestDetailOut,
    QuestListOut,
    QuestOut,
    QuestUpdateIn,
    SkipOut,
    UndoOut,
)
from app.services import quests as quest_service
from app.services.game_config import load_game_settings

router = APIRouter(prefix="/quests", tags=["quests"])

IdempotencyKey = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        description="Client-generated key (e.g. a UUID). A retry with the same key returns the first response.",
    ),
]


@router.get("", response_model=QuestListOut)
async def list_quests(
    user: CurrentUser,
    session: SessionDep,
    now: NowDep,
    quest_type: QuestType | None = None,
    status_filter: Annotated[EffectiveQuestStatus | None, Query(alias="status")] = None,
    scope: Literal["all", "today"] = "all",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> QuestListOut:
    """`scope=today`: quests that can be done now, plus one-off quests finished today."""
    async with session.begin():
        return await quest_service.list_quests(
            session,
            user,
            now,
            quest_type=quest_type,
            status=status_filter,
            today_only=scope == "today",
            limit=limit,
            offset=offset,
        )


@router.post("", response_model=QuestOut, status_code=status.HTTP_201_CREATED)
async def create_quest(
    data: QuestCreateIn,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    now: NowDep,
    idempotency_key: IdempotencyKey = None,
) -> JSONResponse:
    """The XP reward is computed by the server from type, activity and difficulty."""

    async def action() -> tuple[int, QuestOut]:
        game = await load_game_settings(session)
        return status.HTTP_201_CREATED, await quest_service.create_quest(session, user, data, now, game)

    return await run_idempotent(request, session, user.id, idempotency_key, action)


@router.get("/{quest_id}", response_model=QuestDetailOut)
async def get_quest(quest_id: uuid.UUID, user: CurrentUser, session: SessionDep, now: NowDep) -> QuestDetailOut:
    async with session.begin():
        return await quest_service.get_quest_detail(session, user, quest_id, now)


@router.patch("/{quest_id}", response_model=QuestOut)
async def update_quest(
    quest_id: uuid.UUID, data: QuestUpdateIn, user: CurrentUser, session: SessionDep, now: NowDep
) -> QuestOut:
    """Type, difficulty, activity and reward are fixed at creation and cannot be changed."""
    async with session.begin():
        return await quest_service.update_quest(session, user, quest_id, data, now)


@router.delete("/{quest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quest(quest_id: uuid.UUID, user: CurrentUser, session: SessionDep, now: NowDep) -> Response:
    """Removes the quest from lists; XP earned with it stays."""
    async with session.begin():
        await quest_service.delete_quest(session, user, quest_id, now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{quest_id}/complete", response_model=CompletionOut)
async def complete_quest(
    quest_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    now: NowDep,
    idempotency_key: IdempotencyKey = None,
) -> JSONResponse:
    """Complete the current occurrence. XP is awarded once per occurrence."""

    async def action() -> tuple[int, CompletionOut]:
        game = await load_game_settings(session)
        return status.HTTP_200_OK, await quest_service.complete_quest(session, user, quest_id, now, game)

    return await run_idempotent(request, session, user.id, idempotency_key, action)


@router.post("/{quest_id}/skip", response_model=SkipOut)
async def skip_quest(
    quest_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    now: NowDep,
    idempotency_key: IdempotencyKey = None,
) -> JSONResponse:
    """Skip the current occurrence. Skipping never removes XP."""

    async def action() -> tuple[int, SkipOut]:
        return status.HTTP_200_OK, await quest_service.skip_quest(session, user, quest_id, now)

    return await run_idempotent(request, session, user.id, idempotency_key, action)


@router.post("/{quest_id}/undo", response_model=UndoOut)
async def undo_completion(
    quest_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    now: NowDep,
    idempotency_key: IdempotencyKey = None,
) -> JSONResponse:
    """Undo a completion made by mistake; allowed until the end of the same local day."""

    async def action() -> tuple[int, UndoOut]:
        game = await load_game_settings(session)
        return status.HTTP_200_OK, await quest_service.undo_completion(session, user, quest_id, now, game)

    return await run_idempotent(request, session, user.id, idempotency_key, action)
