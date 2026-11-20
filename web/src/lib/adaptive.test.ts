import { describe, expect, it } from "vitest";

import type { AdaptiveRecommendation, PlanChange } from "../api/types";
import { en } from "../i18n/en";
import type { MessageKey } from "../i18n";
import { adviceText, adviceTitle, changeText, percent } from "./adaptive";

function t(key: MessageKey, params?: Record<string, string | number>): string {
  let node: unknown = en;
  for (const part of key.split(".")) node = (node as Record<string, unknown> | undefined)?.[part];
  const text = typeof node === "string" ? node : key;
  return text.replace(/\{(\w+)\}/g, (match, name: string) => (params && name in params ? String(params[name]) : match));
}

function advice(overrides: Partial<AdaptiveRecommendation>): AdaptiveRecommendation {
  return {
    id: "a",
    recommendation_type: "overload",
    status: "pending",
    title: "Lighten the plan",
    description: "",
    params: {},
    changes: [],
    created_at: "2026-11-25T09:00:00Z",
    updated_at: "2026-11-25T09:00:00Z",
    applied_at: null,
    dismissed_at: null,
    ...overrides,
  };
}

describe("advice texts", () => {
  it("names the area with the most misses", () => {
    const item = advice({ params: { done: 7, planned: 19, rate: 37, focus: "learning" } });
    expect(adviceTitle(t, item)).toBe("Lighten the plan?");
    expect(adviceText(t, item)).toBe("7 of 19 done in the last 7 days (37%). Most misses are in “Learning”.");
  });

  it("skips an unknown area", () => {
    const item = advice({ params: { done: 1, planned: 6, rate: 17, focus: null } });
    expect(adviceText(t, item)).toBe("1 of 6 done in the last 7 days (17%).");
  });

  it("uses the title of a stalled item", () => {
    const item = advice({ recommendation_type: "stalled_item", params: { title: "Meditate", done: 1, planned: 13 } });
    expect(adviceTitle(t, item)).toBe("“Meditate” is not working yet");
  });

  it("suggests a challenge when there is nothing to make harder", () => {
    const item = advice({ recommendation_type: "too_easy", params: { rate: 95 } });
    expect(adviceText(t, item)).toBe("95% of the plan in 14 days: you keep the pace. Try a challenge: it gives more XP.");
  });

  it("rounds rates to whole percents", () => {
    expect(percent(0.3684)).toBe(37);
    expect(percent(null)).toBe(0);
  });
});

describe("change texts", () => {
  const cases: [PlanChange, string][] = [
    [
      { op: "quest_minutes", quest_id: "q", title: "Kubernetes", from_minutes: 60, to_minutes: 30, from_xp: 25, to_xp: 15 },
      "“Kubernetes”: 60 → 30 min a day (reward 25 → 15 XP)",
    ],
    [
      { op: "quest_weekdays", quest_id: "q", title: "Inbox zero", from_weekdays: null, to_weekdays: [1, 3, 5] },
      "“Inbox zero”: every day → Mon Wed Fri",
    ],
    [
      {
        op: "habit_schedule",
        habit_id: "h",
        title: "Stretching",
        from_frequency: "daily",
        from_weekdays: null,
        from_times_per_week: null,
        to_times_per_week: 3,
      },
      "“Stretching”: Every day → 3× a week. The old habit goes to the archive with its history.",
    ],
    [{ op: "cycle_pause", cycle_id: "c", title: "Autumn" }, "Pause the cycle “Autumn”"],
  ];

  it.each(cases)("describes %j", (change, text) => {
    expect(changeText(t, change, "en-GB")).toBe(text);
  });

  it("shows the new deadline", () => {
    const change: PlanChange = {
      op: "quest_due",
      quest_id: "q",
      title: "Garage",
      from_due: "2026-11-27T12:00:00Z",
      to_due: "2026-12-04T12:00:00Z",
    };
    expect(changeText(t, change, "en-GB")).toBe("“Garage”: due 27 Nov → 4 Dec");
  });
});
