import type { Achievement, AchievementCategory, Rarity } from "../api/types";
import type { IconName } from "../components/Icon";
import type { MessageKey } from "../i18n";

type Translate = (key: MessageKey, params?: Record<string, string | number>) => string;

/** Localized title and description by code; the server's English text is the fallback. */
export function achievementText(t: Translate, achievement: Pick<Achievement, "code" | "title" | "description">) {
  const titleKey = `achievements.${achievement.code}.title` as MessageKey;
  const descriptionKey = `achievements.${achievement.code}.description` as MessageKey;
  const title = t(titleKey);
  const description = t(descriptionKey);
  return {
    title: title === titleKey ? achievement.title : title,
    description: description === descriptionKey ? achievement.description : description,
  };
}

const ICONS: Record<string, IconName> = {
  flag: "flag",
  calendar: "calendar",
  flame: "flame",
  book: "book",
  mountain: "mountain",
  dumbbell: "dumbbell",
  coins: "finance",
  briefcase: "career",
  star: "star",
};

export function achievementIcon(icon: string): IconName {
  return ICONS[icon] ?? "trophy";
}

export const RARITY_COLOR: Record<Rarity, string> = {
  common: "var(--rarity-common)",
  rare: "var(--rarity-rare)",
  epic: "var(--rarity-epic)",
  legendary: "var(--rarity-legendary)",
};

export const ACHIEVEMENT_CATEGORIES: AchievementCategory[] = [
  "consistency",
  "learning",
  "health",
  "finance",
  "career",
  "level",
];
