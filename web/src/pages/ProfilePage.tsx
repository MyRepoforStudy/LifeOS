import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router";

import { useAchievements, useProfile, useStatistics, useUpdateProfile } from "../api/queries";
import { useAuth } from "../auth/AuthProvider";
import { Avatar } from "../components/Avatar";
import { useFeedback } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { LanguageSwitch } from "../components/LanguageSwitch";
import { useI18n } from "../i18n";
import { formatDateTime, formatDay, formatNumber } from "../lib/format";

function timeZones(current: string): string[] {
  let zones: string[] = [];
  try {
    zones = Intl.supportedValuesOf("timeZone");
  } catch {
    zones = [];
  }
  return zones.includes(current) ? zones : [current, ...zones];
}

function XpChart() {
  const { t, locale } = useI18n();
  const { data } = useStatistics();
  if (!data) return <div className="skeleton" style={{ height: 110 }} />;
  const max = Math.max(1, ...data.xp_by_day.map((day) => day.xp));
  const first = data.xp_by_day[0];
  const last = data.xp_by_day[data.xp_by_day.length - 1];
  return (
    <div>
      <div className="spread small" style={{ marginBottom: 4 }}>
        <span className="muted">{t("profile.chart")}</span>
        <strong className="num" style={{ color: "var(--gold)" }}>
          +{formatNumber(data.total_xp, locale)} XP
        </strong>
      </div>
      {data.total_xp === 0 ? (
        <p className="faint small" style={{ padding: "26px 0" }}>
          {t("profile.chartEmpty")}
        </p>
      ) : (
        <div className="chart" role="img" aria-label={t("profile.chart")}>
          {data.xp_by_day.map((day) => (
            <div
              key={day.date}
              className={day.xp > 0 ? "chart-bar has-xp" : "chart-bar"}
              style={{ height: `${Math.max(4, (day.xp / max) * 100)}%` }}
              title={`${formatDay(day.date, locale)}: ${day.xp} XP`}
            />
          ))}
        </div>
      )}
      {first && last && (
        <div className="spread faint small" style={{ marginTop: 6 }}>
          <span>{formatDay(first.date, locale)}</span>
          <span>{formatDay(last.date, locale)}</span>
        </div>
      )}
    </div>
  );
}

export function ProfilePage() {
  const { t, locale, errorText } = useI18n();
  const { toast } = useFeedback();
  const auth = useAuth();
  const { data: profile } = useProfile();
  const { data: achievements } = useAchievements();
  const update = useUpdateProfile();
  const [name, setName] = useState<string | null>(null);
  const zones = useMemo(() => timeZones(profile?.pending_timezone ?? profile?.timezone ?? "UTC"), [profile]);

  if (!profile) {
    return (
      <main className="page center-screen">
        <div className="spinner" />
      </main>
    );
  }

  const shownName = name ?? profile.display_name;
  const selectedZone = profile.pending_timezone ?? profile.timezone;
  const onError = (error: unknown) => toast(errorText(error), "error");

  const saveName = (event: FormEvent) => {
    event.preventDefault();
    update.mutate(
      { display_name: shownName.trim() },
      {
        onSuccess: () => {
          setName(null);
          toast(t("detail.saved"));
        },
        onError,
      },
    );
  };

  return (
    <main className="page stack">
      <div className="page-header">
        <h1>{t("profile.title")}</h1>
      </div>

      <section className="card hero">
        <div className="hero-top">
          <Avatar
            name={profile.display_name}
            imageUrl={profile.avatar_url}
            level={profile.level}
            progress={profile.level_progress}
          />
          <div className="stack" style={{ gap: 4 }}>
            <div className="hero-name">{profile.display_name}</div>
            <div className="muted small">{profile.email}</div>
            <div className="faint small">
              {t("profile.memberSince", { date: formatDay(profile.registered_at, locale) })}
            </div>
          </div>
        </div>
        <div className="stat-pair">
          <div className="stat">
            <div className="faint small">{t("profile.completed")}</div>
            <div className="stat-value num">{profile.completed_quests}</div>
          </div>
          <div className="stat">
            <div className="faint small">{t("profile.active")}</div>
            <div className="stat-value num">{profile.active_quests}</div>
          </div>
        </div>
      </section>

      <Link to="/achievements" className="card spread" style={{ padding: "14px 18px" }}>
        <span className="row" style={{ fontWeight: 600 }}>
          <Icon name="trophy" width={20} height={20} style={{ color: "var(--gold)" }} />
          {t("nav.achievements")}
        </span>
        <span className="row muted small num">
          {achievements && t("achievements.summary", { unlocked: achievements.filter((a) => a.unlocked).length, total: achievements.length })}
          <Icon name="next" width={18} height={18} />
        </span>
      </Link>

      <section className="card">
        <XpChart />
      </section>

      <section className="card stack">
        <form className="field" onSubmit={saveName}>
          <span>{t("profile.displayName")}</span>
          <div className="row">
            <input
              className="input"
              value={shownName}
              onChange={(event) => setName(event.target.value)}
              maxLength={100}
              required
            />
            <button className="btn" type="submit" disabled={update.isPending || shownName.trim() === profile.display_name}>
              {t("common.save")}
            </button>
          </div>
        </form>

        <label className="field">
          <span>{t("profile.timezone")}</span>
          <select
            className="select"
            value={selectedZone}
            onChange={(event) => update.mutate({ timezone: event.target.value }, { onError })}
          >
            {zones.map((zone) => (
              <option key={zone} value={zone}>
                {zone}
              </option>
            ))}
          </select>
          {profile.pending_timezone && profile.pending_timezone_from && (
            <small className="faint">
              {t("profile.timezonePending", {
                tz: profile.pending_timezone,
                date: formatDateTime(profile.pending_timezone_from, locale),
              })}
            </small>
          )}
        </label>

        <div className="spread">
          <span className="muted small" style={{ fontWeight: 600 }}>
            {t("profile.language")}
          </span>
          <LanguageSwitch />
        </div>
      </section>

      <button className="btn btn-ghost" onClick={() => void auth.logout()}>
        <Icon name="logout" />
        {t("profile.logout")}
      </button>
    </main>
  );
}
