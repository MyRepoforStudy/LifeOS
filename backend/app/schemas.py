import uuid
from datetime import date, datetime
from typing import Annotated

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
    Activity,
    AttributeType,
    Difficulty,
    EffectiveQuestStatus,
    OccurrenceStatus,
    QuestCategory,
    QuestType,
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


class SkipOut(BaseModel):
    quest: QuestOut
    occurrence: OccurrenceOut


class UndoOut(BaseModel):
    quest: QuestOut
    occurrence: OccurrenceOut
    xp_reverted: int
    player: PlayerXpOut
