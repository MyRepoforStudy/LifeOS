from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import get_session
from app.errors import Unauthorized
from app.models import User
from app.security import Passwords, decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_passwords(request: Request) -> Passwords:
    return request.app.state.passwords


def get_now() -> datetime:
    """Current time; tests override this dependency to move the clock."""
    return datetime.now(UTC)


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
PasswordsDep = Annotated[Passwords, Depends(get_passwords)]
NowDep = Annotated[datetime, Depends(get_now)]


async def get_current_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise Unauthorized("Missing bearer token")
    user_id = decode_access_token(credentials.credentials, settings)
    if user_id is None:
        raise Unauthorized("Invalid or expired access token", code="invalid_token")
    async with session.begin():
        user = await session.get(User, user_id)
    if user is None:
        raise Unauthorized("Invalid or expired access token", code="invalid_token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
