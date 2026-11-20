import type { Habit } from "../api/types";
import type { MessageKey } from "../i18n";

type Translate = (key: MessageKey, params?: Record<string, string | number>) => string;

export function frequencyText(t: Translate, habit: Pick<Habit, "frequency" | "weekdays" | "times_per_week">): string {
  if (habit.frequency === "weekly") return t("habits.timesPerWeek", { n: habit.times_per_week ?? 1 });
  if (habit.frequency === "weekdays") {
    return (habit.weekdays ?? []).map((day) => t(`weekday.${day}` as MessageKey)).join(" ");
  }
  return t("habits.everyDay");
}

export function streakText(t: Translate, streak: Habit["streak"], value = streak.current): string {
  return streak.unit === "week" ? t("habits.streakWeeks", { n: value }) : t("habits.streakDays", { n: value });
}
