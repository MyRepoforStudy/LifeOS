import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.domain.dates import validate_timezone
from app.domain.enums import (
    AchievementCategory,
    Activity,
    AttributeType,
    CycleDisplayStatus,
    Difficulty,
    EffectiveQuestStatus,
    GoalMetric,
    HabitFrequency,
    OccurrenceStatus,
    QuestCategory,
    QuestType,
    Rarity,
    RecommendationStatus,
    RecommendationType,
    XpLimitReason,
)

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]


class InputModel(BaseModel):
    """Request bodies reject unknown fields: a client cannot send xp_reward, for example."""

    model_config = ConfigDict(extra="forbid")


# --- auth -----------------------------------------------------------------------------


class RegisterIn(InputModel):
    email: EmailStr
    password: Password
    display_name: DisplayName
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, value: str) -> str:
        return validate_timezone(value)


class LoginIn(InputModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class RefreshIn(InputModel):
    refresh_token: Annotated[str, StringConstraints(min_length=16, max_length=256)]


class AccountDeleteIn(InputModel):
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class TokenPairOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


# --- player ---------------------------------------------------------------------------


class LevelInfo(BaseModel):
    level: int
    total_xp: int
    xp_in_level: int
    xp_for_level: int | None
    xp_to_next_level: int | None
    level_progress: float


class ProfileOut(LevelInfo):
    user_id: uuid.UUID
    email: str
    display_name: str
    avatar_url: str | None
    registered_at: datetime
    development_started_on: date | None
    timezone: str
    pending_timezone: str | None
    pending_timezone_from: datetime | None
    active_quests: int
    completed_quests: int
    last_activity_at: datetime | None


class ProfileUpdateIn(InputModel):
    display_name: DisplayName | None = None
    avatar_url: Annotated[str, StringConstraints(max_length=500, pattern=r"^https?://")] | None = None
    development_started_on: date | None = None
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, value: str | None) -> str | None:
        return validate_timezone(value) if value is not None else None


class AttributeOut(LevelInfo):
    attribute_type: AttributeType
    xp_last_7_days: int
    xp_last_30_days: int


class LedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    source_type: str
    source_id: uuid.UUID | None
    occurrence_date: date | None
    attribute_type: str | None
    xp_amount: int
    reason: str
    description: str | None
    reverses_id: uuid.UUID | None
    created_at: datetime


class XpHistoryOut(BaseModel):
    items: list[LedgerEntryOut]
    next_offset: int | None


class DailyXp(BaseModel):
    date: date
    xp: int


class StatisticsOut(BaseModel):
    date_from: date
    date_to: date
    timezone: str
    total_xp: int
    quests_completed: int
    quests_skipped: int
    xp_by_day: list[DailyXp]
    xp_by_attribute: dict[str, int]


class LevelRowOut(BaseModel):
    level: int
    xp_to_next_level: int
    total_xp_required: int


class LevelTableOut(BaseModel):
    base: int
    exponent: float
    levels: list[LevelRowOut]


# --- achievements ---------------------------------------------------------------------


class AchievementProgress(BaseModel):
    current: int
    target: int


class AchievementOut(BaseModel):
    code: str
    title: str
    description: str
    category: AchievementCategory
    rarity: Rarity
    icon: str
    xp_reward: int
    unlocked: bool
    unlocked_at: datetime | None
    progress: AchievementProgress


# --- quests ---------------------------------------------------------------------------


class ChecklistItem(InputModel):
    title: Title
    done: bool = False


def _check_weekdays(value: list[int]) -> list[int]:
    if not value:
        raise ValueError("weekdays must not be empty; omit it for every day")
    if any(day < 1 or day > 7 for day in value):
        raise ValueError("weekdays are ISO numbers 1 (Monday) to 7 (Sunday)")
    return sorted(set(value))


Weekdays = Annotated[list[int], AfterValidator(_check_weekdays)]


class QuestCreateIn(InputModel):
    title: Title
    description: Annotated[str, StringConstraints(max_length=5000)] | None = None
    quest_type: QuestType
    category: QuestCategory
    attribute_types: list[AttributeType] | None = Field(
        default=None, description="Defaults to the attribute of the category"
    )
    activity: Activity = Activity.TASK
    difficulty: Difficulty = Difficulty.MEDIUM
    target_minutes: int | None = Field(default=None, ge=1, le=1440)
    is_recurring: bool | None = Field(default=None, description="Defaults to true for daily and weekly quests")
    weekdays: Weekdays | None = None
    priority: int = Field(default=2, ge=1, le=3)
    starts_at: AwareDatetime | None = None
    due_at: AwareDatetime | None = None
    checklist: list[ChecklistItem] = Field(default_factory=list, max_length=50)
    goal_id: uuid.UUID | None = Field(default=None, description="A goal of the open life cycle")

    @field_validator("attribute_types")
    @classmethod
    def _unique_attributes(cls, value: list[AttributeType] | None) -> list[AttributeType] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("attribute_types must be unique")
        return value

    @model_validator(mode="after")
    def _consistency(self) -> "QuestCreateIn":
        one_off = self.quest_type in (QuestType.PERSONAL, QuestType.CHALLENGE, QuestType.MILESTONE)
        if one_off and self.is_recurring:
            raise ValueError(f"{self.quest_type} quests cannot be recurring")
        recurring = self.is_recurring if self.is_recurring is not None else not one_off
        if self.weekdays is not None and not (self.quest_type == QuestType.DAILY and recurring):
            raise ValueError("weekdays apply only to recurring daily quests")
        if self.starts_at and self.due_at and self.due_at <= self.starts_at:
            raise ValueError("due_at must be after starts_at")
        if self.activity == Activity.LEARNING and self.target_minutes is None:
            raise ValueError("learning quests need target_minutes")
        return self


class QuestUpdateIn(InputModel):
    """Only descriptive fields can change; type, difficulty and reward are fixed at creation."""

    title: Title | None = None
    description: Annotated[str, StringConstraints(max_length=5000)] | None = None
    priority: int | None = Field(default=None, ge=1, le=3)
    due_at: AwareDatetime | None = None
    weekdays: Weekdays | None = None
    checklist: list[ChecklistItem] | None = Field(default=None, max_length=50)
    goal_id: uuid.UUID | None = Field(default=None, description="null removes the link")


class OccurrenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    occurrence_date: date
    status: OccurrenceStatus
    xp_awarded: int
    minutes_credited: int | None
    completed_at: datetime | None
    skipped_at: datetime | None


class QuestOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    quest_type: QuestType
    category: QuestCategory
    attribute_types: list[AttributeType]
    activity: Activity
    difficulty: Difficulty
    target_minutes: int | None
    xp_reward: int
    status: EffectiveQuestStatus
    is_recurring: bool
    weekdays: list[int] | None
    priority: int
    checklist: list[ChecklistItem]
    goal_id: uuid.UUID | None
    starts_at: datetime
    due_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    current_occurrence_date: date | None = Field(
        description="The day (or week start) the quest can be completed for right now"
    )
    current_occurrence: OccurrenceOut | None


class QuestDetailOut(QuestOut):
    occurrences: list[OccurrenceOut]


class QuestListOut(BaseModel):
    items: list[QuestOut]
    total: int


class PlayerXpOut(LevelInfo):
    previous_level: int
    leveled_up: bool


class CompletionOut(BaseModel):
    quest: QuestOut
    occurrence: OccurrenceOut
    xp_awarded: int
    xp_limit_reason: XpLimitReason | None
    player: PlayerXpOut
    achievements_unlocked: list[AchievementOut] = Field(default_factory=list)


class SkipOut(BaseModel):
    quest: QuestOut
    occurrence: OccurrenceOut


class UndoOut(BaseModel):
    quest: QuestOut
    occurrence: OccurrenceOut
    xp_reverted: int
    player: PlayerXpOut


# --- habits ---------------------------------------------------------------------------


class HabitCreateIn(InputModel):
    title: Title
    description: Annotated[str, StringConstraints(max_length=5000)] | None = None
    category: QuestCategory
    attribute_types: list[AttributeType] | None = Field(
        default=None, description="Defaults to the attribute of the category"
    )
    frequency: HabitFrequency = HabitFrequency.DAILY
    weekdays: Weekdays | None = Field(default=None, description="Required for frequency=weekdays")
    times_per_week: int | None = Field(default=None, ge=1, le=7, description="Required for frequency=weekly")
    goal_id: uuid.UUID | None = Field(default=None, description="A goal of the open life cycle")

    @model_validator(mode="after")
    def _schedule(self) -> "HabitCreateIn":
        if (self.frequency == HabitFrequency.WEEKDAYS) != (self.weekdays is not None):
            raise ValueError("weekdays are required for frequency=weekdays and allowed only there")
        if (self.frequency == HabitFrequency.WEEKLY) != (self.times_per_week is not None):
            raise ValueError("times_per_week is required for frequency=weekly and allowed only there")
        if self.attribute_types is not None and len(set(self.attribute_types)) != len(self.attribute_types):
            raise ValueError("attribute_types must be unique")
        return self


class HabitUpdateIn(InputModel):
    """The schedule is fixed: changing it would rewrite the streak history."""

    title: Title | None = None
    description: Annotated[str, StringConstraints(max_length=5000)] | None = None
    goal_id: uuid.UUID | None = Field(default=None, description="null removes the link")


class HabitFreezeIn(InputModel):
    day: date = Field(description="A missed day; for weekly habits the Monday of the missed week")


class StreakOut(BaseModel):
    unit: Literal["day", "week"]
    current: int
    best: int
    last_completed_on: date | None


class HabitOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    category: QuestCategory
    attribute_types: list[AttributeType]
    frequency: HabitFrequency
    weekdays: list[int] | None
    times_per_week: int | None
    xp_reward: int
    is_active: bool
    goal_id: uuid.UUID | None
    starts_on: date
    created_at: datetime
    required_today: bool = Field(description="Planned for today (weekly habits: always)")
    done_today: bool
    week_done: int | None = Field(description="Completions this week, weekly habits only")
    streak: StreakOut
    freezes_left: int = Field(description="Freezes left this month")
    freezable: list[date] = Field(description="Missed days (weeks) that can still be frozen")


class HabitDayOut(BaseModel):
    date: date
    status: Literal["done", "frozen", "missed", "rest", "open", "before_start"]


class HabitDetailOut(HabitOut):
    history: list[HabitDayOut]


class HabitCompletionOut(BaseModel):
    habit: HabitOut
    xp_awarded: int
    xp_limit_reason: XpLimitReason | None
    player: PlayerXpOut
    achievements_unlocked: list[AchievementOut] = Field(default_factory=list)


class HabitUndoOut(BaseModel):
    habit: HabitOut
    xp_reverted: int
    player: PlayerXpOut


# --- life cycles ----------------------------------------------------------------------


class GoalCreateIn(InputModel):
    title: Title
    category: QuestCategory
    metric: GoalMetric = GoalMetric.MANUAL
    target_value: int = Field(default=1, ge=1, le=100_000)
    unit: Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)] | None = None


class GoalUpdateIn(InputModel):
    title: Title | None = None
    target_value: int | None = Field(default=None, ge=1, le=100_000)
    current_value: int | None = Field(default=None, ge=0, le=100_000, description="Manual goals only")
    unit: Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)] | None = None


class CycleCreateIn(InputModel):
    title: Title
    description: Annotated[str, StringConstraints(max_length=5000)] | None = None
    duration_days: int = Field(ge=7, le=366, description="Any length: 30, 45, 66, 90, 120...")
    starts_on: date | None = Field(default=None, description="Local date; today by default, at most 30 days ahead")
    goals: list[GoalCreateIn] = Field(default_factory=list, max_length=10)


class CycleUpdateIn(InputModel):
    title: Title | None = None
    description: Annotated[str, StringConstraints(max_length=5000)] | None = None


class GoalOut(BaseModel):
    id: uuid.UUID
    title: str
    category: QuestCategory
    metric: GoalMetric
    target_value: int
    current_value: int
    unit: str | None
    progress: float
    done: bool
    linked_quests: int
    linked_habits: int


class ReportGoal(BaseModel):
    title: str
    metric: GoalMetric
    target_value: int
    current_value: int
    unit: str | None
    done: bool


class ReportAttribute(BaseModel):
    attribute_type: AttributeType
    xp_gained: int
    level_before: int
    level_after: int


class ReportAchievement(BaseModel):
    code: str
    title: str
    rarity: Rarity


class Recommendation(BaseModel):
    """A rule-based hint for the next cycle; the client words it by `code`."""

    code: str
    params: dict[str, str | int] = Field(default_factory=dict)


class CycleReport(BaseModel):
    starts_on: date
    ends_on: date
    duration_days: int
    paused_days: int
    finished_early: bool
    goals: list[ReportGoal]
    goals_done: int
    goals_total: int
    xp_total: int
    attributes: list[ReportAttribute]
    learning_minutes: int
    workouts: int
    quests_completed: int
    habit_checkins: int
    active_days: int
    achievements: list[ReportAchievement]
    cycle_xp: int
    recommendations: list[Recommendation]


class CycleOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    duration_days: int
    starts_on: date
    ends_on: date
    status: CycleDisplayStatus
    day_number: int = Field(description="Active days lived so far, 0 before the start")
    days_left: int
    time_progress: float
    paused_on: date | None
    paused_days: int
    goals: list[GoalOut]
    goals_done: int
    goals_total: int
    xp_in_cycle: int
    reached_end: bool = Field(description="Summing up now gives the cycle reward")
    finished_early: bool | None
    completed_at: datetime | None
    xp_awarded: int
    report: CycleReport | None


class CycleSummaryOut(BaseModel):
    id: uuid.UUID
    title: str
    status: CycleDisplayStatus
    starts_on: date
    ends_on: date
    duration_days: int
    goals_done: int
    goals_total: int
    xp_awarded: int


class CycleCompletionOut(BaseModel):
    cycle: CycleOut
    xp_awarded: int
    player: PlayerXpOut
    achievements_unlocked: list[AchievementOut] = Field(default_factory=list)


# --- adaptive engine (phase 5) ------------------------------------------------------


class CategoryStatOut(BaseModel):
    category: QuestCategory
    planned: int
    done: int
    rate: float | None


class WindowOut(BaseModel):
    """Plan against reality over the last complete days (today is still open)."""

    days: int
    first_day: date
    last_day: date
    planned: int
    done: int
    skipped: int
    rate: float | None = Field(description="Share of the plan done, null without a plan")
    quests_planned: int
    quests_done: int
    habits_planned: int
    habits_done: int
    learning_minutes_planned: int
    learning_minutes_done: int
    active_days: int
    xp: int
    categories: list[CategoryStatOut]


class ItemStatOut(BaseModel):
    kind: Literal["quest", "habit"]
    id: uuid.UUID
    title: str
    category: QuestCategory
    planned: int
    done: int
    skipped: int
    rate: float | None


class AnalysisOut(BaseModel):
    today: date
    week: WindowOut
    month: WindowOut
    previous_week_rate: float | None = Field(
        description="The 7 days before the last 7; null when that week had too little plan to compare with"
    )
    struggling: list[ItemStatOut] = Field(description="Items most often missed in the last 14 days")


class QuestMinutesChange(BaseModel):
    """Daily minutes of a learning quest; the reward follows the new plan."""

    op: Literal["quest_minutes"] = "quest_minutes"
    quest_id: uuid.UUID
    title: str
    from_minutes: int
    to_minutes: int
    from_xp: int
    to_xp: int


class QuestWeekdaysChange(BaseModel):
    op: Literal["quest_weekdays"] = "quest_weekdays"
    quest_id: uuid.UUID
    title: str
    from_weekdays: list[int] | None = Field(description="null: every day")
    to_weekdays: list[int]


class QuestDueChange(BaseModel):
    op: Literal["quest_due"] = "quest_due"
    quest_id: uuid.UUID
    title: str
    from_due: datetime | None
    to_due: datetime


class HabitScheduleChange(BaseModel):
    """The schedule of a habit is fixed: the old habit goes to the archive with its
    history, and a new one with the lighter schedule takes its place."""

    op: Literal["habit_schedule"] = "habit_schedule"
    habit_id: uuid.UUID
    title: str
    from_frequency: HabitFrequency
    from_weekdays: list[int] | None
    from_times_per_week: int | None
    to_times_per_week: int


class CyclePauseChange(BaseModel):
    op: Literal["cycle_pause"] = "cycle_pause"
    cycle_id: uuid.UUID
    title: str


PlanChange = Annotated[
    QuestMinutesChange | QuestWeekdaysChange | QuestDueChange | HabitScheduleChange | CyclePauseChange,
    Field(discriminator="op"),
]


class AdaptiveRecommendationOut(BaseModel):
    id: uuid.UUID
    recommendation_type: RecommendationType
    status: RecommendationStatus
    title: str = Field(description="English fallback; clients localize by type and params")
    description: str
    params: dict[str, str | int | float | None]
    changes: list[PlanChange]
    created_at: datetime
    updated_at: datetime
    applied_at: datetime | None
    dismissed_at: datetime | None


class RecommendationApplyIn(InputModel):
    changes: list[Annotated[int, Field(ge=0)]] | None = Field(
        default=None, max_length=10, description="Indexes of the changes to apply; all of them by default"
    )


class RecommendationApplyOut(BaseModel):
    recommendation: AdaptiveRecommendationOut
    applied: int
