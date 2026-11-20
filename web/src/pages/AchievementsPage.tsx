import type { CSSProperties } from "react";

import { useAchievements } from "../api/queries";
import type { Achievement } from "../api/types";
import { Icon } from "../components/Icon";
import { ProgressBar } from "../components/ProgressBar";
import { useI18n } from "../i18n";
import { ACHIEVEMENT_CATEGORIES, RARITY_COLOR, achievementIcon, achievementText } from "../lib/achievements";
import { formatDay } from "../lib/format";

export function AchievementCard({ achievement, compact }: { achievement: Achievement; compact?: boolean }) {
  const { t, locale } = useI18n();
  const { title, description } = achievementText(t, achievement);
  const style = { "--rarity-color": RARITY_COLOR[achievement.rarity] } as CSSProperties;
  const { current, target } = achievement.progress;
  return (
    <div className={achievement.unlocked ? "ach unlocked" : "ach"} style={style}>
      <div className="ach-icon">
        <Icon name={achievement.unlocked ? achievementIcon(achievement.icon) : "lock"} />
      </div>
      <div className="ach-body">
        <div className="spread" style={{ alignItems: "baseline" }}>
          <span className="ach-title">{title}</span>
          <span className="faint small num">+{achievement.xp_reward}</span>
        </div>
        {!compact && <span className="muted small">{description}</span>}
        <span className="ach-rarity">{t(`rarity.${achievement.rarity}`)}</span>
        {achievement.unlocked && achievement.unlocked_at ? (
          <span className="faint small">
            {t("achievements.unlockedOn", { date: formatDay(achievement.unlocked_at, locale) })}
          </span>
        ) : (
          !compact && (
            <div className="stack" style={{ gap: 4 }}>
              <ProgressBar value={current / Math.max(target, 1)} thin label={title} />
              <span className="faint small num">
                {current} / {target}
              </span>
            </div>
          )
        )}
      </div>
    </div>
  );
}

export function AchievementsPage() {
  const { t } = useI18n();
  const { data } = useAchievements();

  if (!data) {
    return (
      <main className="page center-screen">
        <div className="spinner" />
      </main>
    );
  }

  const unlocked = data.filter((a) => a.unlocked).length;
  return (
    <main className="page stack">
      <div className="page-header" style={{ marginBottom: 4 }}>
        <h1>{t("nav.achievements")}</h1>
        <span className="chip chip-gold num">
          <Icon name="trophy" width={14} height={14} />
          {t("achievements.summary", { unlocked, total: data.length })}
        </span>
      </div>
      <ProgressBar value={unlocked / Math.max(data.length, 1)} label={t("nav.achievements")} />
      {ACHIEVEMENT_CATEGORIES.map((category) => {
        const items = data.filter((a) => a.category === category);
        if (items.length === 0) return null;
        return (
          <section key={category}>
            <div className="section-title">
              <h2>{t(`achievementCategory.${category}`)}</h2>
            </div>
            <div className="ach-grid">
              {items.map((achievement) => (
                <AchievementCard key={achievement.code} achievement={achievement} />
              ))}
            </div>
          </section>
        );
      })}
    </main>
  );
}
