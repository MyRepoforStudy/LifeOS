import { describe, expect, it } from "vitest";

import { en } from "../i18n/en";
import type { MessageKey } from "../i18n";
import {
  acceptedMetrics,
  addDays,
  cycleReward,
  goalValueText,
  isOpen,
  minutesText,
  recommendationText,
} from "./cycles";
import type { RewardRules } from "./rewards";

// A tiny stand-in for the i18n provider: English texts with {param} substitution.
function t(key: MessageKey, params?: Record<string, string | number>): string {
  let node: unknown = en;
  for (const part of key.split(".")) node = (node as Record<string, unknown> | undefined)?.[part];
  const text = typeof node === "string" ? node : key;
  return text.replace(/\{(\w+)\}/g, (match, name: string) => (params && name in params ? String(params[name]) : match));
}

const rules = { cycle_completion: 200 } as RewardRules;

describe("cycleReward", () => {
  it("is proportional to the goals reached and rounded like the server", () => {
    expect(cycleReward(rules, 1, 2)).toBe(100);
    expect(cycleReward(rules, 1, 3)).toBe(67);
    expect(cycleReward(rules, 2, 3)).toBe(133);
    expect(cycleReward(rules, 3, 3)).toBe(200);
  });

  it("is zero without goals or rules", () => {
    expect(cycleReward(rules, 0, 0)).toBe(0);
    expect(cycleReward(undefined, 1, 1)).toBe(0);
  });
});

describe("dates", () => {
  it("adds days across month and year ends", () => {
    expect(addDays("2026-11-18", 29)).toBe("2026-12-17");
    expect(addDays("2026-12-20", 30)).toBe("2027-01-19");
  });
});

describe("texts", () => {
  it("shows goal values with their unit", () => {
    expect(goalValueText(t, { metric: "minutes", current_value: 60, target_value: 600, unit: null })).toBe(
      "60 / 600 min",
    );
    expect(goalValueText(t, { metric: "manual", current_value: 2, target_value: 3, unit: "books" })).toBe(
      "2 / 3 books",
    );
    expect(goalValueText(t, { metric: "completions", current_value: 1, target_value: 5, unit: null })).toBe("1 / 5");
  });

  it("formats learning time", () => {
    expect(minutesText(t, 45)).toBe("45 min");
    expect(minutesText(t, 120)).toBe("2 h");
    expect(minutesText(t, 150)).toBe("2 h 30 min");
  });

  it("localizes recommendations and skips unknown codes", () => {
    expect(recommendationText(t, { code: "stalled_goal", params: { title: "CKA" } })).toBe(
      "No progress on “CKA”. Break it into small daily steps.",
    );
    expect(recommendationText(t, { code: "something_new" })).toBeNull();
  });
});

describe("rules", () => {
  it("lets only learning quests feed minutes goals", () => {
    expect(acceptedMetrics("quest", "learning")).toEqual(["completions", "minutes"]);
    expect(acceptedMetrics("quest", "workout")).toEqual(["completions"]);
    expect(acceptedMetrics("habit")).toEqual(["completions"]);
  });

  it("treats finished but not wrapped up cycles as open", () => {
    expect(isOpen({ status: "finished" })).toBe(true);
    expect(isOpen({ status: "planned" })).toBe(true);
    expect(isOpen({ status: "completed" })).toBe(false);
    expect(isOpen({ status: "cancelled" })).toBe(false);
  });
});
