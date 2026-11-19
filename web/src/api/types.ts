import type { components } from "./schema";

type Schemas = components["schemas"];

export type TokenPair = Schemas["TokenPairOut"];
export type Profile = Schemas["ProfileOut"];
export type ProfileUpdate = Schemas["ProfileUpdateIn"];
export type Attribute = Schemas["AttributeOut"];
export type LedgerEntry = Schemas["LedgerEntryOut"];
export type XpHistory = Schemas["XpHistoryOut"];
export type Statistics = Schemas["StatisticsOut"];
export type LevelTable = Schemas["LevelTableOut"];
export type Quest = Schemas["QuestOut"];
export type QuestDetail = Schemas["QuestDetailOut"];
export type QuestList = Schemas["QuestListOut"];
export type Occurrence = Schemas["OccurrenceOut"];
export type ChecklistItem = Schemas["ChecklistItem"];
export type Completion = Schemas["CompletionOut"];
export type SkipResult = Schemas["SkipOut"];
export type UndoResult = Schemas["UndoOut"];
export type PlayerXp = Schemas["PlayerXpOut"];

export type Habit = Schemas["HabitOut"];
export type HabitDetail = Schemas["HabitDetailOut"];
export type HabitDay = Schemas["HabitDayOut"];
export type HabitCompletion = Schemas["HabitCompletionOut"];
export type HabitUndo = Schemas["HabitUndoOut"];
export type HabitFrequency = Schemas["HabitFrequency"];
export type Achievement = Schemas["AchievementOut"];
export type Rarity = Schemas["Rarity"];
export type AchievementCategory = Schemas["AchievementCategory"];

/** What a completion (quest or habit) reports back for celebrations. */
export interface Reward {
  xp_awarded: number;
  xp_limit_reason: XpLimitReason | null;
  player: PlayerXp;
  achievements_unlocked?: Achievement[];
}

export interface HabitDraft {
  title: string;
  description?: string | null;
  category: QuestCategory;
  frequency: HabitFrequency;
  weekdays?: number[] | null;
  times_per_week?: number | null;
}

export type QuestType = Schemas["QuestType"];
export type QuestCategory = Schemas["QuestCategory"];
export type AttributeType = Schemas["AttributeType"];
export type Activity = Schemas["Activity"];
export type Difficulty = Schemas["Difficulty"];
export type QuestStatus = Schemas["EffectiveQuestStatus"];
export type XpLimitReason = Schemas["XpLimitReason"];

/** Body of POST /quests; fields left out get the server defaults. */
export interface QuestDraft {
  title: string;
  description?: string | null;
  quest_type: QuestType;
  category: QuestCategory;
  attribute_types?: AttributeType[] | null;
  activity?: Activity;
  difficulty?: Difficulty;
  target_minutes?: number | null;
  is_recurring?: boolean | null;
  weekdays?: number[] | null;
  priority?: number;
  starts_at?: string | null;
  due_at?: string | null;
  checklist?: ChecklistItem[];
}

export interface QuestPatch {
  title?: string;
  description?: string | null;
  priority?: number;
  due_at?: string | null;
  weekdays?: number[] | null;
  checklist?: ChecklistItem[];
}

export interface RegisterData {
  email: string;
  password: string;
  display_name: string;
  timezone: string;
}

export const QUEST_TYPES: QuestType[] = ["daily", "weekly", "personal", "challenge", "milestone"];
export const CATEGORIES: QuestCategory[] = ["learning", "health", "career", "finance", "other"];
export const ATTRIBUTES: AttributeType[] = ["health", "intelligence", "career", "finance"];
export const DIFFICULTIES: Difficulty[] = ["simple", "medium", "hard", "epic"];
export const ACTIVITIES: Activity[] = ["task", "learning", "workout"];
