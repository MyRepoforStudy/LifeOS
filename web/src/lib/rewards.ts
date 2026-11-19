import type { components } from "../api/schema";
import type { Activity, Difficulty, QuestType } from "../api/types";

export type RewardRules = components["schemas"]["RewardRules"];

export function learningXp(minutes: number, rules: RewardRules): number {
  const blocks = Math.floor(Math.max(0, minutes) / rules.learning_block_minutes);
  if (blocks === 0) return 0;
  return rules.learning_first_block + rules.learning_next_block * (blocks - 1);
}

/** Preview only: mirrors app/domain/rewards.py, the server decides the real reward. */
export function previewReward(
  rules: RewardRules,
  questType: QuestType,
  activity: Activity,
  difficulty: Difficulty,
  minutes: number | null,
): number {
  let base: number;
  if (questType === "weekly") base = rules.weekly_quest;
  else if (activity === "learning") base = learningXp(minutes ?? 0, rules);
  else if (activity === "workout") base = rules.workout;
  else {
    const byDifficulty: Record<Difficulty, number> = {
      simple: rules.task_simple,
      medium: rules.task_medium,
      hard: rules.task_hard,
      epic: rules.task_epic,
    };
    base = byDifficulty[difficulty];
  }
  if (questType === "challenge") base = Math.floor(base * rules.challenge_multiplier + 0.5);
  return base;
}
