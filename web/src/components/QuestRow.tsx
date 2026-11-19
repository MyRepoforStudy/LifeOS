import type { CSSProperties } from "react";
import { Link } from "react-router";

import { useCompleteQuest, useSkipQuest, useUndoQuest } from "../api/queries";
import type { Quest } from "../api/types";
import { useI18n } from "../i18n";
import { formatDay } from "../lib/format";
import { useFeedback } from "./Feedback";
import { Icon } from "./Icon";

export const ATTRIBUTE_COLOR: Record<string, string> = {
  health: "var(--attr-health)",
  intelligence: "var(--attr-intelligence)",
  career: "var(--attr-career)",
  finance: "var(--attr-finance)",
};

/** Can the quest be completed or skipped right now? */
export function isActionable(quest: Quest): boolean {
  return quest.current_occurrence_date !== null && (quest.status === "active" || quest.status === "skipped");
}

export function useQuestActions() {
  const { t, errorText } = useI18n();
  const { toast, celebrate } = useFeedback();
  const onError = (error: unknown) => toast(errorText(error), "error");
  const complete = useCompleteQuest(celebrate);
  const skip = useSkipQuest();
  const undo = useUndoQuest((result) => toast(t("feedback.undone", { xp: result.xp_reverted })));
  return {
    complete: (id: string) => complete.mutate({ id }, { onError }),
    skip: (id: string) => skip.mutate({ id }, { onSuccess: () => toast(t("feedback.skipped")), onError }),
    undo: (id: string) => undo.mutate({ id }, { onError }),
    busy: complete.isPending || skip.isPending || undo.isPending,
  };
}

export function QuestRow({ quest }: { quest: Quest }) {
  const { t, locale } = useI18n();
  const actions = useQuestActions();
  const done = quest.status === "completed";
  const skipped = quest.status === "skipped";
  const actionable = isActionable(quest);
  const attribute = quest.attribute_types[0];

  const onCheck = () => {
    if (done) actions.undo(quest.id);
    else if (actionable) actions.complete(quest.id);
  };

  let note: string | null = null;
  if (quest.status === "pending") note = t("status.pending");
  else if (quest.status === "expired") note = t("status.expired");
  else if (!done && quest.current_occurrence_date === null) note = t("quest.notToday");

  return (
    <div className={`quest-row${done ? " is-done" : ""}`}>
      <button
        className={`check${done ? " is-done" : ""}${skipped ? " is-skipped" : ""}`}
        onClick={onCheck}
        disabled={actions.busy || (!done && !actionable)}
        aria-label={done ? t("quest.undo") : t("quest.complete")}
        aria-pressed={done}
      >
        <Icon name={done ? "check" : skipped ? "skip" : "check"} />
      </button>
      <Link to={`/quests/${quest.id}`} className="quest-main">
        <div className="quest-title">{quest.title}</div>
        <div className="quest-meta">
          <span className="row" style={attribute ? ({ "--attr-color": ATTRIBUTE_COLOR[attribute] } as CSSProperties) : undefined}>
            <span className="dot" />
            {t(`category.${quest.category}`)}
          </span>
          <span>{t(`questType.${quest.quest_type}`)}</span>
          {quest.target_minutes ? (
            <span className="row">
              <Icon name="clock" width={13} height={13} />
              {quest.target_minutes} {t("common.minutes")}
            </span>
          ) : null}
          {quest.due_at ? <span>{t("quest.due", { date: formatDay(quest.due_at, locale) })}</span> : null}
          {note ? <span className="chip">{note}</span> : null}
          {skipped ? <span className="chip">{t("status.skipped")}</span> : null}
        </div>
      </Link>
      {actionable && !skipped ? (
        <button
          className="icon-btn"
          onClick={() => actions.skip(quest.id)}
          disabled={actions.busy}
          aria-label={t("quest.skip")}
          title={t("quest.skip")}
        >
          <Icon name="skip" />
        </button>
      ) : null}
      <span className="xp-tag num">+{quest.xp_reward}</span>
    </div>
  );
}
