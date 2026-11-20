import { useState, type FormEvent, type KeyboardEvent } from "react";

import { useAddGoal, useDeleteGoal, useUpdateGoal } from "../api/queries";
import { CATEGORIES, GOAL_METRICS, type Goal, type GoalDraft, type GoalMetric, type QuestCategory } from "../api/types";
import { useI18n } from "../i18n";
import { MAX_GOAL_VALUE } from "../lib/cycles";
import { useFeedback } from "./Feedback";
import { Icon } from "./Icon";
import { Sheet } from "./Sheet";

/** Form state of a goal; numbers stay strings while they are being typed. */
export interface GoalValues {
  title: string;
  category: QuestCategory;
  metric: GoalMetric;
  target: string;
  unit: string;
}

export const EMPTY_GOAL: GoalValues = { title: "", category: "learning", metric: "completions", target: "10", unit: "" };

function validNumber(value: string, min: number): boolean {
  const number = Number(value);
  return value.trim() !== "" && Number.isInteger(number) && number >= min && number <= MAX_GOAL_VALUE;
}

export function goalValid(values: GoalValues): boolean {
  return values.title.trim().length > 0 && validNumber(values.target, 1);
}

export function goalDraft(values: GoalValues): GoalDraft {
  return {
    title: values.title.trim(),
    category: values.category,
    metric: values.metric,
    target_value: Number(values.target),
    unit: values.metric === "manual" ? values.unit.trim() || null : null,
  };
}

interface GoalFieldsProps {
  values: GoalValues;
  onChange: (values: GoalValues) => void;
  /** The area and the metric cannot change once the goal exists. */
  fixedKind?: boolean;
  /** Enter in a text field; inside another form it must not submit that form. */
  onEnter?: () => void;
}

export function GoalFields({ values, onChange, fixedKind, onEnter }: GoalFieldsProps) {
  const { t } = useI18n();
  const set = (patch: Partial<GoalValues>) => onChange({ ...values, ...patch });
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" && onEnter) {
      event.preventDefault();
      onEnter();
    }
  };

  return (
    <>
      <label className="field">
        <span>{t("cycles.goal")}</span>
        <input
          className="input"
          value={values.title}
          onChange={(event) => set({ title: event.target.value })}
          onKeyDown={onKeyDown}
          placeholder={t("cycles.goalTitlePlaceholder")}
          maxLength={200}
        />
      </label>

      {!fixedKind && (
        <>
          <div className="field">
            <span>{t("cycles.metric")}</span>
            <div className="segmented">
              {GOAL_METRICS.map((metric) => (
                <button key={metric} type="button" aria-pressed={values.metric === metric} onClick={() => set({ metric })}>
                  {t(`goalMetric.${metric}`)}
                </button>
              ))}
            </div>
            <small className="faint">{t(`goalMetricHint.${values.metric}`)}</small>
          </div>

          <div className="field">
            <span>{t("form.category")}</span>
            <div className="choice-grid">
              {CATEGORIES.map((category) => (
                <button
                  key={category}
                  type="button"
                  className="choice"
                  aria-pressed={values.category === category}
                  onClick={() => set({ category })}
                >
                  {t(`category.${category}`)}
                </button>
              ))}
            </div>
          </div>
        </>
      )}

      <div className="field-pair">
        <label className="field">
          <span>{values.metric === "minutes" ? t("cycles.targetMinutes") : t("cycles.target")}</span>
          <input
            className="input num"
            type="number"
            inputMode="numeric"
            min={1}
            max={MAX_GOAL_VALUE}
            value={values.target}
            onChange={(event) => set({ target: event.target.value })}
            onKeyDown={onKeyDown}
          />
        </label>
        {values.metric === "manual" && (
          <label className="field">
            <span>
              {t("cycles.unit")} <span className="faint">({t("common.optional")})</span>
            </span>
            <input
              className="input"
              value={values.unit}
              onChange={(event) => set({ unit: event.target.value })}
              onKeyDown={onKeyDown}
              placeholder={t("cycles.unitPlaceholder")}
              maxLength={30}
            />
          </label>
        )}
      </div>
    </>
  );
}

function toValues(goal: Goal): GoalValues {
  return {
    title: goal.title,
    category: goal.category,
    metric: goal.metric,
    target: String(goal.target_value),
    unit: goal.unit ?? "",
  };
}

/** Adds a goal to an open cycle, or edits one (with its current value for manual goals). */
export function GoalForm({ cycleId, goal, onClose }: { cycleId: string; goal?: Goal; onClose: () => void }) {
  const { t, errorText } = useI18n();
  const { toast } = useFeedback();
  const add = useAddGoal(cycleId);
  const update = useUpdateGoal(cycleId);
  const remove = useDeleteGoal(cycleId);
  const [values, setValues] = useState<GoalValues>(goal ? toValues(goal) : EMPTY_GOAL);
  const [current, setCurrent] = useState(goal ? String(goal.current_value) : "0");
  const [error, setError] = useState<string | null>(null);

  const manual = values.metric === "manual";
  const editsCurrent = Boolean(goal) && manual;
  const valid = goalValid(values) && (!editsCurrent || validNumber(current, 0));
  const busy = add.isPending || update.isPending || remove.isPending;
  const onError = (err: unknown) => setError(errorText(err));
  const done = () => {
    toast(t("detail.saved"));
    onClose();
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const draft = goalDraft(values);
    if (!goal) {
      add.mutate(draft, { onSuccess: done, onError });
      return;
    }
    update.mutate(
      {
        goalId: goal.id,
        patch: {
          title: draft.title,
          target_value: draft.target_value,
          ...(manual ? { unit: draft.unit, current_value: Number(current) } : {}),
        },
      },
      { onSuccess: done, onError },
    );
  };

  const onDelete = () => {
    if (!goal || !window.confirm(t("cycles.deleteGoalConfirm"))) return;
    remove.mutate(goal.id, {
      onSuccess: () => {
        toast(t("cycles.goalDeleted"));
        onClose();
      },
      onError,
    });
  };

  return (
    <Sheet title={goal ? goal.title : t("cycles.addGoal")} onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <GoalFields values={values} onChange={setValues} fixedKind={Boolean(goal)} />

        {editsCurrent && (
          <label className="field">
            <span>{t("cycles.current")}</span>
            <input
              className="input num"
              type="number"
              inputMode="numeric"
              min={0}
              max={MAX_GOAL_VALUE}
              value={current}
              onChange={(event) => setCurrent(event.target.value)}
            />
          </label>
        )}
        {goal && !manual && <p className="faint small">{t(`goalMetricHint.${goal.metric}`)}</p>}

        {error && <div className="form-error">{error}</div>}

        <button className="btn btn-primary btn-block" type="submit" disabled={busy || !valid}>
          {goal ? t("common.save") : t("cycles.addGoal")}
        </button>
        {goal && (
          <button className="btn btn-danger btn-block" type="button" onClick={onDelete} disabled={busy}>
            <Icon name="trash" />
            {t("cycles.deleteGoal")}
          </button>
        )}
      </form>
    </Sheet>
  );
}
