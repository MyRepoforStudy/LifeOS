import { Link } from "react-router";

import { useCurrentCycle } from "../api/queries";
import { useI18n } from "../i18n";
import { goalValueText, statusChip } from "../lib/cycles";
import { CycleNote } from "./CycleView";
import { Icon } from "./Icon";
import { ProgressBar } from "./ProgressBar";

const SHOWN_GOALS = 3;

/** The current cycle at a glance on the dashboard. */
export function CycleCard() {
  const { t } = useI18n();
  const { data: cycle, isLoading } = useCurrentCycle();

  if (isLoading) return <div className="card skeleton" style={{ height: 112 }} />;
  if (!cycle) {
    return (
      <Link to="/cycles" className="card spread cycle-card">
        <span className="row" style={{ fontWeight: 600 }}>
          <Icon name="cycle" width={20} height={20} style={{ color: "var(--gold)", flex: "none" }} />
          {t("cycles.dashboardEmpty")}
        </span>
        <Icon name="next" width={18} height={18} style={{ flex: "none" }} />
      </Link>
    );
  }

  const goals = cycle.goals.slice(0, SHOWN_GOALS);
  return (
    <Link to="/cycles" className="card stack cycle-card" style={{ gap: 12 }}>
      <div className="spread">
        <span className="eyebrow">{t("cycles.currentTitle")}</span>
        <span className={statusChip(cycle.status)}>{t(`cycleStatus.${cycle.status}`)}</span>
      </div>
      <div className="cycle-card-title">{cycle.title}</div>
      {cycle.status !== "planned" && (
        <div className="stack" style={{ gap: 6 }}>
          <div className="spread small">
            <span className="num">{t("cycles.dayOf", { day: cycle.day_number, total: cycle.duration_days })}</span>
            <span className="muted num">
              {t("cycles.goalsProgress", { done: cycle.goals_done, total: cycle.goals_total })}
            </span>
          </div>
          <ProgressBar value={cycle.time_progress} thin label={cycle.title} />
        </div>
      )}
      {goals.length > 0 && (
        <div className="cycle-card-goals">
          {goals.map((goal) => (
            <div key={goal.id} className={goal.done ? "cycle-card-goal done" : "cycle-card-goal"}>
              <Icon name={goal.done ? "check" : "flag"} width={14} height={14} />
              <span className="quest-title">{goal.title}</span>
              <span className="num">{goalValueText(t, goal)}</span>
            </div>
          ))}
          {cycle.goals.length > SHOWN_GOALS && (
            <span className="faint small num">+{cycle.goals.length - SHOWN_GOALS}</span>
          )}
        </div>
      )}
      <CycleNote cycle={cycle} />
    </Link>
  );
}
