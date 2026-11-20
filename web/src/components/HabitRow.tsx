import type { CSSProperties } from "react";
import { Link } from "react-router";

import { useCompleteHabit, useFreezeHabit, useUndoHabit } from "../api/queries";
import type { Habit } from "../api/types";
import { useI18n } from "../i18n";
import { formatDay } from "../lib/format";
import { frequencyText, streakText } from "../lib/habits";
import { useFeedback } from "./Feedback";
import { Icon } from "./Icon";
import { ATTRIBUTE_COLOR } from "./QuestRow";

export function useHabitActions() {
  const { t, errorText } = useI18n();
  const { toast, celebrate } = useFeedback();
  const onError = (error: unknown) => toast(errorText(error), "error");
  const complete = useCompleteHabit(celebrate);
  const undo = useUndoHabit((result) => toast(t("feedback.undone", { xp: result.xp_reverted })));
  const freeze = useFreezeHabit();
  return {
    complete: (id: string) => complete.mutate({ id }, { onError }),
    undo: (id: string) => undo.mutate({ id }, { onError }),
    freeze: (id: string, day: string) =>
      freeze.mutate({ id, day }, { onSuccess: () => toast(t("feedback.frozen")), onError }),
    busy: complete.isPending || undo.isPending || freeze.isPending,
  };
}

/** Can the habit be marked for today? Weekly habits: any day. */
export function canComplete(habit: Habit): boolean {
  return habit.is_active && habit.required_today && !habit.done_today;
}

export function HabitRow({ habit }: { habit: Habit }) {
  const { t, locale } = useI18n();
  const actions = useHabitActions();
  const done = habit.done_today;
  const attribute = habit.attribute_types[0];
  const missed = habit.freezable[habit.freezable.length - 1];

  const onCheck = () => {
    if (done) actions.undo(habit.id);
    else if (canComplete(habit)) actions.complete(habit.id);
  };

  return (
    <>
      <div className={`quest-row${done ? " is-done" : ""}`}>
        <button
          className={`check${done ? " is-done" : ""}`}
          onClick={onCheck}
          disabled={actions.busy || (!done && !canComplete(habit))}
          aria-label={done ? t("quest.undo") : t("quest.complete")}
          aria-pressed={done}
        >
          <Icon name="check" />
        </button>
        <Link to={`/habits/${habit.id}`} className="quest-main">
          <div className="quest-title">{habit.title}</div>
          <div className="quest-meta">
            <span
              className="row"
              style={attribute ? ({ "--attr-color": ATTRIBUTE_COLOR[attribute] } as CSSProperties) : undefined}
            >
              <span className="dot" />
              {frequencyText(t, habit)}
            </span>
            {habit.week_done !== null && habit.times_per_week !== null && (
              <span>{t("habits.weekProgress", { done: habit.week_done, target: habit.times_per_week })}</span>
            )}
            {!habit.required_today && <span className="chip">{t("habits.restDay")}</span>}
          </div>
        </Link>
        <span className={habit.streak.current > 0 ? "streak-chip hot num" : "streak-chip num"} title={t("habits.streak")}>
          <Icon name="flame" />
          {streakText(t, habit.streak)}
        </span>
        <span className="xp-tag num">+{habit.xp_reward}</span>
      </div>
      {missed && (
        <div className="freeze-note">
          <span>
            {habit.streak.unit === "week"
              ? t("habits.missedWeek", { date: formatDay(missed, locale) })
              : t("habits.missed", { date: formatDay(missed, locale) })}
          </span>
          <button
            className="btn btn-small btn-frozen"
            onClick={() => actions.freeze(habit.id, missed)}
            disabled={actions.busy}
            title={t("habits.freezeHint")}
          >
            <Icon name="snowflake" />
            {t("habits.freeze")}
          </button>
        </div>
      )}
    </>
  );
}
