import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { newId } from "../lib/id";
import { api, type QuestFilter } from "./endpoints";
import type {
  Completion,
  HabitCompletion,
  HabitDraft,
  HabitUndo,
  ProfileUpdate,
  QuestDraft,
  QuestPatch,
  UndoResult,
} from "./types";

export const keys = {
  profile: ["profile"] as const,
  attributes: ["attributes"] as const,
  quests: (filter: QuestFilter) => ["quests", filter] as const,
  allQuests: ["quests"] as const,
  quest: (id: string) => ["quest", id] as const,
  history: (limit: number) => ["xp-history", limit] as const,
  statistics: ["statistics"] as const,
  habits: ["habits"] as const,
  habit: (id: string) => ["habit", id] as const,
  achievements: ["achievements"] as const,
};

/** Everything that can change when XP, quests, habits or achievements change. */
function invalidatePlayerData(queryClient: QueryClient): Promise<unknown> {
  return Promise.all(
    [
      keys.profile,
      keys.attributes,
      keys.allQuests,
      ["quest"],
      ["xp-history"],
      keys.statistics,
      keys.habits,
      ["habit"],
      keys.achievements,
    ].map((queryKey) => queryClient.invalidateQueries({ queryKey })),
  );
}

export const useProfile = () => useQuery({ queryKey: keys.profile, queryFn: api.profile });
export const useAttributes = () => useQuery({ queryKey: keys.attributes, queryFn: api.attributes });
export const useQuests = (filter: QuestFilter) =>
  useQuery({ queryKey: keys.quests(filter), queryFn: () => api.quests(filter) });
export const useQuest = (id: string) => useQuery({ queryKey: keys.quest(id), queryFn: () => api.quest(id) });
export const useXpHistory = (limit = 8) =>
  useQuery({ queryKey: keys.history(limit), queryFn: () => api.xpHistory(limit) });
export const useStatistics = () => useQuery({ queryKey: keys.statistics, queryFn: () => api.statistics() });
export const useHabits = () => useQuery({ queryKey: keys.habits, queryFn: () => api.habits() });
export const useHabit = (id: string) => useQuery({ queryKey: keys.habit(id), queryFn: () => api.habit(id) });
export const useAchievements = () => useQuery({ queryKey: keys.achievements, queryFn: api.achievements });

/** Each user action gets one Idempotency-Key, reused if the request is retried. */
export function useCompleteQuest(onDone?: (result: Completion) => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, key = newId() }: { id: string; key?: string }) => api.completeQuest(id, key),
    onSuccess: async (result) => {
      onDone?.(result);
      await invalidatePlayerData(queryClient);
    },
  });
}

export function useSkipQuest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, key = newId() }: { id: string; key?: string }) => api.skipQuest(id, key),
    onSuccess: () => invalidatePlayerData(queryClient),
  });
}

export function useUndoQuest(onDone?: (result: UndoResult) => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, key = newId() }: { id: string; key?: string }) => api.undoQuest(id, key),
    onSuccess: async (result) => {
      onDone?.(result);
      await invalidatePlayerData(queryClient);
    },
  });
}

export function useCreateQuest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ draft, key = newId() }: { draft: QuestDraft; key?: string }) => api.createQuest(draft, key),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.allQuests }),
  });
}

export function useUpdateQuest(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: QuestPatch) => api.updateQuest(id, patch),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.quest(id) }),
        queryClient.invalidateQueries({ queryKey: keys.allQuests }),
      ]),
  });
}

export function useDeleteQuest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteQuest(id),
    onSuccess: () => invalidatePlayerData(queryClient),
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: ProfileUpdate) => api.updateProfile(patch),
    onSuccess: (profile) => queryClient.setQueryData(keys.profile, profile),
  });
}

export function useCreateHabit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ draft, key = newId() }: { draft: HabitDraft; key?: string }) => api.createHabit(draft, key),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.habits }),
  });
}

export function useCompleteHabit(onDone?: (result: HabitCompletion) => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, key = newId() }: { id: string; key?: string }) => api.completeHabit(id, key),
    onSuccess: async (result) => {
      onDone?.(result);
      await invalidatePlayerData(queryClient);
    },
  });
}

export function useUndoHabit(onDone?: (result: HabitUndo) => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, key = newId() }: { id: string; key?: string }) => api.undoHabit(id, key),
    onSuccess: async (result) => {
      onDone?.(result);
      await invalidatePlayerData(queryClient);
    },
  });
}

export function useFreezeHabit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, day, key = newId() }: { id: string; day: string; key?: string }) =>
      api.freezeHabit(id, day, key),
    onSuccess: (_, { id }) =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.habits }),
        queryClient.invalidateQueries({ queryKey: keys.habit(id) }),
        queryClient.invalidateQueries({ queryKey: keys.achievements }),
      ]),
  });
}

export function useUpdateHabit(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: { title?: string; description?: string | null }) => api.updateHabit(id, patch),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.habits }),
        queryClient.invalidateQueries({ queryKey: keys.habit(id) }),
      ]),
  });
}

export function useArchiveHabit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.archiveHabit(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.habits }),
  });
}
