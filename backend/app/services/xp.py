"""XP Ledger: every XP change is an immutable ledger entry plus an update of the
profile and attribute totals, all in the caller's transaction."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.levels import LevelCurve, level_after_change, level_progress
from app.errors import Conflict
from app.models import Attribute, PlayerProfile, XpLedgerEntry, new_id
from app.schemas import PlayerXpOut

EVENT_NAMESPACE = uuid.UUID("6f1c3a52-6a5e-4c1e-9a43-2a4f5b8c9d10")


def event_id_for(user_id: uuid.UUID, event_key: str) -> uuid.UUID:
    """Deterministic event id: the same event always maps to the same UUID."""
    return uuid.uuid5(EVENT_NAMESPACE, f"{user_id}:{event_key}")


@dataclass(frozen=True)
class LedgerDraft:
    event_key: str
    source_type: str
    source_id: uuid.UUID | None
    occurrence_date: date | None
    attribute_type: str | None
    xp_amount: int
    reason: str
    description: str | None = None
    reverses_id: uuid.UUID | None = None


@dataclass(frozen=True)
class XpChange:
    total_before: int
    total_after: int
    level_before: int
    level_after: int

    @property
    def delta(self) -> int:
        return self.total_after - self.total_before


async def lock_profile(session: AsyncSession, user_id: uuid.UUID) -> PlayerProfile:
    """Lock the player's profile row.

    Every XP change of a user takes this lock first, so concurrent completions are
    applied one after another and daily limits are checked against committed data.
    """
    result = await session.execute(
        select(PlayerProfile)
        .where(PlayerProfile.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def apply_xp(
    session: AsyncSession,
    profile: PlayerProfile,
    drafts: list[LedgerDraft],
    curve: LevelCurve,
    now: datetime,
) -> XpChange:
    """Write ledger entries and update totals. `profile` must be locked by lock_profile().

    Entries are stamped with the same `now` as the rest of the use case, so local
    dates of the ledger and of quest occurrences always agree.
    """
    total_before, level_before = profile.total_xp, profile.current_level
    if not drafts:
        return XpChange(total_before, total_before, level_before, level_before)

    total_after = total_before + sum(d.xp_amount for d in drafts)
    if total_after < 0:
        raise Conflict("XP total cannot become negative", code="negative_xp")

    rows = [
        {
            "id": new_id(),
            "user_id": profile.user_id,
            "event_id": event_id_for(profile.user_id, d.event_key),
            "source_type": d.source_type,
            "source_id": d.source_id,
            "occurrence_date": d.occurrence_date,
            "attribute_type": d.attribute_type,
            "xp_amount": d.xp_amount,
            "reason": d.reason,
            "description": d.description,
            "reverses_id": d.reverses_id,
            "created_at": now,
        }
        for d in drafts
    ]
    try:
        await session.execute(insert(XpLedgerEntry), rows)
    except IntegrityError as exc:
        raise Conflict("This XP event was already recorded", code="duplicate_event") from exc

    per_attribute: dict[str, int] = {}
    for d in drafts:
        if d.attribute_type:
            per_attribute[d.attribute_type] = per_attribute.get(d.attribute_type, 0) + d.xp_amount
    for attribute_type, amount in per_attribute.items():
        if amount:
            await session.execute(
                update(Attribute)
                .where(Attribute.user_id == profile.user_id, Attribute.attribute_type == attribute_type)
                .values(total_xp=Attribute.total_xp + amount)
            )

    profile.total_xp = total_after
    profile.current_level = level_after_change(level_before, total_before, total_after, curve)
    await session.flush()
    return XpChange(total_before, total_after, level_before, profile.current_level)


def player_xp_out(change: XpChange, curve: LevelCurve) -> PlayerXpOut:
    progress = level_progress(change.total_after, change.level_after, curve)
    return PlayerXpOut(
        level=progress.level,
        total_xp=progress.total_xp,
        xp_in_level=progress.xp_in_level,
        xp_for_level=progress.xp_for_level,
        xp_to_next_level=progress.xp_to_next_level,
        level_progress=progress.progress,
        previous_level=change.level_before,
        leveled_up=change.level_after > change.level_before,
    )
