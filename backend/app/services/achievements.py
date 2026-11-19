"""Achievement engine: evaluates catalog conditions and unlocks achievements once.

Condition types (achievements.condition_config):
- {"type": "completions", "count": N, "source": "any|quest|habit", "window_days": D,
   "activity"|"category"|"difficulty"|"quest_type": ...}  completed quests and/or habits
- {"type": "active_days", "count": N}       distinct local days with any completion
- {"type": "learning_minutes", "minutes": N} learning minutes credited by quests
- {"type": "level", "level": N}
- {"type": "habit_streak", "days": N}        best streak of a day-based habit

Unlocking runs inside the completion's transaction with the profile already locked.
Achievement XP can raise the level, which can unlock a level achievement: the loop
repeats until nothing new unlocks. Undoing a completion never takes an achievement back.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import HabitFrequency, HabitLogStatus, LedgerReason, LedgerSource, OccurrenceStatus
from app.domain.streaks import Schedule, compute_streak
from app.domain import dates
from app.models import Achievement, Habit, HabitLog, PlayerProfile, Quest, QuestOccurrence, User, UserAchievement
from app.schemas import AchievementOut, AchievementProgress
from app.services.game_config import GameSettings
from app.services.player import effective_timezone
from app.services.xp import LedgerDraft, apply_xp

QUEST_FILTERS = ("activity", "category", "difficulty", "quest_type")
MAX_CASCADE = 5


@dataclass(frozen=True)
class Progress:
    current: int
    target: int

    @property
    def met(self) -> bool:
        return self.current >= self.target


class _Evaluator:
    """Evaluates conditions for one user, caching the shared queries of one pass."""

    def __init__(self, session: AsyncSession, user: User, profile: PlayerProfile, now: datetime) -> None:
        self.session = session
        self.user = user
        self.profile = profile
        self.now = now
        self.tz = effective_timezone(user, now)
        self._cache: dict[str, int] = {}

    async def progress(self, achievement: Achievement) -> Progress:
        config: dict[str, Any] = achievement.condition_config
        kind = config.get("type")
        if kind == "level":
            return Progress(self.profile.current_level, int(config["level"]))
        if kind == "learning_minutes":
            return Progress(await self._cached("learning_minutes", self._learning_minutes), int(config["minutes"]))
        if kind == "active_days":
            return Progress(await self._cached("active_days", self._active_days), int(config["count"]))
        if kind == "habit_streak":
            return Progress(await self._cached("best_streak", self._best_day_streak), int(config["days"]))
        if kind == "completions":
            return Progress(await self._completions(config), int(config["count"]))
        raise ValueError(f"Unknown achievement condition {kind!r} ({achievement.code})")

    async def _cached(self, key: str, compute) -> int:  # type: ignore[no-untyped-def]
        if key not in self._cache:
            self._cache[key] = int(await compute())
        return self._cache[key]

    async def _learning_minutes(self) -> int:
        value = await self.session.scalar(
            select(func.coalesce(func.sum(QuestOccurrence.minutes_credited), 0)).where(
                QuestOccurrence.user_id == self.user.id, QuestOccurrence.status == OccurrenceStatus.COMPLETED
            )
        )
        return int(value or 0)

    async def _active_days(self) -> int:
        value = await self.session.scalar(
            text(
                """
                SELECT count(*) FROM (
                    SELECT (completed_at AT TIME ZONE :tz)::date AS day
                    FROM quest_occurrences WHERE user_id = :user_id AND status = 'completed'
                    UNION
                    SELECT completed_on FROM habit_logs WHERE user_id = :user_id AND status = 'done'
                ) AS days
                """
            ),
            {"tz": self.tz, "user_id": self.user.id},
        )
        return int(value or 0)

    async def _best_day_streak(self) -> int:
        return await best_day_streak(self.session, self.user, self.now)

    async def _completions(self, config: dict[str, Any]) -> int:
        source = config.get("source", "any")
        since = self.now - timedelta(days=int(config["window_days"])) if config.get("window_days") else None
        total = 0
        if source in ("any", "quest"):
            stmt = (
                select(func.count())
                .select_from(QuestOccurrence)
                .join(Quest, Quest.id == QuestOccurrence.quest_id)
                .where(QuestOccurrence.user_id == self.user.id, QuestOccurrence.status == OccurrenceStatus.COMPLETED)
            )
            for key in QUEST_FILTERS:
                if key in config:
                    stmt = stmt.where(getattr(Quest, key) == config[key])
            if since is not None:
                stmt = stmt.where(QuestOccurrence.completed_at >= since)
            total += int(await self.session.scalar(stmt) or 0)
        # Habits have a category only; a condition on quest-only fields never matches them.
        if source in ("any", "habit") and not any(key in config for key in QUEST_FILTERS if key != "category"):
            stmt = (
                select(func.count())
                .select_from(HabitLog)
                .join(Habit, Habit.id == HabitLog.habit_id)
                .where(HabitLog.user_id == self.user.id, HabitLog.status == HabitLogStatus.DONE)
            )
            if "category" in config:
                stmt = stmt.where(Habit.category == config["category"])
            if since is not None:
                stmt = stmt.where(HabitLog.completed_at >= since)
            total += int(await self.session.scalar(stmt) or 0)
        return total


async def best_day_streak(session: AsyncSession, user: User, now: datetime) -> int:
    """Best streak over all day-based habits (weekly habits count weeks and are left out)."""
    today = dates.local_date(effective_timezone(user, now), now)
    habits = (
        await session.scalars(
            select(Habit).where(Habit.user_id == user.id, Habit.frequency != HabitFrequency.WEEKLY)
        )
    ).all()
    if not habits:
        return 0
    rows = await session.execute(
        select(HabitLog.habit_id, HabitLog.completed_on, HabitLog.status).where(
            HabitLog.habit_id.in_([h.id for h in habits]),
            HabitLog.status.in_([HabitLogStatus.DONE, HabitLogStatus.FROZEN]),
        )
    )
    done: dict[Any, set[Any]] = {h.id: set() for h in habits}
    frozen: dict[Any, set[Any]] = {h.id: set() for h in habits}
    for habit_id, day, status in rows:
        (done if status == HabitLogStatus.DONE else frozen)[habit_id].add(day)
    best = 0
    for habit in habits:
        schedule = Schedule(
            frequency=HabitFrequency(habit.frequency),
            starts_on=habit.starts_on,
            weekdays=frozenset(habit.weekdays or ()),
            times_per_week=habit.times_per_week or 1,
        )
        best = max(best, compute_streak(schedule, done[habit.id], frozen[habit.id], today).best)
    return best


def achievement_out(achievement: Achievement, unlocked_at: datetime | None, progress: Progress) -> AchievementOut:
    target = max(progress.target, 1)
    current = target if unlocked_at else min(progress.current, target)
    return AchievementOut(
        code=achievement.code,
        title=achievement.title,
        description=achievement.description,
        category=achievement.category,
        rarity=achievement.rarity,
        icon=achievement.icon,
        xp_reward=achievement.xp_reward,
        unlocked=unlocked_at is not None,
        unlocked_at=unlocked_at,
        progress=AchievementProgress(current=current, target=target),
    )


async def _catalog(session: AsyncSession) -> list[Achievement]:
    return list(
        (
            await session.scalars(
                select(Achievement).where(Achievement.is_active.is_(True)).order_by(Achievement.sort_order)
            )
        ).all()
    )


async def _unlocked_at(session: AsyncSession, user: User) -> dict[Any, datetime]:
    rows = await session.execute(
        select(UserAchievement.achievement_id, UserAchievement.unlocked_at).where(UserAchievement.user_id == user.id)
    )
    return {achievement_id: unlocked_at for achievement_id, unlocked_at in rows}


async def unlock_new(
    session: AsyncSession, user: User, profile: PlayerProfile, now: datetime, game: GameSettings
) -> list[AchievementOut]:
    """Unlock every achievement whose condition is now met. `profile` must be locked."""
    unlocked = await _unlocked_at(session, user)
    remaining = [a for a in await _catalog(session) if a.id not in unlocked]
    newly: list[AchievementOut] = []
    for _ in range(MAX_CASCADE):
        evaluator = _Evaluator(session, user, profile, now)
        batch = []
        for achievement in remaining:
            progress = await evaluator.progress(achievement)
            if progress.met:
                batch.append((achievement, progress))
        if not batch:
            break
        session.add_all(
            UserAchievement(user_id=user.id, achievement_id=achievement.id, unlocked_at=now) for achievement, _ in batch
        )
        await session.flush()
        drafts = [
            LedgerDraft(
                event_key=f"achievement:{achievement.code}",
                source_type=LedgerSource.ACHIEVEMENT.value,
                source_id=achievement.id,
                occurrence_date=None,
                attribute_type=None,
                xp_amount=achievement.xp_reward,
                reason=LedgerReason.ACHIEVEMENT_UNLOCKED.value,
                description=achievement.title,
            )
            for achievement, _ in batch
            if achievement.xp_reward > 0
        ]
        await apply_xp(session, profile, drafts, game.level_curve, now)
        newly.extend(achievement_out(achievement, now, progress) for achievement, progress in batch)
        unlocked_ids = {achievement.id for achievement, _ in batch}
        remaining = [a for a in remaining if a.id not in unlocked_ids]
    return newly


async def list_achievements(session: AsyncSession, user: User, now: datetime) -> list[AchievementOut]:
    profile = await session.scalar(select(PlayerProfile).where(PlayerProfile.user_id == user.id))
    assert profile is not None
    unlocked = await _unlocked_at(session, user)
    evaluator = _Evaluator(session, user, profile, now)
    result = []
    for achievement in await _catalog(session):
        progress = await evaluator.progress(achievement)
        result.append(achievement_out(achievement, unlocked.get(achievement.id), progress))
    return result
