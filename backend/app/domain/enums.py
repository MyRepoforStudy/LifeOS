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
    HABIT = "habit"
    HABIT_UNDO = "habit_undo"
    ACHIEVEMENT = "achievement"
    ADJUSTMENT = "adjustment"


class LedgerReason(StrEnum):
    QUEST_COMPLETED = "quest_completed"
    QUEST_COMPLETION_UNDONE = "quest_completion_undone"
    HABIT_COMPLETED = "habit_completed"
    HABIT_COMPLETION_UNDONE = "habit_completion_undone"
    ACHIEVEMENT_UNLOCKED = "achievement_unlocked"
    MANUAL_ADJUSTMENT = "manual_adjustment"


class XpLimitReason(StrEnum):
    SIMPLE_TASK_DAILY_LIMIT = "simple_task_daily_limit"
    LEARNING_DAILY_CAP = "learning_daily_cap"
    HABIT_DAILY_LIMIT = "habit_daily_limit"


class HabitFrequency(StrEnum):
    DAILY = "daily"
    WEEKDAYS = "weekdays"  # on chosen ISO weekdays; other days are rest days
    WEEKLY = "weekly"  # N times per ISO week; the streak counts weeks


class HabitLogStatus(StrEnum):
    DONE = "done"
    UNDONE = "undone"  # completed, then undone on the same day
    FROZEN = "frozen"  # a missed day (or week) covered by a streak freeze


class AchievementCategory(StrEnum):
    CONSISTENCY = "consistency"
    LEARNING = "learning"
    HEALTH = "health"
    FINANCE = "finance"
    CAREER = "career"
    LEVEL = "level"


class Rarity(StrEnum):
    COMMON = "common"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


ONE_OFF_TYPES = frozenset({QuestType.PERSONAL, QuestType.CHALLENGE, QuestType.MILESTONE})
LATE_COMPLETION_TYPES = frozenset({QuestType.PERSONAL, QuestType.MILESTONE})

CATEGORY_DEFAULT_ATTRIBUTE: dict[QuestCategory, AttributeType | None] = {
    QuestCategory.HEALTH: AttributeType.HEALTH,
    QuestCategory.LEARNING: AttributeType.INTELLIGENCE,
    QuestCategory.CAREER: AttributeType.CAREER,
    QuestCategory.FINANCE: AttributeType.FINANCE,
    QuestCategory.OTHER: None,
}
