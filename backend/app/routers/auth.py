from fastapi import APIRouter, status
from fastapi.responses import Response

from app.deps import CurrentUser, NowDep, PasswordsDep, SessionDep, SettingsDep
from app.errors import Unauthorized
from app.schemas import AccountDeleteIn, LoginIn, RefreshIn, RegisterIn, TokenPairOut
from app.services import auth as auth_service

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=TokenPairOut, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterIn, session: SessionDep, settings: SettingsDep, passwords: PasswordsDep, now: NowDep
) -> TokenPairOut:
    async with session.begin():
        user = await auth_service.register(session, passwords, data)
        return await auth_service.issue_tokens(session, settings, user.id, now)


@router.post("/auth/login", response_model=TokenPairOut)
async def login(
    data: LoginIn, session: SessionDep, settings: SettingsDep, passwords: PasswordsDep, now: NowDep
) -> TokenPairOut:
    async with session.begin():
        user = await auth_service.authenticate(session, passwords, data.email, data.password)
        return await auth_service.issue_tokens(session, settings, user.id, now)


@router.post("/auth/refresh", response_model=TokenPairOut)
async def refresh(data: RefreshIn, session: SessionDep, settings: SettingsDep, now: NowDep) -> TokenPairOut:
    async with session.begin():
        tokens = await auth_service.rotate_refresh_token(session, settings, data.refresh_token, now)
    if tokens is None:
        # Committed above: the whole token family is revoked.
        raise Unauthorized("Refresh token was already used; please log in again", code="refresh_token_reused")
    return tokens


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(data: RefreshIn, session: SessionDep, now: NowDep) -> Response:
    async with session.begin():
        await auth_service.revoke_refresh_token(session, data.refresh_token, now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/account/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    data: AccountDeleteIn, user: CurrentUser, session: SessionDep, passwords: PasswordsDep
) -> Response:
    """Delete the account and all its data, including the XP ledger."""
    async with session.begin():
        await auth_service.delete_account(session, passwords, user, data.password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
