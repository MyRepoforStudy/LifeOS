"""Idempotency-Key support for POST endpoints.

The key is claimed inside the same transaction as the action itself, so:
- a retry after a network error returns the stored response instead of acting again;
- a concurrent duplicate waits on the unique index and then gets the stored response;
- if the action fails, the claim rolls back with it and the client may retry.
"""

import hashlib
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import Conflict, InvalidRequest
from app.models import IdempotencyRecord, new_id

REPLAY_HEADER = "Idempotent-Replayed"

Action = Callable[[], Awaitable[tuple[int, Any]]]


def _fingerprint(method: str, path: str, body: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(f"{method} {path}\n".encode())
    digest.update(body)
    return digest.hexdigest()


async def run_idempotent(
    request: Request,
    session: AsyncSession,
    user_id: uuid.UUID,
    key: str | None,
    action: Action,
) -> JSONResponse:
    if key is not None:
        key = key.strip()
        if not 1 <= len(key) <= 100:
            raise InvalidRequest("Idempotency-Key must be 1-100 characters", code="invalid_idempotency_key")
    fingerprint = _fingerprint(request.method, request.url.path, await request.body())

    async with session.begin():
        record_id: uuid.UUID | None = None
        if key:
            claimed = await session.execute(
                pg_insert(IdempotencyRecord)
                .values(id=new_id(), user_id=user_id, key=key, request_hash=fingerprint)
                .on_conflict_do_nothing(index_elements=["user_id", "key"])
                .returning(IdempotencyRecord.id)
            )
            record_id = claimed.scalar_one_or_none()
            if record_id is None:
                existing = (
                    await session.execute(
                        select(IdempotencyRecord).where(
                            IdempotencyRecord.user_id == user_id, IdempotencyRecord.key == key
                        )
                    )
                ).scalar_one()
                if existing.request_hash != fingerprint:
                    raise InvalidRequest(
                        "Idempotency-Key was already used for a different request",
                        code="idempotency_key_reused",
                    )
                if existing.status_code is None:
                    raise Conflict("A request with this Idempotency-Key is in progress", code="idempotency_in_progress")
                return JSONResponse(
                    status_code=existing.status_code,
                    content=existing.response_body,
                    headers={REPLAY_HEADER: "true"},
                )

        status_code, payload = await action()
        content = jsonable_encoder(payload)
        if record_id is not None:
            await session.execute(
                update(IdempotencyRecord)
                .where(IdempotencyRecord.id == record_id)
                .values(status_code=status_code, response_body=content)
            )
    return JSONResponse(status_code=status_code, content=content)
