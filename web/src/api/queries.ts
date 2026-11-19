import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { newId } from "../lib/id";
import { api, type QuestFilter } from "./endpoints";
import type { Completion, ProfileUpdate, QuestDraft, QuestPatch, UndoResult } from "./types";

export const keys = {
  profile: ["profile"] as const,
  attributes: ["attributes"] as const,
  quests: (filter: QuestFilter) => ["quests", filter] as const,
  allQuests: ["quests"] as const,
  quest: (id: string) => ["quest", id] as const,
  history: (limit: number) => ["xp-history", limit] as const,
  statistics: ["statistics"] as const,
};

/** Everything that can change when XP or quests change. */
function invalidatePlayerData(queryClient: QueryClient): Promise<unknown> {
  return Promise.all(
    [keys.profile, keys.attributes, keys.allQuests, ["quest"], ["xp-history"], keys.statistics].map((queryKey) =>
      queryClient.invalidateQueries({ queryKey }),
    ),
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
