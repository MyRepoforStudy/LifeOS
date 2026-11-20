import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { ApiError } from "../api/client";
import { useArchiveHabit, useHabit, useUpdateHabit } from "../api/queries";
import type { HabitDay, HabitDetail } from "../api/types";
import { useFeedback } from "../components/Feedback";
import { canComplete, useHabitActions } from "../components/HabitRow";
import { Icon } from "../components/Icon";
import { useI18n, type MessageKey } from "../i18n";
import { formatDay, parseLocalDate } from "../lib/format";
import { frequencyText, streakText } from "../lib/habits";

function History({ habit }: { habit: HabitDetail }) {
  const { t, locale } = useI18n();
  const weekly = habit.streak.unit === "week";
  const label = (day: HabitDay) => `${formatDay(day.date, locale)}: ${day.status}`;
  // Day grid starts on Monday: pad with empty cells before the first day.
  const first = habit.history[0];
  const pad = !weekly && first ? (parseLocalDate(first.date).getDay() + 6) % 7 : 0;

  return (
    <section className="card">
      <div className="spread" style={{ marginBottom: 10 }}>
        <h2>{t("habits.history")}</h2>
        <span className="faint small">{weekly ? t("habits.historyWeeks") : t("habits.historyDays")}</span>
      </div>
      <div className={weekly ? "heatmap weeks" : "heatmap"}>
        {!weekly &&
          [1, 2, 3, 4, 5, 6, 7].map((day) => (
            <div key={`h${day}`} className="heatmap-head">
              {t(`weekday.${day}` as MessageKey)}
            </div>
          ))}
        {Array.from({ length: pad }, (_, i) => (
          <div key={`p${i}`} className="heat pad" />
        ))}
        {habit.history.map((day) => (
          <div key={day.date} className={`heat ${day.status}`} title={label(day)} />
        ))}
      </div>
      <div className="legend">
        <span>
          <i className="heat done" /> {t("habits.legendDone")}
        </span>
        <span>
          <i className="heat frozen" /> {t("habits.legendFrozen")}
        </span>
        <span>
          <i className="heat missed" /> {t("habits.legendMissed")}
        </span>
        {!weekly && (
          <span>
            <i className="heat rest" /> {t("habits.legendRest")}
          </span>
        )}
      </div>
    </section>
  );
}

function EditTitle({ habit }: { habit: HabitDetail }) {
  const { t, errorText } = useI18n();
  const { toast } = useFeedback();
  const update = useUpdateHabit(habit.id);
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(habit.title);

  if (!editing) {
    return (
      <div className="spread" style={{ alignItems: "flex-start" }}>
        <div className="stack" style={{ gap: 6 }}>
          <h1>{habit.title}</h1>
          {habit.description && <p className="muted">{habit.description}</p>}
        </div>
        <button className="icon-btn" aria-label={t("common.edit")} title={t("common.edit")} onClick={() => setEditing(true)}>
          <Icon name="edit" />
        </button>
      </div>
    );
  }

  const save = (event: FormEvent) => {
    event.preventDefault();
    update.mutate(
      { title: title.trim() },
      {
        onSuccess: () => {
          setEditing(false);
          toast(t("detail.saved"));
        },
        onError: (e) => toast(errorText(e), "error"),
      },
    );
  };

  return (
    <form className="row" onSubmit={save}>
      <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} required />
      <button className="btn btn-primary btn-small" type="submit" disabled={!title.trim() || update.isPending}>
        {t("common.save")}
      </button>
    </form>
  );
}

export function HabitDetailPage() {
  const { id = "" } = useParams();
  const { t, locale, errorText } = useI18n();
  const navigate = useNavigate();
  const { toast } = useFeedback();
  const { data: habit, error, isLoading } = useHabit(id);
  const actions = useHabitActions();
  const archive = useArchiveHabit();

  if (isLoading) {
    return (
      <main className="page center-screen">
        <div className="spinner" />
      </main>
    );
  }
  if (!habit) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <main className="page">
        <div className="empty card">
          <strong>{notFound ? t("errors.habit_not_found") : errorText(error)}</strong>
          <Link className="link" to="/habits">
            {t("common.back")}
          </Link>
        </div>
      </main>
    );
  }

  const onArchive = () => {
    if (!window.confirm(t("habits.archiveConfirm"))) return;
    archive.mutate(habit.id, {
      onSuccess: () => {
        toast(t("habits.archived"));
        navigate("/habits", { replace: true });
      },
      onError: (e) => toast(errorText(e), "error"),
    });
  };

  return (
    <main className="page stack">
      <div className="row">
        <button className="icon-btn" onClick={() => navigate(-1)} aria-label={t("common.back")}>
          <Icon name="back" />
        </button>
        <span className="chip">
          <Icon name="repeat" width={13} height={13} />
          {frequencyText(t, habit)}
        </span>
        <span className="chip">{t(`category.${habit.category}`)}</span>
        {!habit.is_active && <span className="chip chip-danger">{t("habits.archived")}</span>}
      </div>

      <section className="card stack">
        <EditTitle key={habit.title} habit={habit} />
        <div className="stat-trio">
          <div className="stat">
            <div className="faint small">{t("habits.streak")}</div>
            <div className="stat-value num" style={{ color: habit.streak.current > 0 ? "var(--gold)" : undefined }}>
              {streakText(t, habit.streak)}
            </div>
          </div>
          <div className="stat">
            <div className="faint small">{t("habits.best")}</div>
            <div className="stat-value num">{streakText(t, habit.streak, habit.streak.best)}</div>
          </div>
          <div className="stat">
            <div className="faint small">{t("detail.reward")}</div>
            <div className="stat-value num">+{habit.xp_reward}</div>
          </div>
        </div>
        {habit.week_done !== null && habit.times_per_week !== null && (
          <p className="muted small">
            {t("habits.weekProgress", { done: habit.week_done, target: habit.times_per_week })}
          </p>
        )}
        <div className="row" style={{ flexWrap: "wrap" }}>
          {habit.done_today ? (
            <button className="btn" onClick={() => actions.undo(habit.id)} disabled={actions.busy}>
              <Icon name="undo" />
              {t("quest.undo")}
            </button>
          ) : (
            <button
              className="btn btn-primary"
              onClick={() => actions.complete(habit.id)}
              disabled={actions.busy || !canComplete(habit)}
            >
              <Icon name="check" />
              {habit.required_today ? t("quest.complete") : t("habits.restDay")}
            </button>
          )}
          {habit.is_active && (
            <button className="btn btn-danger" onClick={onArchive} disabled={archive.isPending} style={{ marginLeft: "auto" }}>
              <Icon name="trash" />
              {t("habits.archive")}
            </button>
          )}
        </div>
      </section>

      {habit.is_active && habit.freezable.length > 0 && (
        <section className="card stack" style={{ gap: 10 }}>
          <div className="spread">
            <h2>{t("habits.freeze")}</h2>
            <span className="faint small">{t("habits.freezesLeft", { n: habit.freezes_left })}</span>
          </div>
          <p className="muted small">{t("habits.freezeHint")}</p>
          {habit.freezable.map((day) => (
            <div key={day} className="spread">
              <span>
                {habit.streak.unit === "week"
                  ? t("habits.missedWeek", { date: formatDay(day, locale) })
                  : t("habits.missed", { date: formatDay(day, locale) })}
              </span>
              <button
                className="btn btn-small btn-frozen"
                onClick={() => actions.freeze(habit.id, day)}
                disabled={actions.busy}
              >
                <Icon name="snowflake" />
                {t("habits.freeze")}
              </button>
            </div>
          ))}
        </section>
      )}

      <History habit={habit} />
    </main>
  );
}
