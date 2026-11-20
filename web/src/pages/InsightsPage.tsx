import { useState, type CSSProperties } from "react";
import { Link, useNavigate } from "react-router";

import { useAnalysis, useRecommendations } from "../api/queries";
import type { AdaptiveRecommendation, Analysis, AnalysisWindow, ItemStat } from "../api/types";
import { AdviceCard } from "../components/AdviceCard";
import { Icon } from "../components/Icon";
import { ProgressBar } from "../components/ProgressBar";
import { Stat } from "../components/Stat";
import { useI18n } from "../i18n";
import { CATEGORY_COLOR, adviceTitle, percent } from "../lib/adaptive";
import { minutesText } from "../lib/cycles";
import { formatDay, formatNumber } from "../lib/format";

type Span = "week" | "month";

function Trend({ analysis }: { analysis: Analysis }) {
  const { t } = useI18n();
  const { rate } = analysis.week;
  if (rate === null || analysis.previous_week_rate === null) return null;
  const change = Math.round((rate - analysis.previous_week_rate) * 100);
  if (change > 0) return <span className="small trend-up num">{t("insights.trendUp", { n: change })}</span>;
  if (change < 0) return <span className="small faint num">{t("insights.trendDown", { n: -change })}</span>;
  return <span className="small faint">{t("insights.trendSame")}</span>;
}

function PlanCard({ analysis }: { analysis: Analysis }) {
  const { t, locale } = useI18n();
  const [span, setSpan] = useState<Span>("week");
  const stats: AnalysisWindow = span === "week" ? analysis.week : analysis.month;

  return (
    <section className="card stack">
      <div className="spread" style={{ flexWrap: "wrap" }}>
        <h2>{t("insights.plan")}</h2>
        <div className="segmented compact" role="group" aria-label={t("insights.plan")}>
          {(["week", "month"] as const).map((option) => (
            <button key={option} type="button" aria-pressed={span === option} onClick={() => setSpan(option)}>
              {t(`insights.${option}`)}
            </button>
          ))}
        </div>
      </div>
      <span className="faint small num">
        {formatDay(stats.first_day, locale)} — {formatDay(stats.last_day, locale)}
      </span>

      {stats.planned === 0 ? (
        <p className="muted">{t("insights.noPlan")}</p>
      ) : (
        <>
          <div className="rate-line">
            <span className="rate-value num">{percent(stats.rate)}%</span>
            <div className="stack" style={{ gap: 2 }}>
              <span>{t("insights.done", { done: stats.done, planned: stats.planned })}</span>
              {stats.skipped > 0 && <span className="faint small">{t("insights.skipped", { n: stats.skipped })}</span>}
              {span === "week" && <Trend analysis={analysis} />}
            </div>
          </div>
          <ProgressBar value={stats.rate ?? 0} label={t("insights.plan")} />
        </>
      )}

      <div className="insight-grid">
        <Stat label={t("insights.quests")} value={`${stats.quests_done}/${stats.quests_planned}`} />
        <Stat label={t("insights.habits")} value={`${stats.habits_done}/${stats.habits_planned}`} />
        <Stat label={t("insights.learning")} value={minutesText(t, stats.learning_minutes_done)} />
        <Stat label={t("insights.activeDays")} value={`${stats.active_days}/${stats.days}`} />
        <Stat label={t("insights.xp")} value={`+${formatNumber(stats.xp, locale)}`} gold />
      </div>

      {stats.categories.length > 0 && (
        <div>
          <h3 className="eyebrow" style={{ margin: "6px 0 4px" }}>
            {t("insights.categories")}
          </h3>
          {stats.categories.map((category) => (
            <div
              key={category.category}
              className="cat-row"
              style={{ "--cat-color": CATEGORY_COLOR[category.category] } as CSSProperties}
            >
              <span className="cat-name">{t(`category.${category.category}`)}</span>
              <ProgressBar value={category.rate ?? 0} thin label={t(`category.${category.category}`)} />
              <span className="small muted num">{t("insights.outOf", { done: category.done, planned: category.planned })}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function Struggling({ items }: { items: ItemStat[] }) {
  const { t } = useI18n();
  if (items.length === 0) return null;
  return (
    <section>
      <div className="section-title">
        <h2>{t("insights.struggling")}</h2>
        <span className="faint small">{t("insights.strugglingHint")}</span>
      </div>
      <div className="card flush">
        <div className="quest-list">
          {items.map((item) => (
            <Link key={item.id} to={`/${item.kind === "quest" ? "quests" : "habits"}/${item.id}`} className="quest-row">
              <div className="quest-main">
                <div className="quest-title">{item.title}</div>
                <div className="quest-meta">
                  <span>{item.kind === "quest" ? t("nav.quests") : t("nav.habits")}</span>
                  <span>{t(`category.${item.category}`)}</span>
                </div>
              </div>
              <span className="small muted num">{t("insights.outOf", { done: item.done, planned: item.planned })}</span>
              <Icon name="next" width={18} height={18} style={{ color: "var(--text-faint)", flex: "none" }} />
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}

function History({ items }: { items: AdaptiveRecommendation[] }) {
  const { t, locale } = useI18n();
  if (items.length === 0) return null;
  const chip = (status: AdaptiveRecommendation["status"]) => (status === "applied" ? "chip chip-success" : "chip");
  return (
    <section>
      <div className="section-title">
        <h2>{t("insights.history")}</h2>
      </div>
      <div className="card flush">
        {items.map((advice) => (
          <div key={advice.id} className="ledger-row">
            <div style={{ minWidth: 0 }}>
              <div className="quest-title">{adviceTitle(t, advice)}</div>
              <div className="faint small">{formatDay(advice.updated_at, locale)}</div>
            </div>
            <span className={chip(advice.status)} style={{ marginLeft: "auto" }}>
              {t(`adviceStatus.${advice.status}`)}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

export function InsightsPage() {
  const { t, errorText } = useI18n();
  const navigate = useNavigate();
  const analysis = useAnalysis();
  const advice = useRecommendations();
  const pending = advice.data?.filter((item) => item.status === "pending") ?? [];
  const history = advice.data?.filter((item) => item.status !== "pending") ?? [];
  // Opened from a link of its own (or the home screen), there is no page to go back to.
  const back = () => (window.history.length > 1 ? navigate(-1) : navigate("/"));

  return (
    <main className="page stack">
      <div className="row">
        <button className="icon-btn" onClick={back} aria-label={t("common.back")}>
          <Icon name="back" />
        </button>
        <h1>{t("insights.title")}</h1>
      </div>
      <p className="muted small">{t("insights.subtitle")}</p>

      <section>
        <div className="section-title">
          <h2>{t("insights.recommendations")}</h2>
        </div>
        {advice.isLoading && <div className="card skeleton" style={{ height: 150 }} />}
        {advice.error && <div className="card muted small">{errorText(advice.error)}</div>}
        {advice.data && pending.length === 0 && (
          <div className="card">
            <p className="muted small">{t("insights.noAdvice")}</p>
          </div>
        )}
        <div className="stack">
          {pending.map((item) => (
            <AdviceCard key={item.id} advice={item} />
          ))}
        </div>
        <p className="faint small" style={{ marginTop: 10 }}>
          {t("insights.consentNote")}
        </p>
      </section>

      {analysis.isLoading && <div className="card skeleton" style={{ height: 260 }} />}
      {analysis.data && <PlanCard analysis={analysis.data} />}
      {analysis.data && <Struggling items={analysis.data.struggling} />}
      <History items={history} />

      <p className="faint small" style={{ textAlign: "center" }}>
        {t("insights.calmNote")}
      </p>
    </main>
  );
}
