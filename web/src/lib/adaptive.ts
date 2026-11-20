import { CATEGORIES, type AdaptiveRecommendation, type PlanChange, type QuestCategory } from "../api/types";
import type { MessageKey } from "../i18n";
import { formatDay } from "./format";
import { frequencyText } from "./habits";

type Translate = (key: MessageKey, params?: Record<string, string | number>) => string;
type Params = AdaptiveRecommendation["params"];

export const CATEGORY_COLOR: Record<QuestCategory, string> = {
  learning: "var(--attr-intelligence)",
  health: "var(--attr-health)",
  career: "var(--attr-career)",
  finance: "var(--attr-finance)",
  other: "var(--text-faint)",
};

export function percent(rate: number | null | undefined): number {
  return Math.round((rate ?? 0) * 100);
}

const num = (params: Params, key: string): number => Number(params[key] ?? 0);
const str = (params: Params, key: string): string => String(params[key] ?? "");

function categoryName(t: Translate, value: string): string | null {
  const category = CATEGORIES.find((item) => item === value);
  return category ? t(`category.${category}`) : null;
}

/** Localized title by type and params; the server's English text is the fallback. */
export function adviceTitle(t: Translate, advice: AdaptiveRecommendation): string {
  const titles: Record<AdaptiveRecommendation["recommendation_type"], () => string> = {
    overload: () => t("advice.overload.title"),
    stalled_item: () => t("advice.stalled_item.title", { title: str(advice.params, "title") }),
    too_easy: () => t("advice.too_easy.title"),
    rest: () => t("advice.rest.title"),
  };
  return titles[advice.recommendation_type]?.() ?? advice.title;
}

export function adviceText(t: Translate, advice: AdaptiveRecommendation): string {
  const p = advice.params;
  switch (advice.recommendation_type) {
    case "overload": {
      const text = t("advice.overload.text", { done: num(p, "done"), planned: num(p, "planned"), rate: num(p, "rate") });
      const focus = categoryName(t, str(p, "focus"));
      return focus ? `${text} ${t("advice.overload.focus", { focus })}` : text;
    }
    case "stalled_item":
      return t("advice.stalled_item.text", { done: num(p, "done"), planned: num(p, "planned") });
    case "too_easy": {
      const text = t("advice.too_easy.text", { rate: num(p, "rate") });
      return advice.changes.length === 0 ? `${text} ${t("advice.too_easy.noChanges")}` : text;
    }
    case "rest":
      return t("advice.rest.text", { days: num(p, "days"), cycle: str(p, "cycle") });
    default:
      return advice.description;
  }
}

function weekdaysText(t: Translate, days: number[] | null): string {
  return days && days.length > 0
    ? days.map((day) => t(`weekday.${day}` as MessageKey)).join(" ")
    : t("change.everyDay");
}

export function changeText(t: Translate, change: PlanChange, locale: string): string {
  switch (change.op) {
    case "quest_minutes":
      return t("change.quest_minutes", {
        title: change.title,
        from: change.from_minutes,
        to: change.to_minutes,
        fromXp: change.from_xp,
        toXp: change.to_xp,
      });
    case "quest_weekdays":
      return t("change.quest_weekdays", {
        title: change.title,
        from: weekdaysText(t, change.from_weekdays),
        to: weekdaysText(t, change.to_weekdays),
      });
    case "quest_due":
      return t("change.quest_due", {
        title: change.title,
        from: change.from_due ? formatDay(change.from_due, locale) : t("change.noDue"),
        to: formatDay(change.to_due, locale),
      });
    case "habit_schedule":
      return t("change.habit_schedule", {
        title: change.title,
        from: frequencyText(t, {
          frequency: change.from_frequency,
          weekdays: change.from_weekdays,
          times_per_week: change.from_times_per_week,
        }),
        to: t("habits.timesPerWeek", { n: change.to_times_per_week }),
      });
    case "cycle_pause":
      return t("change.cycle_pause", { title: change.title });
  }
}
