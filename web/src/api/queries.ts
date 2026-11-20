import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { newId } from "../lib/id";
import { api, type QuestFilter } from "./endpoints";
import type {
  Completion,
  Cycle,
  CycleCompletion,
  CycleDraft,
  CyclePatch,
  GoalDraft,
  GoalPatch,
  HabitCompletion,
  HabitDraft,
  HabitPatch,
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
  /** Prefix of the cycle list and the current cycle. */
  cycles: ["cycles"] as const,
  cycleList: ["cycles", "list"] as const,
  currentCycle: ["cycles", "current"] as const,
  cycle: (id: string) => ["cycle", id] as const,
  /** Prefix of the analysis and the recommendations. */
  adaptive: ["adaptive"] as const,
  analysis: ["adaptive", "analysis"] as const,
  recommendations: ["adaptive", "recommendations"] as const,
};

/** Goal progress and links live in the cycle views. */
function invalidateCycles(queryClient: QueryClient): Promise<unknown> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: keys.cycles }),
    queryClient.invalidateQueries({ queryKey: ["cycle"] }),
  ]);
}

/** Puts the cycle view a mutation returned into the cache and refreshes the list. */
function storeCycle(queryClient: QueryClient, cycle: Cycle): Promise<unknown> {
  queryClient.setQueryData(keys.cycle(cycle.id), cycle);
  const current = queryClient.getQueryData<Cycle | null>(keys.currentCycle);
  if (current?.id === cycle.id) queryClient.setQueryData(keys.currentCycle, cycle);
  return queryClient.invalidateQueries({ queryKey: keys.cycleList });
}

/** Everything that can change when XP, quests, habits, achievements or cycles change. */
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
      keys.cycles,
      ["cycle"],
      keys.adaptive,
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
export const useCycles = () => useQuery({ queryKey: keys.cycleList, queryFn: api.cycles });
export const useCurrentCycle = () => useQuery({ queryKey: keys.currentCycle, queryFn: api.currentCycle });
export const useCycle = (id: string) => useQuery({ queryKey: keys.cycle(id), queryFn: () => api.cycle(id) });
export const useAnalysis = () => useQuery({ queryKey: keys.analysis, queryFn: api.analysis });
/** Asking refreshes the advice on the server; the plan changes only on apply. */
export const useRecommendations = () => useQuery({ queryKey: keys.recommendations, queryFn: api.recommendations });

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
    onSuccess: () => Promise.all([queryClient.invalidateQueries({ queryKey: keys.allQuests }), invalidateCycles(queryClient)]),
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
        invalidateCycles(queryClient),
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
    onSuccess: () => Promise.all([queryClient.invalidateQueries({ queryKey: keys.habits }), invalidateCycles(queryClient)]),
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
    mutationFn: (patch: HabitPatch) => api.updateHabit(id, patch),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.habits }),
        queryClient.invalidateQueries({ queryKey: keys.habit(id) }),
        invalidateCycles(queryClient),
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

export function useCreateCycle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ draft, key = newId() }: { draft: CycleDraft; key?: string }) => api.createCycle(draft, key),
    onSuccess: (cycle) => {
      // Only one cycle can be open, so the new one is the current one.
      queryClient.setQueryData(keys.cycle(cycle.id), cycle);
      queryClient.setQueryData(keys.currentCycle, cycle);
      return queryClient.invalidateQueries({ queryKey: keys.cycleList });
    },
  });
}

export function useUpdateCycle(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: CyclePatch) => api.updateCycle(id, patch),
    onSuccess: (cycle) => storeCycle(queryClient, cycle),
  });
}

export type CycleAction = "pause" | "resume" | "cancel";

export function useCycleAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, action }: { id: string; action: CycleAction }): Promise<Cycle | null> => {
      if (action === "pause") return api.pauseCycle(id);
      if (action === "resume") return api.resumeCycle(id);
      await api.cancelCycle(id);
      return null;
    },
    onSuccess: (cycle) => (cycle ? storeCycle(queryClient, cycle) : invalidateCycles(queryClient)),
  });
}

export function useCompleteCycle(onDone?: (result: CycleCompletion) => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, key = newId() }: { id: string; key?: string }) => api.completeCycle(id, key),
    onSuccess: async (result) => {
      queryClient.setQueryData(keys.cycle(result.cycle.id), result.cycle);
      onDone?.(result);
      await invalidatePlayerData(queryClient);
    },
  });
}

export function useAddGoal(cycleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (draft: GoalDraft) => api.addGoal(cycleId, draft),
    onSuccess: (cycle) => storeCycle(queryClient, cycle),
  });
}

export function useUpdateGoal(cycleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ goalId, patch }: { goalId: string; patch: GoalPatch }) => api.updateGoal(cycleId, goalId, patch),
    onSuccess: (cycle) => storeCycle(queryClient, cycle),
  });
}

export function useDeleteGoal(cycleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (goalId: string) => api.deleteGoal(cycleId, goalId),
    // Linked quests and habits lose the link (ON DELETE SET NULL).
    onSuccess: (cycle) =>
      Promise.all([
        storeCycle(queryClient, cycle),
        ...[keys.allQuests, ["quest"], keys.habits, ["habit"]].map((queryKey) =>
          queryClient.invalidateQueries({ queryKey }),
        ),
      ]),
  });
}

export function useApplyRecommendation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, changes, key = newId() }: { id: string; changes: number[]; key?: string }) =>
      api.applyRecommendation(id, changes, key),
    // Applied changes touch quests, habits or the cycle; an outdated advice gets refreshed.
    onSettled: () =>
      Promise.all([
        ...[keys.allQuests, ["quest"], keys.habits, ["habit"], keys.adaptive].map((queryKey) =>
          queryClient.invalidateQueries({ queryKey }),
        ),
        invalidateCycles(queryClient),
      ]),
  });
}

export function useDismissRecommendation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.dismissRecommendation(id),
    onSettled: () => queryClient.invalidateQueries({ queryKey: keys.adaptive }),
  });
}
