import { useState, type CSSProperties } from "react";
import { Link } from "react-router";

import { useAttributes, useProfile, useQuests, useXpHistory } from "../api/queries";
import type { Attribute, LedgerEntry } from "../api/types";
import { Avatar } from "../components/Avatar";
import { Icon } from "../components/Icon";
import { ProgressBar } from "../components/ProgressBar";
import { QuestForm } from "../components/QuestForm";
import { ATTRIBUTE_COLOR, QuestRow } from "../components/QuestRow";
import { useI18n } from "../i18n";
import { formatDateTime, formatNumber } from "../lib/format";

function Hero() {
  const { t, locale } = useI18n();
  const { data: profile } = useProfile();
  if (!profile) return <div className="card skeleton" style={{ height: 220 }} />;
  const nextLevel = profile.level + 1;
  return (
    <section className="card hero" aria-label={t("common.level")}>
      <div className="hero-top">
        <Avatar
          name={profile.display_name}
          imageUrl={profile.avatar_url}
          level={profile.level}
          progress={profile.level_progress}
        />
        <div>
          <div className="hero-name">{t("dashboard.greeting", { name: profile.display_name })}</div>
          <div className="muted small num">
            {t("common.level")} {profile.level} · {formatNumber(profile.total_xp, locale)} XP
          </div>
        </div>
      </div>
      <div className="hero-meta">
        <div className="spread small">
          <span className="num">
            <strong>{formatNumber(profile.xp_in_level, locale)}</strong>
            <span className="faint"> / {formatNumber(profile.xp_for_level ?? 0, locale)} XP</span>
          </span>
          {profile.xp_to_next_level !== null && (
            <span className="muted num">
              {t("dashboard.toNext", { xp: formatNumber(profile.xp_to_next_level, locale), level: nextLevel })}
            </span>
          )}
        </div>
        <ProgressBar value={profile.level_progress} label={t("common.level")} pulseOn={profile.total_xp} />
      </div>
      <div className="stat-pair">
        <div className="stat">
          <div className="faint small">{t("dashboard.totalXp")}</div>
          <div className="stat-value num">{formatNumber(profile.total_xp, locale)}</div>
        </div>
        <div className="stat">
          <div className="faint small">{t("profile.completed")}</div>
          <div className="stat-value num">{formatNumber(profile.completed_quests, locale)}</div>
        </div>
      </div>
    </section>
  );
}

function AttributeCard({ attribute }: { attribute: Attribute }) {
  const { t } = useI18n();
  const style = { "--attr-color": ATTRIBUTE_COLOR[attribute.attribute_type] } as CSSProperties;
  return (
    <div className="attr" style={style}>
      <div className="attr-head">
        <span className="attr-icon">
          <Icon name={attribute.attribute_type} />
        </span>
        <span className="attr-name">{t(`attribute.${attribute.attribute_type}`)}</span>
        <span className="attr-level num">
          {t("common.levelShort")} {attribute.level}
        </span>
      </div>
      <ProgressBar value={attribute.level_progress} thin label={t(`attribute.${attribute.attribute_type}`)} />
      <div className="faint small num">
        {attribute.total_xp} XP
        {attribute.xp_last_7_days > 0 && ` · ${t("dashboard.weekGain", { xp: attribute.xp_last_7_days })}`}
      </div>
    </div>
  );
}

function Attributes() {
  const { t } = useI18n();
  const { data } = useAttributes();
  return (
    <section>
      <div className="section-title">
        <h2>{t("dashboard.attributes")}</h2>
      </div>
      <div className="attr-grid">
        {data
          ? data.map((attribute) => <AttributeCard key={attribute.attribute_type} attribute={attribute} />)
          : [0, 1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 96 }} />)}
      </div>
    </section>
  );
}

function TodayQuests() {
  const { t } = useI18n();
  const { data, isLoading } = useQuests({ scope: "today" });
  const [creating, setCreating] = useState(false);
  return (
    <section>
      <div className="section-title">
        <h2>{t("dashboard.today")}</h2>
        <Link className="link" to="/quests">
          {t("dashboard.allQuests")}
        </Link>
      </div>
      <div className="card flush">
        {isLoading && <div className="skeleton" style={{ height: 180, margin: 6 }} />}
        {data && data.items.length === 0 && (
          <div className="empty">
            <Icon name="target" />
            <strong>{t("dashboard.todayEmpty")}</strong>
            <p className="muted small">{t("dashboard.todayEmptyHint")}</p>
          </div>
        )}
        {data && data.items.length > 0 && (
          <div className="quest-list">
            {data.items.map((quest) => (
              <QuestRow key={quest.id} quest={quest} />
            ))}
          </div>
        )}
        <div style={{ padding: 8 }}>
          <button className="btn btn-block" onClick={() => setCreating(true)}>
            <Icon name="plus" />
            {t("quest.newQuest")}
          </button>
        </div>
      </div>
      {creating && <QuestForm onClose={() => setCreating(false)} />}
    </section>
  );
}

function LedgerRow({ entry }: { entry: LedgerEntry }) {
  const { t, locale } = useI18n();
  const reason = (["quest_completed", "quest_completion_undone", "manual_adjustment"] as const).find(
    (code) => code === entry.reason,
  );
  return (
    <div className="ledger-row">
      <div style={{ minWidth: 0 }}>
        <div className="quest-title">{entry.description ?? (reason ? t(`ledger.${reason}`) : entry.reason)}</div>
        <div className="faint small">
          {reason ? t(`ledger.${reason}`) : entry.reason} · {formatDateTime(entry.created_at, locale)}
        </div>
      </div>
      <span className={`ledger-amount num ${entry.xp_amount > 0 ? "plus" : "minus"}`}>
        {entry.xp_amount > 0 ? "+" : "−"}
        {Math.abs(entry.xp_amount)}
      </span>
    </div>
  );
}

function RecentXp() {
  const { t } = useI18n();
  const { data } = useXpHistory(6);
  return (
    <section>
      <div className="section-title">
        <h2>{t("dashboard.recent")}</h2>
      </div>
      <div className="card flush">
        {data && data.items.length === 0 && <p className="empty muted small">{t("dashboard.recentEmpty")}</p>}
        {data?.items.map((entry) => (
          <LedgerRow key={entry.id} entry={entry} />
        ))}
        {!data && <div className="skeleton" style={{ height: 120, margin: 6 }} />}
      </div>
    </section>
  );
}

export function DashboardPage() {
  return (
    <main className="page">
      <div className="dashboard-grid">
        <div className="stack">
          <Hero />
          <Attributes />
        </div>
        <div className="stack">
          <TodayQuests />
          <RecentXp />
        </div>
      </div>
    </main>
  );
}
