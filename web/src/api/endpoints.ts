import { ApiClient } from "./client";
import type {
  Achievement,
  AdaptiveRecommendation,
  Analysis,
  Attribute,
  Completion,
  Cycle,
  CycleCompletion,
  CycleDraft,
  CyclePatch,
  CycleSummary,
  GoalDraft,
  GoalPatch,
  Habit,
  HabitCompletion,
  HabitDetail,
  HabitDraft,
  HabitPatch,
  HabitUndo,
  LevelTable,
  Profile,
  ProfileUpdate,
  QuestDetail,
  QuestDraft,
  QuestList,
  QuestPatch,
  QuestStatus,
  QuestType,
  Quest,
  RecommendationApplyResult,
  RegisterData,
  SkipResult,
  Statistics,
  TokenPair,
  UndoResult,
  XpHistory,
} from "./types";

export const client = new ApiClient();

export interface QuestFilter {
  scope?: "all" | "today";
  quest_type?: QuestType;
  status?: QuestStatus;
}

export const api = {
  register: (data: RegisterData) => client.request<TokenPair>("POST", "/auth/register", { body: data, auth: false }),
  login: (email: string, password: string) =>
    client.request<TokenPair>("POST", "/auth/login", { body: { email, password }, auth: false }),
  logout: (refreshToken: string) =>
    client.request<void>("POST", "/auth/logout", { body: { refresh_token: refreshToken }, auth: false }),

  profile: () => client.request<Profile>("GET", "/player/profile"),
  updateProfile: (patch: ProfileUpdate) => client.request<Profile>("PATCH", "/player/profile", { body: patch }),
  attributes: () => client.request<Attribute[]>("GET", "/player/attributes"),
  xpHistory: (limit = 20, offset = 0) =>
    client.request<XpHistory>("GET", "/player/xp-history", { query: { limit, offset } }),
  statistics: (dateFrom?: string, dateTo?: string) =>
    client.request<Statistics>("GET", "/player/statistics", { query: { date_from: dateFrom, date_to: dateTo } }),

  quests: (filter: QuestFilter = {}) => client.request<QuestList>("GET", "/quests", { query: { ...filter } }),
  quest: (id: string) => client.request<QuestDetail>("GET", `/quests/${id}`),
  createQuest: (draft: QuestDraft, idempotencyKey: string) =>
    client.request<Quest>("POST", "/quests", { body: draft, idempotencyKey }),
  updateQuest: (id: string, patch: QuestPatch) => client.request<Quest>("PATCH", `/quests/${id}`, { body: patch }),
  deleteQuest: (id: string) => client.request<void>("DELETE", `/quests/${id}`),
  completeQuest: (id: string, idempotencyKey: string) =>
    client.request<Completion>("POST", `/quests/${id}/complete`, { idempotencyKey }),
  skipQuest: (id: string, idempotencyKey: string) =>
    client.request<SkipResult>("POST", `/quests/${id}/skip`, { idempotencyKey }),
  undoQuest: (id: string, idempotencyKey: string) =>
    client.request<UndoResult>("POST", `/quests/${id}/undo`, { idempotencyKey }),

  habits: (includeArchived = false) =>
    client.request<Habit[]>("GET", "/habits", { query: { include_archived: includeArchived } }),
  habit: (id: string) => client.request<HabitDetail>("GET", `/habits/${id}`),
  createHabit: (draft: HabitDraft, idempotencyKey: string) =>
    client.request<Habit>("POST", "/habits", { body: draft, idempotencyKey }),
  updateHabit: (id: string, patch: HabitPatch) => client.request<Habit>("PATCH", `/habits/${id}`, { body: patch }),
  archiveHabit: (id: string) => client.request<void>("DELETE", `/habits/${id}`),
  completeHabit: (id: string, idempotencyKey: string) =>
    client.request<HabitCompletion>("POST", `/habits/${id}/complete`, { idempotencyKey }),
  undoHabit: (id: string, idempotencyKey: string) =>
    client.request<HabitUndo>("POST", `/habits/${id}/undo`, { idempotencyKey }),
  freezeHabit: (id: string, day: string, idempotencyKey: string) =>
    client.request<Habit>("POST", `/habits/${id}/freeze`, { body: { day }, idempotencyKey }),

  cycles: () => client.request<CycleSummary[]>("GET", "/cycles"),
  currentCycle: () => client.request<Cycle | null>("GET", "/cycles/current"),
  cycle: (id: string) => client.request<Cycle>("GET", `/cycles/${id}`),
  createCycle: (draft: CycleDraft, idempotencyKey: string) =>
    client.request<Cycle>("POST", "/cycles", { body: draft, idempotencyKey }),
  updateCycle: (id: string, patch: CyclePatch) => client.request<Cycle>("PATCH", `/cycles/${id}`, { body: patch }),
  cancelCycle: (id: string) => client.request<void>("DELETE", `/cycles/${id}`),
  pauseCycle: (id: string) => client.request<Cycle>("POST", `/cycles/${id}/pause`),
  resumeCycle: (id: string) => client.request<Cycle>("POST", `/cycles/${id}/resume`),
  completeCycle: (id: string, idempotencyKey: string) =>
    client.request<CycleCompletion>("POST", `/cycles/${id}/complete`, { idempotencyKey }),
  addGoal: (cycleId: string, draft: GoalDraft) =>
    client.request<Cycle>("POST", `/cycles/${cycleId}/goals`, { body: draft }),
  updateGoal: (cycleId: string, goalId: string, patch: GoalPatch) =>
    client.request<Cycle>("PATCH", `/cycles/${cycleId}/goals/${goalId}`, { body: patch }),
  deleteGoal: (cycleId: string, goalId: string) =>
    client.request<Cycle>("DELETE", `/cycles/${cycleId}/goals/${goalId}`),

  analysis: () => client.request<Analysis>("GET", "/adaptive/summary"),
  recommendations: () => client.request<AdaptiveRecommendation[]>("GET", "/adaptive/recommendations"),
  applyRecommendation: (id: string, changes: number[], idempotencyKey: string) =>
    client.request<RecommendationApplyResult>("POST", `/adaptive/recommendations/${id}/apply`, {
      body: { changes },
      idempotencyKey,
    }),
  dismissRecommendation: (id: string) =>
    client.request<AdaptiveRecommendation>("POST", `/adaptive/recommendations/${id}/dismiss`),

  achievements: () => client.request<Achievement[]>("GET", "/achievements"),
  unlockedAchievements: () => client.request<Achievement[]>("GET", "/achievements/unlocked"),

  levels: (upTo = 50) => client.request<LevelTable>("GET", "/config/levels", { query: { up_to: upTo }, auth: false }),
};
