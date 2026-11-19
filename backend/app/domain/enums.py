from enum import StrEnum


class AttributeType(StrEnum):
    HEALTH = "health"
    INTELLIGENCE = "intelligence"
    CAREER = "career"
    FINANCE = "finance"


class QuestType(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    PERSONAL = "personal"
    CHALLENGE = "challenge"
    MILESTONE = "milestone"


class QuestCategory(StrEnum):
    HEALTH = "health"
    LEARNING = "learning"
    CAREER = "career"
    FINANCE = "finance"
    OTHER = "other"


class Activity(StrEnum):
    """What the quest is about; decides which reward rule applies."""

    TASK = "task"
    LEARNING = "learning"
    WORKOUT = "workout"


class Difficulty(StrEnum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    HARD = "hard"
    EPIC = "epic"  # a major project


class QuestStatus(StrEnum):
    """Stored status of a quest row."""

    ACTIVE = "active"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class EffectiveQuestStatus(StrEnum):
    """Status shown to the client: the stored one plus time-based states."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class OccurrenceStatus(StrEnum):
    PENDING = "pending"  # exists, no outcome yet (e.g. after an undo)
    COMPLETED = "completed"
    SKIPPED = "skipped"


class LedgerSource(StrEnum):
    QUEST = "quest"
    QUEST_UNDO = "quest_undo"
    ADJUSTMENT = "adjustment"


class LedgerReason(StrEnum):
    QUEST_COMPLETED = "quest_completed"
    QUEST_COMPLETION_UNDONE = "quest_completion_undone"
    MANUAL_ADJUSTMENT = "manual_adjustment"


class XpLimitReason(StrEnum):
    SIMPLE_TASK_DAILY_LIMIT = "simple_task_daily_limit"
    LEARNING_DAILY_CAP = "learning_daily_cap"


ONE_OFF_TYPES = frozenset({QuestType.PERSONAL, QuestType.CHALLENGE, QuestType.MILESTONE})
LATE_COMPLETION_TYPES = frozenset({QuestType.PERSONAL, QuestType.MILESTONE})

CATEGORY_DEFAULT_ATTRIBUTE: dict[QuestCategory, AttributeType | None] = {
    QuestCategory.HEALTH: AttributeType.HEALTH,
    QuestCategory.LEARNING: AttributeType.INTELLIGENCE,
    QuestCategory.CAREER: AttributeType.CAREER,
    QuestCategory.FINANCE: AttributeType.FINANCE,
    QuestCategory.OTHER: None,
}
