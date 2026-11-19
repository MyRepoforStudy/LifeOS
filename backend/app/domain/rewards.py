"""Reward rules. The server alone decides how much XP an action is worth."""

from pydantic import BaseModel, Field

from app.domain.enums import Activity, AttributeType, Difficulty, QuestType


class RewardRules(BaseModel, frozen=True):
    task_simple: int = Field(default=10, ge=0)
    task_medium: int = Field(default=20, ge=0)
    task_hard: int = Field(default=40, ge=0)
    task_epic: int = Field(default=100, ge=0)
    habit: int = Field(default=15, ge=0)
    workout: int = Field(default=30, ge=0)
    weekly_quest: int = Field(default=100, ge=0)
    cycle_completion: int = Field(default=200, ge=0)

    # Learning: the first full block gives `learning_first_block`, every next full
    # block gives `learning_next_block` (30 min = 15 XP, 60 min = 25 XP, ...).
    learning_block_minutes: int = Field(default=30, gt=0)
    learning_first_block: int = Field(default=15, ge=0)
    learning_next_block: int = Field(default=10, ge=0)
    learning_daily_cap_minutes: int = Field(default=240, gt=0)

    challenge_multiplier: float = Field(default=2.0, ge=1.0)
    # Only the first N simple tasks per local day give XP.
    simple_task_daily_limit: int = Field(default=5, ge=0)

    def task_xp(self, difficulty: Difficulty) -> int:
        return {
            Difficulty.SIMPLE: self.task_simple,
            Difficulty.MEDIUM: self.task_medium,
            Difficulty.HARD: self.task_hard,
            Difficulty.EPIC: self.task_epic,
        }[difficulty]


def learning_xp(minutes: int, rules: RewardRules) -> int:
    """XP for a learning session; only full blocks count."""
    blocks = max(0, minutes) // rules.learning_block_minutes
    if blocks == 0:
        return 0
    return rules.learning_first_block + rules.learning_next_block * (blocks - 1)


def quest_reward(
    rules: RewardRules,
    *,
    quest_type: QuestType,
    activity: Activity,
    difficulty: Difficulty,
    target_minutes: int | None,
) -> int:
    """XP for completing a quest, fixed when the quest is created."""
    if quest_type is QuestType.WEEKLY:
        base = rules.weekly_quest
    elif activity is Activity.LEARNING:
        base = learning_xp(target_minutes or 0, rules)
    elif activity is Activity.WORKOUT:
        base = rules.workout
    else:
        base = rules.task_xp(difficulty)
    if quest_type is QuestType.CHALLENGE:
        base = int(base * rules.challenge_multiplier + 0.5)
    return base


def scaled_learning_reward(xp_reward: int, target_minutes: int, credited_minutes: int, rules: RewardRules) -> int:
    """Part of a learning quest's reward when the daily cap credits fewer minutes than planned."""
    if credited_minutes >= target_minutes:
        return xp_reward
    full = learning_xp(target_minutes, rules)
    if full == 0:
        return 0
    return int(xp_reward * learning_xp(credited_minutes, rules) / full + 0.5)


def split_xp(total: int, attributes: list[AttributeType]) -> list[tuple[AttributeType | None, int]]:
    """Split XP evenly between attributes; the remainder goes to the first ones."""
    if total <= 0:
        return []
    if not attributes:
        return [(None, total)]
    share, remainder = divmod(total, len(attributes))
    parts = [(attr, share + (1 if i < remainder else 0)) for i, attr in enumerate(attributes)]
    return [(attr, amount) for attr, amount in parts if amount > 0]
