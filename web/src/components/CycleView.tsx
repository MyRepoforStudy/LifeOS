import { useState, type CSSProperties, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router";

import { useCompleteCycle, useCycleAction, useUpdateCycle, useUpdateGoal, type CycleAction } from "../api/queries";
import type { Cycle, CycleReport, Goal } from "../api/types";
import { useI18n, type MessageKey } from "../i18n";
import { RARITY_COLOR, achievementText } from "../lib/achievements";
import {
  MAX_GOALS,
  MAX_GOAL_VALUE,
  cycleReward,
  goalValueText,
  isOpen,
  minutesText,
  recommendationText,
  statusChip,
} from "../lib/cycles";
import { formatDay, formatLongDay, formatNumber } from "../lib/format";
import { useFeedback } from "./Feedback";
import { GoalForm } from "./GoalForm";
import { Icon } from "./Icon";
import { ProgressBar } from "./ProgressBar";
import { useRewardRules } from "./QuestForm";
import { ATTRIBUTE_COLOR } from "./QuestRow";

type Translate = ReturnType<typeof useI18n>["t"];
type GoalLike = Pick<Goal, "title" | "metric" | "target_value" | "current_value" | "unit" | "done">;

function Stat({ label, value, gold }: { label: string; value: ReactNode; gold?: boolean }) {
  return (
    <div className="stat">
      <div className="faint small">{label}</div>
      <div className={gold ? "stat-value num gold" : "stat-value num"}>{value}</div>
    </div>
  );
}

function CycleTitle({ cycle }: { cycle: Cycle }) {
  const { t, errorText } = useI18n();
  const { toast } = useFeedback();
  const update = useUpdateCycle(cycle.id);
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(cycle.title);
  const [description, setDescription] = useState(cycle.description ?? "");

  if (!editing) {
    return (
      <div className="spread" style={{ alignItems: "flex-start" }}>
        <div className="stack" style={{ gap: 6, minWidth: 0 }}>
          <h1>{cycle.title}</h1>
          {cycle.description && <p className="muted">{cycle.description}</p>}
        </div>
        {isOpen(cycle) && (
          <button
            className="icon-btn"
            aria-label={t("common.edit")}
            title={t("common.edit")}
            onClick={() => setEditing(true)}
          >
            <Icon name="edit" />
          </button>
        )}
      </div>
    );
  }

  const save = (event: FormEvent) => {
    event.preventDefault();
    update.mutate(
      { title: title.trim(), description: description.trim() || null },
      {
        onSuccess: () => {
          setEditing(false);
          toast(t("detail.saved"));
        },
        onError: (error) => toast(errorText(error), "error"),
      },
    );
  };

  return (
    <form className="stack" onSubmit={save}>
      <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} required />
      <textarea
        className="textarea"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder={t("cycles.descriptionPlaceholder")}
        maxLength={5000}
      />
      <div className="row">
        <button className="btn btn-primary btn-small" type="submit" disabled={!title.trim() || update.isPending}>
          {t("common.save")}
        </button>
        <button className="btn btn-ghost btn-small" type="button" onClick={() => setEditing(false)}>
          {t("common.cancel")}
        </button>
      </div>
    </form>
  );
}

/** What the cycle needs from the player right now, if anything. */
export function CycleNote({ cycle }: { cycle: Cycle }) {
  const { t, locale } = useI18n();
  if (cycle.status === "planned") {
    return <div className="note">{t("cycles.plannedNote", { date: formatLongDay(cycle.starts_on, locale) })}</div>;
  }
  if (cycle.status === "paused" && cycle.paused_on) {
    return (
      <div className="note frozen">{t("cycles.pausedNote", { date: formatLongDay(cycle.paused_on, locale) })}</div>
    );
  }
  if (cycle.status === "finished") {
    return <div className="note gold">{t("cycles.timeUpNote", { date: formatLongDay(cycle.ends_on, locale) })}</div>;
  }
  if (cycle.status === "active" && cycle.reached_end) {
    return <div className="note gold">{t("cycles.lastDayNote")}</div>;
  }
  if (cycle.status === "cancelled") return <div className="note">{t("cycles.cancelledNote")}</div>;
  return null;
}

function CycleActions({ cycle }: { cycle: Cycle }) {
  const { t, errorText } = useI18n();
  const { toast, celebrate } = useFeedback();
  const navigate = useNavigate();
  const rules = useRewardRules();
  const action = useCycleAction();
  const complete = useCompleteCycle((result) => {
    toast(t("cycles.completed"));
    celebrate(result);
    // The report lives on the cycle page; the cycles tab shows the next cycle.
    navigate(`/cycles/${result.cycle.id}`);
  });
  const busy = action.isPending || complete.isPending;
  const onError = (error: unknown) => toast(errorText(error), "error");
  // Paused on its last day: resuming happens on wrap-up and still counts as reaching the end.
  const ready = cycle.reached_end || (cycle.status === "paused" && cycle.days_left === 0);

  const run = (kind: CycleAction, done: MessageKey) =>
    action.mutate({ id: cycle.id, action: kind }, { onSuccess: () => toast(t(done)), onError });

  const onCancel = () => {
    if (window.confirm(t("cycles.cancelConfirm"))) run("cancel", "cycles.cancelled");
  };

  const onFinish = () => {
    let message: string;
    if (!ready) message = t("cycles.finishEarlyConfirm", { n: cycle.days_left });
    else if (cycle.goals_total === 0) message = t("cycles.finishNoGoalsConfirm");
    else {
      const xp = cycleReward(rules.data, cycle.goals_done, cycle.goals_total);
      message = t("cycles.finishConfirm", { xp, done: cycle.goals_done, total: cycle.goals_total });
    }
    if (window.confirm(message)) complete.mutate({ id: cycle.id }, { onError });
  };

  return (
    <div className="row" style={{ flexWrap: "wrap" }}>
      {cycle.status === "paused" && (
        <button className="btn btn-primary" onClick={() => run("resume", "cycles.resumed")} disabled={busy}>
          <Icon name="play" />
          {t("cycles.resume")}
        </button>
      )}
      {cycle.status !== "planned" && (
        <button className={ready ? "btn btn-primary" : "btn"} onClick={onFinish} disabled={busy}>
          <Icon name="flag" />
          {t("cycles.finish")}
        </button>
      )}
      {cycle.status === "active" && !cycle.reached_end && (
        <button className="btn" onClick={() => run("pause", "cycles.paused")} disabled={busy}>
          <Icon name="pause" />
          {t("cycles.pause")}
        </button>
      )}
      <button className="btn btn-danger" onClick={onCancel} disabled={busy} style={{ marginLeft: "auto" }}>
        <Icon name="close" />
        {t("cycles.cancel")}
      </button>
    </div>
  );
}

function CycleHero({ cycle }: { cycle: Cycle }) {
  const { t, locale } = useI18n();
  const rules = useRewardRules();
  const open = isOpen(cycle);
  const running = open && cycle.status !== "planned";

  return (
    <section className="card stack">
      <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
        <span className={statusChip(cycle.status)}>{t(`cycleStatus.${cycle.status}`)}</span>
        {cycle.finished_early && <span className="chip">{t("cycles.finishedEarly")}</span>}
        <span className="chip">
          <Icon name="calendar" width={13} height={13} />
          {t("cycles.period", { from: formatDay(cycle.starts_on, locale), to: formatDay(cycle.ends_on, locale) })}
        </span>
        <span className="chip num">{t("cycles.days", { n: cycle.duration_days })}</span>
      </div>

      <CycleTitle key={`${cycle.title}|${cycle.description ?? ""}`} cycle={cycle} />

      {running && (
        <div className="stack" style={{ gap: 8 }}>
          <div className="spread">
            <span className="cycle-day num">
              {t("cycles.dayOf", { day: cycle.day_number, total: cycle.duration_days })}
            </span>
            {cycle.days_left > 0 && (
              <span className="muted small num">{t("cycles.daysLeft", { n: cycle.days_left })}</span>
            )}
          </div>
          <ProgressBar value={cycle.time_progress} label={t("cycles.duration")} />
        </div>
      )}

      <CycleNote cycle={cycle} />

      {open && (
        <>
          <div className="stat-trio">
            <Stat label={t("cycles.goals")} value={`${cycle.goals_done}/${cycle.goals_total}`} />
            <Stat label={t("cycles.xpInCycle")} value={formatNumber(cycle.xp_in_cycle, locale)} />
            <Stat
              label={t("cycles.reward")}
              value={`+${cycleReward(rules.data, cycle.goals_done, cycle.goals_total)}`}
              gold
            />
          </div>
          <p className="faint small">{t("cycles.rewardHint", { xp: rules.data?.cycle_completion ?? 200 })}</p>
          <CycleActions cycle={cycle} />
        </>
      )}
    </section>
  );
}

function GoalRow({ goal, hint, children }: { goal: GoalLike; hint?: string; children?: ReactNode }) {
  const { t } = useI18n();
  return (
    <div className={goal.done ? "goal-row done" : "goal-row"}>
      <span className="goal-mark" aria-hidden="true">
        <Icon name={goal.done ? "check" : "flag"} />
      </span>
      <div className="goal-main">
        <div className="spread" style={{ alignItems: "baseline" }}>
          <span className="quest-title">{goal.title}</span>
          <span className="goal-value small num">{goalValueText(t, goal)}</span>
        </div>
        <ProgressBar value={Math.min(1, goal.current_value / goal.target_value)} thin label={goal.title} />
        {hint && <div className="faint small">{hint}</div>}
      </div>
      {children}
    </div>
  );
}

function linkHint(t: Translate, goal: Goal): string {
  if (goal.metric === "manual") return t("cycles.manualHint");
  if (goal.linked_quests + goal.linked_habits === 0) return t("cycles.notLinked");
  return t("cycles.linked", { quests: goal.linked_quests, habits: goal.linked_habits });
}

function OpenGoalRow({ cycleId, goal, onEdit }: { cycleId: string; goal: Goal; onEdit: () => void }) {
  const { t, errorText } = useI18n();
  const { toast } = useFeedback();
  const update = useUpdateGoal(cycleId);

  const increment = () => {
    const next = goal.current_value + 1;
    update.mutate(
      { goalId: goal.id, patch: { current_value: next } },
      {
        onSuccess: () => {
          if (!goal.done && next >= goal.target_value) toast(t("cycles.goalDone", { title: goal.title }), "achievement");
        },
        onError: (error) => toast(errorText(error), "error"),
      },
    );
  };

  return (
    <GoalRow goal={goal} hint={linkHint(t, goal)}>
      {goal.metric === "manual" && (
        // Disabled while saving: two quick taps must not both send the same old value + 1.
        <button
          className="step-btn num"
          onClick={increment}
          disabled={update.isPending || goal.current_value >= MAX_GOAL_VALUE}
          aria-label={`+1 · ${goal.title}`}
        >
          +1
        </button>
      )}
      <button className="icon-btn" onClick={onEdit} aria-label={t("common.edit")} title={t("common.edit")}>
        <Icon name="edit" />
      </button>
    </GoalRow>
  );
}

function Goals({ cycle }: { cycle: Cycle }) {
  const { t } = useI18n();
  const [editing, setEditing] = useState<Goal | "new" | null>(null);
  const open = isOpen(cycle);
  // A completed cycle shows the goals as they were summed up.
  const snapshot = cycle.report?.goals;
  const count = snapshot ? snapshot.length : cycle.goals.length;

  return (
    <section className="card">
      <div className="spread" style={{ marginBottom: 4 }}>
        <h2>{t("cycles.goals")}</h2>
        {open && cycle.goals.length < MAX_GOALS && (
          <button className="btn btn-small" onClick={() => setEditing("new")}>
            <Icon name="plus" />
            {t("cycles.addGoal")}
          </button>
        )}
      </div>
      {count === 0 && (
        <div className="empty">
          <Icon name="flag" />
          <strong>{open ? t("cycles.noGoals") : t("cycles.noGoalsClosed")}</strong>
          {open && <p className="muted small">{t("cycles.noGoalsHint")}</p>}
        </div>
      )}
      <div className="goal-list">
        {snapshot
          ? snapshot.map((goal, index) => <GoalRow key={index} goal={goal} />)
          : cycle.goals.map((goal) =>
              open ? (
                <OpenGoalRow key={goal.id} cycleId={cycle.id} goal={goal} onEdit={() => setEditing(goal)} />
              ) : (
                <GoalRow key={goal.id} goal={goal} />
              ),
            )}
      </div>
      {editing && (
        <GoalForm
          cycleId={cycle.id}
          goal={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </section>
  );
}

function Report({ report }: { report: CycleReport }) {
  const { t, locale } = useI18n();
  const recommendations = report.recommendations
    .map((item) => recommendationText(t, item))
    .filter((text): text is string => text !== null);

  return (
    <>
      <section className="card stack">
        <h2>{t("report.title")}</h2>
        {report.finished_early && <div className="note">{t("report.earlyNote")}</div>}
        <div className="report-grid">
          <Stat label={t("report.goals")} value={`${report.goals_done}/${report.goals_total}`} />
          <Stat label={t("report.xpTotal")} value={`+${formatNumber(report.xp_total, locale)}`} />
          <Stat label={t("report.cycleXp")} value={`+${formatNumber(report.cycle_xp, locale)}`} gold />
          <Stat label={t("report.activeDays")} value={report.active_days} />
        </div>
      </section>

      <section className="card">
        <h2 style={{ marginBottom: 4 }}>{t("report.attributes")}</h2>
        {report.attributes.map((attribute) => (
          <div
            key={attribute.attribute_type}
            className="attr-change"
            style={{ "--attr-color": ATTRIBUTE_COLOR[attribute.attribute_type] } as CSSProperties}
          >
            <span className="attr-icon">
              <Icon name={attribute.attribute_type} />
            </span>
            <span className="attr-change-name">{t(`attribute.${attribute.attribute_type}`)}</span>
            {attribute.level_after > attribute.level_before && (
              <span className="chip chip-gold num">
                {t("report.levels", { from: attribute.level_before, to: attribute.level_after })}
              </span>
            )}
            <span className={`ledger-amount num ${attribute.xp_gained > 0 ? "plus" : "minus"}`}>
              +{formatNumber(attribute.xp_gained, locale)}
            </span>
          </div>
        ))}
      </section>

      <section className="card">
        <h2 style={{ marginBottom: 10 }}>{t("report.activity")}</h2>
        <dl className="kv">
          <dt>{t("report.learning")}</dt>
          <dd className="num">{minutesText(t, report.learning_minutes)}</dd>
          <dt>{t("report.workouts")}</dt>
          <dd className="num">{report.workouts}</dd>
          <dt>{t("report.quests")}</dt>
          <dd className="num">{report.quests_completed}</dd>
          <dt>{t("report.habits")}</dt>
          <dd className="num">{report.habit_checkins}</dd>
          {report.paused_days > 0 && (
            <>
              <dt>{t("report.paused")}</dt>
              <dd className="num">{t("cycles.days", { n: report.paused_days })}</dd>
            </>
          )}
        </dl>
      </section>

      {report.achievements.length > 0 && (
        <section className="card">
          <h2 style={{ marginBottom: 10 }}>{t("report.achievements")}</h2>
          <div className="report-ach">
            {report.achievements.map((achievement) => (
              <span
                key={achievement.code}
                className="chip"
                style={{ "--rarity-color": RARITY_COLOR[achievement.rarity] } as CSSProperties}
              >
                <Icon name="trophy" width={13} height={13} />
                {achievementText(t, { ...achievement, description: "" }).title}
              </span>
            ))}
          </div>
        </section>
      )}

      {recommendations.length > 0 && (
        <section className="card">
          <h2 style={{ marginBottom: 12 }}>{t("report.recommendations")}</h2>
          <ul className="rec-list">
            {recommendations.map((text) => (
              <li key={text}>
                <Icon name="bulb" />
                <span>{text}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

/** A whole cycle: progress and actions while open, the stored report once completed. */
export function CycleView({ cycle }: { cycle: Cycle }) {
  return (
    <>
      <CycleHero cycle={cycle} />
      <Goals cycle={cycle} />
      {cycle.report && <Report report={cycle.report} />}
    </>
  );
}
