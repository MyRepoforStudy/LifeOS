import { useState } from "react";

import { useHabits } from "../api/queries";
import { HabitForm } from "../components/HabitForm";
import { HabitRow } from "../components/HabitRow";
import { Icon } from "../components/Icon";
import { useI18n } from "../i18n";

export function HabitsPage() {
  const { t } = useI18n();
  const { data, isLoading } = useHabits();
  const [creating, setCreating] = useState(false);

  return (
    <main className="page">
      <div className="page-header">
        <h1>{t("nav.habits")}</h1>
        <button className="btn btn-primary btn-small" onClick={() => setCreating(true)}>
          <Icon name="plus" />
          {t("habits.newHabit")}
        </button>
      </div>

      <div className="card flush">
        {isLoading && <div className="skeleton" style={{ height: 200, margin: 6 }} />}
        {data && data.length === 0 && (
          <div className="empty">
            <Icon name="flame" />
            <strong>{t("habits.empty")}</strong>
            <p className="muted small">{t("habits.emptyHint")}</p>
            <button className="btn btn-small" style={{ marginTop: 6 }} onClick={() => setCreating(true)}>
              <Icon name="plus" />
              {t("habits.newHabit")}
            </button>
          </div>
        )}
        {data && data.length > 0 && (
          <div className="quest-list">
            {data.map((habit) => (
              <HabitRow key={habit.id} habit={habit} />
            ))}
          </div>
        )}
      </div>
      <p className="faint small" style={{ marginTop: 12, textAlign: "center" }}>
        {t("habits.freezeHint")}
      </p>

      {creating && <HabitForm onClose={() => setCreating(false)} />}
    </main>
  );
}
