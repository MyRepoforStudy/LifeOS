import { useCurrentCycle } from "../api/queries";
import type { Goal, GoalMetric } from "../api/types";
import { useI18n } from "../i18n";

/** Goals of the open cycle that a quest or habit with these metrics can feed. */
export function useLinkableGoals(accepts: readonly GoalMetric[]): { all: Goal[]; linkable: Goal[] } {
  const { data: cycle } = useCurrentCycle();
  const all = cycle?.goals ?? [];
  return { all, linkable: all.filter((goal) => accepts.includes(goal.metric)) };
}

interface GoalSelectProps {
  accepts: readonly GoalMetric[];
  value: string | null;
  onChange: (goalId: string | null) => void;
  disabled?: boolean;
}

/** Links a quest or habit to a goal of the current cycle; hidden when there is nothing to pick. */
export function GoalSelect({ accepts, value, onChange, disabled }: GoalSelectProps) {
  const { t } = useI18n();
  const { all, linkable } = useLinkableGoals(accepts);
  if (linkable.length === 0 && !value) return null;
  const listed = linkable.some((goal) => goal.id === value);
  // A link to a goal that is not offered (a past cycle) stays visible instead of looking like "no goal".
  const other = value && !listed ? (all.find((goal) => goal.id === value)?.title ?? t("cycles.pastGoal")) : null;

  return (
    <label className="field">
      <span>
        {t("cycles.goalLink")} <span className="faint">({t("common.optional")})</span>
      </span>
      <select
        className="select"
        value={value ?? ""}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value || null)}
      >
        <option value="">{t("cycles.noGoal")}</option>
        {other && value && <option value={value}>{other}</option>}
        {linkable.map((goal) => (
          <option key={goal.id} value={goal.id}>
            {goal.title}
          </option>
        ))}
      </select>
      <small className="faint">{t("cycles.goalLinkHint")}</small>
    </label>
  );
}

interface GoalLinkCardProps {
  accepts: readonly GoalMetric[];
  value: string | null;
  onSave: (goalId: string | null) => void;
  saving: boolean;
}

/** The goal link of an existing quest or habit; a change is saved right away. */
export function GoalLinkCard({ accepts, value, onSave, saving }: GoalLinkCardProps) {
  const { linkable } = useLinkableGoals(accepts);
  if (linkable.length === 0 && !value) return null;
  return (
    <section className="card">
      <GoalSelect accepts={accepts} value={value} onChange={onSave} disabled={saving} />
    </section>
  );
}
