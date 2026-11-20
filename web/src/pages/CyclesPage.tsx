import { useState } from "react";
import { Link } from "react-router";

import { useCurrentCycle, useCycles } from "../api/queries";
import type { CycleSummary } from "../api/types";
import { CycleForm } from "../components/CycleForm";
import { CycleView } from "../components/CycleView";
import { Icon } from "../components/Icon";
import { useI18n } from "../i18n";
import { statusChip } from "../lib/cycles";
import { formatDay } from "../lib/format";

function HistoryRow({ cycle }: { cycle: CycleSummary }) {
  const { t, locale } = useI18n();
  return (
    <Link to={`/cycles/${cycle.id}`} className="quest-row">
      <span className={cycle.status === "completed" ? "goal-mark done" : "goal-mark"} aria-hidden="true">
        <Icon name={cycle.status === "completed" ? "check" : "close"} />
      </span>
      <div className="quest-main">
        <div className="quest-title">{cycle.title}</div>
        <div className="quest-meta">
          <span className="num">
            {t("cycles.period", { from: formatDay(cycle.starts_on, locale), to: formatDay(cycle.ends_on, locale) })}
          </span>
          <span className="num">{t("cycles.goalsProgress", { done: cycle.goals_done, total: cycle.goals_total })}</span>
          <span className={statusChip(cycle.status)}>{t(`cycleStatus.${cycle.status}`)}</span>
        </div>
      </div>
      {cycle.xp_awarded > 0 && <span className="xp-tag num">+{cycle.xp_awarded}</span>}
      <Icon name="next" width={18} height={18} style={{ color: "var(--text-faint)", flex: "none" }} />
    </Link>
  );
}

function History({ currentId }: { currentId?: string }) {
  const { t } = useI18n();
  const { data } = useCycles();
  const past = (data ?? []).filter((cycle) => cycle.id !== currentId && !["planned", "active", "paused", "finished"].includes(cycle.status));
  if (past.length === 0) return null;
  return (
    <section>
      <div className="section-title">
        <h2>{t("cycles.history")}</h2>
      </div>
      <div className="card flush">
        <div className="quest-list">
          {past.map((cycle) => (
            <HistoryRow key={cycle.id} cycle={cycle} />
          ))}
        </div>
      </div>
    </section>
  );
}

export function CyclesPage() {
  const { t, errorText } = useI18n();
  const { data: current, error, isLoading, refetch } = useCurrentCycle();
  const [creating, setCreating] = useState(false);
  const none = !isLoading && !error && !current;

  return (
    <main className="page stack">
      <div className="page-header" style={{ marginBottom: 4 }}>
        <h1>{t("nav.cycles")}</h1>
        {none && (
          <button className="btn btn-primary btn-small" onClick={() => setCreating(true)}>
            <Icon name="plus" />
            {t("cycles.newCycle")}
          </button>
        )}
      </div>

      {isLoading && <div className="card skeleton" style={{ height: 280 }} />}
      {error && !current && (
        <div className="card empty">
          <strong>{errorText(error)}</strong>
          <button className="btn btn-small" onClick={() => void refetch()}>
            {t("common.retry")}
          </button>
        </div>
      )}
      {none && (
        <div className="card empty">
          <Icon name="cycle" />
          <strong>{t("cycles.empty")}</strong>
          <p className="muted small" style={{ maxWidth: 420 }}>
            {t("cycles.emptyHint")}
          </p>
          <button className="btn btn-primary btn-small" style={{ marginTop: 6 }} onClick={() => setCreating(true)}>
            <Icon name="plus" />
            {t("cycles.start")}
          </button>
        </div>
      )}
      {current && <CycleView cycle={current} />}

      <History currentId={current?.id} />

      {creating && <CycleForm onClose={() => setCreating(false)} />}
    </main>
  );
}
