import { useMemo, useState, type FormEvent } from "react";

import { useCreateCycle } from "../api/queries";
import type { CycleDraft } from "../api/types";
import { useI18n } from "../i18n";
import {
  DURATION_PRESETS,
  MAX_DURATION,
  MAX_GOALS,
  MAX_START_AHEAD_DAYS,
  MIN_DURATION,
  addDays,
  goalTargetText,
  localDate,
} from "../lib/cycles";
import { formatLongDay } from "../lib/format";
import { newId } from "../lib/id";
import { useFeedback } from "./Feedback";
import { EMPTY_GOAL, GoalFields, goalDraft, goalValid, type GoalValues } from "./GoalForm";
import { Icon } from "./Icon";
import { useRewardRules } from "./QuestForm";
import { Sheet } from "./Sheet";

export function CycleForm({ onClose, onCreated }: { onClose: () => void; onCreated?: () => void }) {
  const { t, locale, errorText } = useI18n();
  const { toast } = useFeedback();
  const rules = useRewardRules();
  const create = useCreateCycle();
  // One key per opened form: a double tap or a retry cannot create two cycles.
  const [idempotencyKey] = useState(newId);
  const today = useMemo(() => localDate(), []);
  const lastStart = addDays(today, MAX_START_AHEAD_DAYS);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [preset, setPreset] = useState<number | "custom">(30);
  const [customDays, setCustomDays] = useState("60");
  const [startsOn, setStartsOn] = useState(today);
  const [goals, setGoals] = useState<GoalValues[]>([]);
  const [goal, setGoal] = useState<GoalValues>(EMPTY_GOAL);
  const [error, setError] = useState<string | null>(null);

  const duration = preset === "custom" ? Number(customDays) : preset;
  const durationValid = Number.isInteger(duration) && duration >= MIN_DURATION && duration <= MAX_DURATION;
  // ISO dates compare correctly as strings.
  const startValid = startsOn >= today && startsOn <= lastStart;
  const endsOn = durationValid && startValid ? addDays(startsOn, duration - 1) : null;
  const canAddGoal = goalValid(goal) && goals.length < MAX_GOALS;

  const addGoal = () => {
    if (!canAddGoal) return;
    setGoals((list) => [...list, goal]);
    setGoal({ ...EMPTY_GOAL, metric: goal.metric, category: goal.category });
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    // A goal that was typed in but not added yet is still meant to be part of the cycle.
    const all = canAddGoal ? [...goals, goal] : goals;
    const draft: CycleDraft = {
      title: title.trim(),
      description: description.trim() || null,
      duration_days: duration,
      // Today is left to the server: it knows the profile's time zone.
      starts_on: startsOn === today ? null : startsOn,
      goals: all.map(goalDraft),
    };
    create.mutate(
      { draft, key: idempotencyKey },
      {
        onSuccess: () => {
          toast(t("cycles.created"));
          onCreated?.();
          onClose();
        },
        onError: (err) => setError(errorText(err)),
      },
    );
  };

  return (
    <Sheet title={t("cycles.newCycle")} onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <label className="field">
          <span>{t("form.title")}</span>
          <input
            className="input"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder={t("cycles.titlePlaceholder")}
            maxLength={200}
            required
          />
        </label>

        <div className="field">
          <span>{t("cycles.duration")}</span>
          <div className="choice-grid">
            {DURATION_PRESETS.map((days) => (
              <button
                key={days}
                type="button"
                className="choice num"
                aria-pressed={preset === days}
                onClick={() => setPreset(days)}
              >
                {t("cycles.days", { n: days })}
              </button>
            ))}
            <button
              type="button"
              className="choice"
              aria-pressed={preset === "custom"}
              onClick={() => setPreset("custom")}
            >
              {t("cycles.custom")}
            </button>
          </div>
          {preset === "custom" && (
            <>
              <input
                className="input num"
                type="number"
                inputMode="numeric"
                min={MIN_DURATION}
                max={MAX_DURATION}
                value={customDays}
                onChange={(event) => setCustomDays(event.target.value)}
                aria-label={t("cycles.duration")}
              />
              <small className={durationValid ? "faint" : "form-hint-error"}>{t("cycles.customHint")}</small>
            </>
          )}
        </div>

        <label className="field">
          <span>{t("cycles.startsOn")}</span>
          <input
            className="input"
            type="date"
            min={today}
            max={lastStart}
            value={startsOn}
            onChange={(event) => setStartsOn(event.target.value)}
            required
          />
          <small className={startValid ? "faint" : "form-hint-error"}>
            {endsOn ? t("cycles.endsOn", { date: formatLongDay(endsOn, locale) }) : t("cycles.startHint")}
          </small>
        </label>

        <label className="field">
          <span>
            {t("form.description")} <span className="faint">({t("common.optional")})</span>
          </span>
          <textarea
            className="textarea"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder={t("cycles.descriptionPlaceholder")}
            maxLength={5000}
          />
        </label>

        <div className="field">
          <span>
            {t("cycles.goals")} <span className="faint num">({goals.length}/{MAX_GOALS})</span>
          </span>
          {goals.map((item, index) => (
            <div key={index} className="goal-draft">
              <div className="quest-main">
                <div className="quest-title">{item.title}</div>
                <div className="faint small num">
                  {t(`goalMetric.${item.metric}`)} · {goalTargetText(t, goalDraft(item))}
                </div>
              </div>
              <button
                type="button"
                className="icon-btn"
                aria-label={t("cycles.removeGoal")}
                title={t("cycles.removeGoal")}
                onClick={() => setGoals((list) => list.filter((_, i) => i !== index))}
              >
                <Icon name="close" />
              </button>
            </div>
          ))}
          {goals.length < MAX_GOALS && (
            <div className="goal-adder">
              <GoalFields values={goal} onChange={setGoal} onEnter={addGoal} />
              <button className="btn btn-small" type="button" onClick={addGoal} disabled={!canAddGoal}>
                <Icon name="plus" />
                {t("cycles.addGoal")}
              </button>
            </div>
          )}
          <small className="faint">{t("cycles.goalsLater")}</small>
        </div>

        {error && <div className="form-error">{error}</div>}

        <div>
          <span className="chip chip-gold num">
            {t("form.rewardPreview", { xp: rules.data?.cycle_completion ?? 200 })}
          </span>
          <p className="faint small" style={{ marginTop: 6 }}>
            {t("cycles.rewardHint", { xp: rules.data?.cycle_completion ?? 200 })}
          </p>
        </div>
        <button
          className="btn btn-primary btn-block"
          type="submit"
          disabled={create.isPending || !title.trim() || !durationValid || !startValid}
        >
          {t("cycles.start")}
        </button>
      </form>
    </Sheet>
  );
}
