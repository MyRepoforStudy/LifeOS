import { useState, type CSSProperties } from "react";
import { Link } from "react-router";

import { useAchievements, useAttributes, useHabits, useProfile, useQuests, useXpHistory } from "../api/queries";
import type { Attribute, LedgerEntry } from "../api/types";
import { Avatar } from "../components/Avatar";
import { CycleCard } from "../components/CycleCard";
import { HabitForm } from "../components/HabitForm";
import { HabitRow } from "../components/HabitRow";
import { Icon } from "../components/Icon";
import { InsightsCard } from "../components/InsightsCard";
import { ProgressBar } from "../components/ProgressBar";
import { QuestForm } from "../components/QuestForm";
import { ATTRIBUTE_COLOR, QuestRow } from "../components/QuestRow";
import { useI18n } from "../i18n";
import { achievementText } from "../lib/achievements";
import { formatDateTime, formatNumber } from "../lib/format";
import { AchievementCard } from "./AchievementsPage";

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

const LEDGER_REASONS = [
  "quest_completed",
  "quest_completion_undone",
  "habit_completed",
  "habit_completion_undone",
  "achievement_unlocked",
  "cycle_completed",
  "manual_adjustment",
] as const;

function TodayHabits() {
  const { t } = useI18n();
  const { data } = useHabits();
  const [creating, setCreating] = useState(false);
  // Weekly habits count for every day of the week until the weekly goal is met.
  const today = data?.filter(
    (habit) =>
      habit.required_today &&
      (habit.done_today || habit.week_done === null || habit.week_done < (habit.times_per_week ?? 1)),
  );
  return (
    <section>
      <div className="section-title">
        <h2>{t("habits.today")}</h2>
        <Link className="link" to="/habits">
          {t("nav.habits")}
        </Link>
      </div>
      <div className="card flush">
        {!data && <div className="skeleton" style={{ height: 120, margin: 6 }} />}
        {today && today.length === 0 && (
          <div className="empty">
            <Icon name="flame" />
            <strong>{data && data.length > 0 ? t("habits.todayEmpty") : t("habits.empty")}</strong>
            {data && data.length === 0 && <p className="muted small">{t("habits.emptyHint")}</p>}
          </div>
        )}
        {today && today.length > 0 && (
          <div className="quest-list">
            {today.map((habit) => (
              <HabitRow key={habit.id} habit={habit} />
            ))}
          </div>
        )}
        {data && data.length === 0 && (
          <div style={{ padding: 8 }}>
            <button className="btn btn-block" onClick={() => setCreating(true)}>
              <Icon name="plus" />
              {t("habits.newHabit")}
            </button>
          </div>
        )}
      </div>
      {creating && <HabitForm onClose={() => setCreating(false)} />}
    </section>
  );
}

function RecentAchievements() {
  const { t } = useI18n();
  const { data } = useAchievements();
  const recent = (data ?? [])
    .filter((a) => a.unlocked_at)
    .sort((a, b) => (b.unlocked_at ?? "").localeCompare(a.unlocked_at ?? ""))
    .slice(0, 3);
  return (
    <section>
      <div className="section-title">
        <h2>{t("achievements.recent")}</h2>
        <Link className="link" to="/achievements">
          {t("achievements.all")}
        </Link>
      </div>
      {!data && <div className="skeleton" style={{ height: 90 }} />}
      {data && recent.length === 0 && (
        <div className="card">
          <p className="muted small">{t("achievements.recentEmpty")}</p>
        </div>
      )}
      <div className="stack" style={{ gap: 8 }}>
        {recent.map((achievement) => (
          <AchievementCard key={achievement.code} achievement={achievement} compact />
        ))}
      </div>
    </section>
  );
}

function LedgerRow({ entry }: { entry: LedgerEntry }) {
  const { t, locale } = useI18n();
  const { data: achievements } = useAchievements();
  const reason = LEDGER_REASONS.find((code) => code === entry.reason);
  // Achievement entries store the English title; show the localized one when known.
  const achievement =
    entry.reason === "achievement_unlocked" ? achievements?.find((a) => a.title === entry.description) : undefined;
  const title = achievement
    ? achievementText(t, achievement).title
    : (entry.description ?? (reason ? t(`ledger.${reason}`) : entry.reason));
  return (
    <div className="ledger-row">
      <div style={{ minWidth: 0 }}>
        <div className="quest-title">{title}</div>
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
          <CycleCard />
          <InsightsCard />
          <Attributes />
          <RecentAchievements />
        </div>
        <div className="stack">
          <TodayQuests />
          <TodayHabits />
          <RecentXp />
        </div>
      </div>
    </main>
  );
}
