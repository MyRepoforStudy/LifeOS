import { ApiClient } from "./client";
import type {
  Attribute,
  Completion,
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

  levels: (upTo = 50) => client.request<LevelTable>("GET", "/config/levels", { query: { up_to: upTo }, auth: false }),
};
