import type { Cycle, CycleStatus, Goal, GoalMetric, Recommendation } from "../api/types";
import type { MessageKey } from "../i18n";
import { parseLocalDate } from "./format";
import type { RewardRules } from "./rewards";

type Translate = (key: MessageKey, params?: Record<string, string | number>) => string;

/** Mirrors the limits in app/schemas.py and app/services/cycles.py. */
export const DURATION_PRESETS = [30, 45, 66, 90, 120] as const;
export const MIN_DURATION = 7;
export const MAX_DURATION = 366;
export const MAX_GOALS = 10;
export const MAX_START_AHEAD_DAYS = 30;
export const MAX_GOAL_VALUE = 100_000;

const OPEN: CycleStatus[] = ["planned", "active", "paused", "finished"];

/** Goals can change and the cycle can be paused, summed up or cancelled. */
export function isOpen(cycle: Pick<Cycle, "status">): boolean {
  return OPEN.includes(cycle.status);
}

export function statusChip(status: CycleStatus): string {
  if (status === "active" || status === "finished") return "chip chip-gold";
  if (status === "paused") return "chip chip-frozen";
  if (status === "completed") return "chip chip-success";
  if (status === "cancelled") return "chip chip-danger";
  return "chip";
}

/** A date in the browser's zone as YYYY-MM-DD. */
export function localDate(date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function addDays(day: string, days: number): string {
  const date = parseLocalDate(day);
  date.setDate(date.getDate() + days);
  return localDate(date);
}

/** Goal metrics that a quest or a habit can feed. */
export function acceptedMetrics(kind: "quest" | "habit", activity?: string): GoalMetric[] {
  if (kind === "quest" && activity === "learning") return ["completions", "minutes"];
  return ["completions"];
}

/** "600 min", "3 books". */
export function goalTargetText(
  t: Translate,
  goal: { metric: GoalMetric; target_value: number; unit?: string | null },
): string {
  const unit = goal.metric === "minutes" ? t("common.minutes") : (goal.unit ?? "");
  return `${goal.target_value}${unit ? ` ${unit}` : ""}`;
}

/** "60 / 600 min", "2 / 3 books". */
export function goalValueText(
  t: Translate,
  goal: Pick<Goal, "metric" | "current_value" | "target_value" | "unit">,
): string {
  return `${goal.current_value} / ${goalTargetText(t, goal)}`;
}

/** The reward for summing up after the end date, rounded like the server does. */
export function cycleReward(rules: RewardRules | undefined, done: number, total: number): number {
  if (!rules || total === 0) return 0;
  return Math.floor((rules.cycle_completion * done) / total + 0.5);
}

/** Localized hint by code; unknown codes from a newer server are skipped. */
export function recommendationText(t: Translate, recommendation: Recommendation): string | null {
  const key = `recommendation.${recommendation.code}` as MessageKey;
  const text = t(key, recommendation.params);
  return text === key ? null : text;
}

export function minutesText(t: Translate, minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return t("report.minutes", { m });
  return m === 0 ? t("report.hoursOnly", { h }) : t("report.hours", { h, m });
}
