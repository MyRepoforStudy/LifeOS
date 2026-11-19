import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.enums import AttributeType
from app.errors import Conflict, Unauthorized
from app.models import Attribute, PlayerProfile, RefreshToken, User, new_id
from app.schemas import RegisterIn, TokenPairOut
from app.security import Passwords, create_access_token, hash_refresh_token, new_refresh_token


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def register(session: AsyncSession, passwords: Passwords, data: RegisterIn) -> User:
    """Create the user with a level-1 profile and the four attributes at 0 XP."""
    email = normalize_email(data.email)
    if await session.scalar(select(User.id).where(User.email == email)):
        raise Conflict("This e-mail is already registered", code="email_taken")
    user = User(
        email=email,
        password_hash=passwords.hash(data.password),
        display_name=data.display_name,
        timezone=data.timezone,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise Conflict("This e-mail is already registered", code="email_taken") from exc
    session.add(PlayerProfile(user_id=user.id))
    session.add_all(Attribute(user_id=user.id, attribute_type=a.value) for a in AttributeType)
    await session.flush()
    return user


async def authenticate(session: AsyncSession, passwords: Passwords, email: str, password: str) -> User:
    user = await session.scalar(select(User).where(User.email == normalize_email(email)))
    if not passwords.verify(user.password_hash if user else None, password):
        raise Unauthorized("Invalid e-mail or password", code="invalid_credentials")
    assert user is not None
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash(password)
    return user


async def issue_tokens(
    session: AsyncSession,
    settings: Settings,
    user_id: uuid.UUID,
    now: datetime,
    family_id: uuid.UUID | None = None,
) -> TokenPairOut:
    raw, token_hash = new_refresh_token()
    session.add(
        RefreshToken(
            user_id=user_id,
            family_id=family_id or new_id(),
            token_hash=token_hash,
            expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        )
    )
    await session.flush()
    return TokenPairOut(
        # JWTs are checked against the wall clock, so they are issued with it too.
        access_token=create_access_token(user_id, settings),
        refresh_token=raw,
        expires_in=settings.access_token_ttl_minutes * 60,
    )


async def rotate_refresh_token(
    session: AsyncSession, settings: Settings, raw_token: str, now: datetime
) -> TokenPairOut | None:
    """Exchange a refresh token for a new pair (rotation).

    Returns None when an already rotated token is presented again: that means it
    leaked, so the whole family is revoked. The caller commits and then rejects.
    """
    token = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token)).with_for_update()
    )
    if token is None:
        raise Unauthorized("Invalid refresh token", code="invalid_refresh_token")
    if token.revoked_at is not None:
        await _revoke_family(session, token.family_id, now)
        return None
    if token.expires_at <= now:
        raise Unauthorized("Refresh token expired", code="refresh_token_expired")
    token.revoked_at = now
    return await issue_tokens(session, settings, token.user_id, now, family_id=token.family_id)


async def revoke_refresh_token(session: AsyncSession, raw_token: str, now: datetime) -> None:
    token = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token)))
    if token is not None:
        await _revoke_family(session, token.family_id, now)


async def _revoke_family(session: AsyncSession, family_id: uuid.UUID, now: datetime) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def delete_account(session: AsyncSession, passwords: Passwords, user: User, password: str) -> None:
    """Delete the user and every row that belongs to them (FK cascades)."""
    if not passwords.verify(user.password_hash, password):
        raise Unauthorized("Invalid password", code="invalid_credentials")
    # The ledger trigger allows DELETE only with this transaction-local flag.
    await session.execute(text("SET LOCAL lifeos.allow_ledger_delete = 'on'"))
    await session.execute(delete(User).where(User.id == user.id))
