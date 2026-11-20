import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain.enums import (
    AchievementCategory,
    Activity,
    AttributeType,
    CycleStatus,
    Difficulty,
    GoalMetric,
    HabitFrequency,
    HabitLogStatus,
    OccurrenceStatus,
    QuestCategory,
    QuestStatus,
    QuestType,
    Rarity,
    RecommendationStatus,
    RecommendationType,
)


def new_id() -> uuid.UUID:
    """Time-ordered UUIDv7 when available (Python 3.14+), else UUIDv4."""
    factory = getattr(uuid, "uuid7", None)
    return factory() if factory else uuid.uuid4()


def _in(column: str, values: type) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"


NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        datetime: DateTime(timezone=True),
        date: Date(),
        uuid.UUID: UUID(as_uuid=True),
    }


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    timezone: Mapped[str] = mapped_column(String(64), server_default="UTC")
    # A time zone change takes effect at the next local midnight (see services.player).
    pending_timezone: Mapped[str | None] = mapped_column(String(64))
    pending_timezone_from: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # All tokens produced by rotating one login share a family; reuse of a
    # rotated token revokes the whole family.
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class PlayerProfile(Base):
    __tablename__ = "player_profiles"
    __table_args__ = (
        CheckConstraint("total_xp >= 0", name="total_xp_non_negative"),
        CheckConstraint("current_level >= 1", name="level_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    total_xp: Mapped[int] = mapped_column(BigInteger, server_default="0")
    current_level: Mapped[int] = mapped_column(Integer, server_default="1")
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    development_started_on: Mapped[date | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Attribute(Base):
    __tablename__ = "attributes"
    __table_args__ = (
        UniqueConstraint("user_id", "attribute_type"),
        CheckConstraint("total_xp >= 0", name="total_xp_non_negative"),
        CheckConstraint(_in("attribute_type", AttributeType), name="attribute_type_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    attribute_type: Mapped[str] = mapped_column(String(20))
    total_xp: Mapped[int] = mapped_column(BigInteger, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class XpLedgerEntry(Base):
    """Append-only journal of XP changes; the source of truth for XP history.

    A database trigger rejects UPDATE and DELETE (except account deletion).
    Corrections are new entries; `reverses_id` links a compensating entry.
    """

    __tablename__ = "xp_ledger"
    __table_args__ = (
        CheckConstraint("xp_amount <> 0", name="xp_amount_non_zero"),
        Index("ix_xp_ledger_user_id_created_at", "user_id", "created_at"),
        Index("ix_xp_ledger_source", "source_type", "source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Deterministic key of the event (UUIDv5 of its source); a retry of the same
    # event hits the unique constraint instead of awarding XP twice.
    event_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    source_type: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[uuid.UUID | None]
    occurrence_date: Mapped[date | None]
    attribute_type: Mapped[str | None] = mapped_column(String(20))
    xp_amount: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    reverses_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("xp_ledger.id", ondelete="CASCADE"), unique=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Quest(Base):
    __tablename__ = "quests"
    __table_args__ = (
        CheckConstraint(_in("quest_type", QuestType), name="quest_type_valid"),
        CheckConstraint(_in("category", QuestCategory), name="category_valid"),
        CheckConstraint(_in("activity", Activity), name="activity_valid"),
        CheckConstraint(_in("difficulty", Difficulty), name="difficulty_valid"),
        CheckConstraint(_in("status", QuestStatus), name="status_valid"),
        CheckConstraint("xp_reward >= 0", name="xp_reward_non_negative"),
        CheckConstraint("target_minutes IS NULL OR target_minutes > 0", name="target_minutes_positive"),
        CheckConstraint("priority BETWEEN 1 AND 3", name="priority_range"),
        CheckConstraint("due_at IS NULL OR due_at > starts_at", name="due_after_start"),
        Index("ix_quests_user_id_status", "user_id", "status"),
        Index("ix_quests_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    quest_type: Mapped[str] = mapped_column(String(20))
    category: Mapped[str] = mapped_column(String(20))
    attribute_types: Mapped[list[str]] = mapped_column(ARRAY(String(20)), server_default="{}")
    activity: Mapped[str] = mapped_column(String(20))
    difficulty: Mapped[str] = mapped_column(String(20))
    target_minutes: Mapped[int | None] = mapped_column(Integer)
    # Fixed when the quest is created: later balance changes do not touch it.
    xp_reward: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), server_default=QuestStatus.ACTIVE.value)
    is_recurring: Mapped[bool]
    # ISO weekdays (1 = Monday) for daily recurring quests; NULL means every day.
    weekdays: Mapped[list[int] | None] = mapped_column(ARRAY(SmallInteger))
    priority: Mapped[int] = mapped_column(SmallInteger, server_default="2")
    # Sub-tasks: a plain checklist, they never give XP.
    checklist: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    # Goal of a life cycle this quest counts towards.
    goal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cycle_goals.id", ondelete="SET NULL"), index=True)
    # Earlier plans, oldest first: [{"until": "YYYY-MM-DD", "weekdays": [...] | null,
    # "target_minutes": int | null}]. Past days are analysed by the plan of that time.
    plan_history: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    starts_at: Mapped[datetime]
    # Local date of starts_at, fixed at creation. One-off quests have exactly one
    # occurrence on this date, so the idempotency key never depends on when the
    # quest is completed.
    anchor_date: Mapped[date]
    due_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class QuestOccurrence(Base):
    """One planned instance of a quest: a day for daily quests, a week for weekly ones."""

    __tablename__ = "quest_occurrences"
    __table_args__ = (
        UniqueConstraint("quest_id", "occurrence_date"),
        CheckConstraint(_in("status", OccurrenceStatus), name="status_valid"),
        CheckConstraint("xp_awarded >= 0", name="xp_awarded_non_negative"),
        Index("ix_quest_occurrences_user_id_completed_at", "user_id", "completed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    quest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quests.id", ondelete="CASCADE"))
    occurrence_date: Mapped[date]
    status: Mapped[str] = mapped_column(String(20), server_default=OccurrenceStatus.PENDING.value)
    completed_at: Mapped[datetime | None]
    skipped_at: Mapped[datetime | None]
    xp_awarded: Mapped[int] = mapped_column(Integer, server_default="0")
    # Learning minutes counted towards the daily cap.
    minutes_credited: Mapped[int | None] = mapped_column(Integer)
    # How many times this occurrence was completed (an undo allows one more);
    # part of the ledger event key.
    completion_count: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class IdempotencyRecord(Base):
    """Stored response of a POST sent with an Idempotency-Key header."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("user_id", "key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[Any | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class GameConfig(Base):
    """Balance settings (reward rules, level curve) editable without a client release."""

    __tablename__ = "game_config"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Habit(Base):
    """A recurring habit. The schedule is fixed at creation: the streak history depends on it."""

    __tablename__ = "habits"
    __table_args__ = (
        CheckConstraint(_in("frequency", HabitFrequency), name="frequency_valid"),
        CheckConstraint(_in("category", QuestCategory), name="category_valid"),
        CheckConstraint("(frequency = 'weekdays') = (weekdays IS NOT NULL)", name="weekdays_match_frequency"),
        CheckConstraint(
            "(frequency = 'weekly') = (times_per_week IS NOT NULL) AND "
            "(times_per_week IS NULL OR times_per_week BETWEEN 1 AND 7)",
            name="times_per_week_match_frequency",
        ),
        CheckConstraint("xp_reward >= 0", name="xp_reward_non_negative"),
        Index("ix_habits_user_id_is_active", "user_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(20))
    attribute_types: Mapped[list[str]] = mapped_column(ARRAY(String(20)), server_default="{}")
    frequency: Mapped[str] = mapped_column(String(20))
    weekdays: Mapped[list[int] | None] = mapped_column(ARRAY(SmallInteger))
    times_per_week: Mapped[int | None] = mapped_column(SmallInteger)
    xp_reward: Mapped[int] = mapped_column(Integer)
    goal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cycle_goals.id", ondelete="SET NULL"), index=True)
    # Local date the habit starts counting from (the creation day).
    starts_on: Mapped[date]
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    archived_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class HabitLog(Base):
    """One local day of a habit: done, undone or frozen (a freeze of a weekly habit uses the week's Monday)."""

    __tablename__ = "habit_logs"
    __table_args__ = (
        UniqueConstraint("habit_id", "completed_on"),
        CheckConstraint(_in("status", HabitLogStatus), name="status_valid"),
        CheckConstraint("xp_awarded >= 0", name="xp_awarded_non_negative"),
        Index("ix_habit_logs_user_id_completed_on", "user_id", "completed_on"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    habit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("habits.id", ondelete="CASCADE"))
    completed_on: Mapped[date]
    status: Mapped[str] = mapped_column(String(20))
    completed_at: Mapped[datetime | None]
    xp_awarded: Mapped[int] = mapped_column(Integer, server_default="0")
    completion_count: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Achievement(Base):
    """Catalog entry. `condition_config` is evaluated by services.achievements."""

    __tablename__ = "achievements"
    __table_args__ = (
        CheckConstraint(_in("category", AchievementCategory), name="category_valid"),
        CheckConstraint(_in("rarity", Rarity), name="rarity_valid"),
        CheckConstraint("xp_reward >= 0", name="xp_reward_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    # English fallback; the client shows localized texts by `code`.
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(20))
    rarity: Mapped[str] = mapped_column(String(20))
    icon: Mapped[str] = mapped_column(String(50))
    xp_reward: Mapped[int] = mapped_column(Integer)
    condition_config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))


class UserAchievement(Base):
    __tablename__ = "user_achievements"
    __table_args__ = (UniqueConstraint("user_id", "achievement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    achievement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("achievements.id", ondelete="CASCADE"))
    unlocked_at: Mapped[datetime]


class LifeCycle(Base):
    """A development cycle of any length (30, 66, 90 days...). At most one is open at a time.

    Pausing moves ends_on forward by the paused days. A completed cycle keeps its
    report as a snapshot and is never changed afterwards.
    """

    __tablename__ = "life_cycles"
    __table_args__ = (
        CheckConstraint(_in("status", CycleStatus), name="status_valid"),
        CheckConstraint("duration_days BETWEEN 7 AND 366", name="duration_range"),
        CheckConstraint("ends_on >= starts_on", name="ends_after_start"),
        CheckConstraint("paused_days >= 0", name="paused_days_non_negative"),
        CheckConstraint("xp_awarded >= 0", name="xp_awarded_non_negative"),
        Index(
            "uq_life_cycles_one_open_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status IN ('active', 'paused')"),
        ),
        Index("ix_life_cycles_user_id_starts_on", "user_id", "starts_on"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    duration_days: Mapped[int] = mapped_column(Integer)
    starts_on: Mapped[date]
    ends_on: Mapped[date]
    status: Mapped[str] = mapped_column(String(20), server_default=CycleStatus.ACTIVE.value)
    paused_on: Mapped[date | None]
    paused_days: Mapped[int] = mapped_column(Integer, server_default="0")
    finished_early: Mapped[bool | None]
    completed_at: Mapped[datetime | None]
    xp_awarded: Mapped[int] = mapped_column(Integer, server_default="0")
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class CycleGoal(Base):
    """A goal of a cycle. Progress is manual or counted from linked quests and habits."""

    __tablename__ = "cycle_goals"
    __table_args__ = (
        CheckConstraint(_in("metric", GoalMetric), name="metric_valid"),
        CheckConstraint(_in("category", QuestCategory), name="category_valid"),
        CheckConstraint("target_value > 0", name="target_positive"),
        CheckConstraint("current_value >= 0", name="current_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("life_cycles.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(20))
    metric: Mapped[str] = mapped_column(String(20))
    target_value: Mapped[int] = mapped_column(Integer)
    # Used by manual goals; the other metrics are counted on the fly.
    current_value: Mapped[int] = mapped_column(Integer, server_default="0")
    unit: Mapped[str | None] = mapped_column(String(30))
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class AdaptiveRecommendation(Base):
    """A suggested change of the plan. Nothing changes until the player applies it.

    target_key identifies what the advice is about ("overload", "stalled:quest:<id>"...):
    at most one pending recommendation per key, and a dismissed key rests for a while.
    """

    __tablename__ = "adaptive_recommendations"
    __table_args__ = (
        CheckConstraint(_in("recommendation_type", RecommendationType), name="type_valid"),
        CheckConstraint(_in("status", RecommendationStatus), name="status_valid"),
        Index(
            "uq_adaptive_recommendations_one_pending_per_key",
            "user_id",
            "target_key",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_adaptive_recommendations_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    recommendation_type: Mapped[str] = mapped_column(String(30))
    target_key: Mapped[str] = mapped_column(String(120))
    # English fallback texts; the client shows localized ones by type and params.
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    suggested_changes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    status: Mapped[str] = mapped_column(String(20), server_default=RecommendationStatus.PENDING.value)
    # Both are set by the service from the request time (the clock tests can move).
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    applied_at: Mapped[datetime | None]
    dismissed_at: Mapped[datetime | None]
    expired_at: Mapped[datetime | None]
