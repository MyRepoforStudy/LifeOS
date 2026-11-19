import pytest

from app.domain.enums import Activity, AttributeType, Difficulty, QuestType
from app.domain.rewards import RewardRules, learning_xp, quest_reward, scaled_learning_reward, split_xp

RULES = RewardRules()


def reward(
    quest_type: QuestType = QuestType.PERSONAL,
    activity: Activity = Activity.TASK,
    difficulty: Difficulty = Difficulty.MEDIUM,
    minutes: int | None = None,
) -> int:
    return quest_reward(RULES, quest_type=quest_type, activity=activity, difficulty=difficulty, target_minutes=minutes)


@pytest.mark.parametrize(
    ("difficulty", "xp"),
    [(Difficulty.SIMPLE, 10), (Difficulty.MEDIUM, 20), (Difficulty.HARD, 40), (Difficulty.EPIC, 100)],
)
def test_task_rewards_follow_difficulty(difficulty: Difficulty, xp: int) -> None:
    assert reward(difficulty=difficulty) == xp


@pytest.mark.parametrize(("minutes", "xp"), [(0, 0), (29, 0), (30, 15), (45, 15), (60, 25), (90, 35), (240, 85)])
def test_learning_xp_counts_full_blocks(minutes: int, xp: int) -> None:
    assert learning_xp(minutes, RULES) == xp


def test_spec_examples() -> None:
    assert reward(QuestType.DAILY, Activity.LEARNING, minutes=60) == 25  # DevOps 60 min
    assert reward(QuestType.DAILY, Activity.LEARNING, minutes=30) == 15  # English 30 min
    assert reward(QuestType.DAILY, Activity.WORKOUT) == 30
    assert reward(QuestType.DAILY, difficulty=Difficulty.SIMPLE) == 10  # record expenses
    assert reward(QuestType.WEEKLY, difficulty=Difficulty.SIMPLE) == 100


def test_challenge_doubles_the_reward() -> None:
    assert reward(QuestType.CHALLENGE, difficulty=Difficulty.HARD) == 80
    assert reward(QuestType.CHALLENGE, Activity.LEARNING, minutes=60) == 50


def test_scaled_learning_reward() -> None:
    assert scaled_learning_reward(25, 60, 60, RULES) == 25
    assert scaled_learning_reward(25, 60, 30, RULES) == 15
    assert scaled_learning_reward(25, 60, 0, RULES) == 0
    assert scaled_learning_reward(50, 60, 30, RULES) == 30


def test_split_xp() -> None:
    both = [AttributeType.INTELLIGENCE, AttributeType.CAREER]
    assert split_xp(25, both) == [(AttributeType.INTELLIGENCE, 13), (AttributeType.CAREER, 12)]
    assert split_xp(10, []) == [(None, 10)]
    assert split_xp(0, both) == []
    assert split_xp(1, both) == [(AttributeType.INTELLIGENCE, 1)]
