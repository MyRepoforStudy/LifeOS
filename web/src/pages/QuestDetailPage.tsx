import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { ApiError } from "../api/client";
import { useDeleteQuest, useQuest, useUpdateQuest } from "../api/queries";
import type { ChecklistItem, QuestDetail } from "../api/types";
import { useFeedback } from "../components/Feedback";
import { GoalLinkCard } from "../components/GoalSelect";
import { Icon } from "../components/Icon";
import { isActionable, useQuestActions } from "../components/QuestRow";
import { useI18n, type MessageKey } from "../i18n";
import { acceptedMetrics } from "../lib/cycles";
import { formatDateTime, formatDay } from "../lib/format";

function QuestGoal({ quest }: { quest: QuestDetail }) {
  const { t, errorText } = useI18n();
  const { toast } = useFeedback();
  const update = useUpdateQuest(quest.id);
  return (
    <GoalLinkCard
      accepts={acceptedMetrics("quest", quest.activity)}
      value={quest.goal_id}
      saving={update.isPending}
      onSave={(goalId) =>
        update.mutate(
          { goal_id: goalId },
          { onSuccess: () => toast(t("detail.saved")), onError: (e) => toast(errorText(e), "error") },
        )
      }
    />
  );
}

function statusChip(status: QuestDetail["status"]): string {
  if (status === "completed") return "chip chip-success";
  if (status === "expired" || status === "cancelled") return "chip chip-danger";
  if (status === "active") return "chip chip-gold";
  return "chip";
}

function Checklist({ quest }: { quest: QuestDetail }) {
  const { t, errorText } = useI18n();
  const { toast } = useFeedback();
  const update = useUpdateQuest(quest.id);
  const [draft, setDraft] = useState("");

  const save = (items: ChecklistItem[]) => update.mutate({ checklist: items }, { onError: (e) => toast(errorText(e), "error") });
  const add = (event: FormEvent) => {
    event.preventDefault();
    if (!draft.trim()) return;
    save([...quest.checklist, { title: draft.trim(), done: false }]);
    setDraft("");
  };

  return (
    <section className="card">
      <div className="spread" style={{ marginBottom: 6 }}>
        <h2>{t("detail.checklist")}</h2>
        <span className="faint small">{t("detail.checklistHint")}</span>
      </div>
      {quest.checklist.map((item, index) => (
        <label key={index} className={`checklist-item${item.done ? " done" : ""}`}>
          <input
            type="checkbox"
            checked={item.done}
            onChange={() =>
              save(quest.checklist.map((other, i) => (i === index ? { ...other, done: !other.done } : other)))
            }
          />
          <span style={{ flex: 1 }}>{item.title}</span>
          <button
            type="button"
            className="icon-btn"
            aria-label={t("common.delete")}
            onClick={() => save(quest.checklist.filter((_, i) => i !== index))}
          >
            <Icon name="close" />
          </button>
        </label>
      ))}
      <form className="row" onSubmit={add} style={{ marginTop: 8 }}>
        <input
          className="input"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={t("detail.addItem")}
          maxLength={200}
        />
        <button className="btn" type="submit" aria-label={t("detail.addItem")} disabled={!draft.trim()}>
          <Icon name="plus" />
        </button>
      </form>
    </section>
  );
}

function EditTitle({ quest }: { quest: QuestDetail }) {
  const { t, errorText } = useI18n();
  const { toast } = useFeedback();
  const update = useUpdateQuest(quest.id);
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(quest.title);
  const [description, setDescription] = useState(quest.description ?? "");

  if (!editing) {
    return (
      <div className="spread" style={{ alignItems: "flex-start" }}>
        <div className="stack" style={{ gap: 6 }}>
          <h1>{quest.title}</h1>
          {quest.description && <p className="muted">{quest.description}</p>}
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
      { title: title.trim(), description: description.trim() || null },
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
    <form className="stack" onSubmit={save}>
      <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} required />
      <textarea className="textarea" value={description} onChange={(e) => setDescription(e.target.value)} />
      <div className="row">
        <button className="btn btn-primary btn-small" type="submit" disabled={!title.trim() || update.isPending}>
          {t("common.save")}
        </button>
        <button className="btn btn-ghost btn-small" type="button" onClick={() => setEditing(false)}>
          {t("common.cancel")}
        </button>
      </div>
    </form>
  );
}

export function QuestDetailPage() {
  const { id = "" } = useParams();
  const { t, locale, errorText } = useI18n();
  const navigate = useNavigate();
  const { toast } = useFeedback();
  const { data: quest, error, isLoading } = useQuest(id);
  const actions = useQuestActions();
  const remove = useDeleteQuest();

  if (isLoading) {
    return (
      <main className="page center-screen">
        <div className="spinner" />
      </main>
    );
  }
  if (!quest) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <main className="page">
        <div className="empty card">
          <strong>{notFound ? t("detail.notFound") : errorText(error)}</strong>
          <Link className="link" to="/quests">
            {t("common.back")}
          </Link>
        </div>
      </main>
    );
  }

  const done = quest.status === "completed";
  const onDelete = () => {
    if (!window.confirm(t("detail.deleteConfirm"))) return;
    remove.mutate(quest.id, {
      onSuccess: () => {
        toast(t("detail.deleted"));
        navigate("/quests", { replace: true });
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
        <span className={statusChip(quest.status)}>{t(`status.${quest.status}`)}</span>
        <span className="chip">{t(`questType.${quest.quest_type}`)}</span>
        {quest.is_recurring && (
          <span className="chip">
            <Icon name="repeat" width={13} height={13} />
            {quest.weekdays
              ? quest.weekdays.map((day) => t(`weekday.${day}` as MessageKey)).join(" ")
              : t("quest.everyDay")}
          </span>
        )}
      </div>

      <section className="card stack">
        <EditTitle key={`${quest.title}|${quest.description ?? ""}`} quest={quest} />
        <dl className="kv">
          <dt>{t("detail.reward")}</dt>
          <dd className="num" style={{ color: "var(--gold)", fontWeight: 700 }}>
            +{quest.xp_reward} XP
          </dd>
          <dt>{t("form.category")}</dt>
          <dd>{t(`category.${quest.category}`)}</dd>
          <dt>{t("form.activity")}</dt>
          <dd>
            {t(`activity.${quest.activity}`)}
            {quest.target_minutes ? ` · ${quest.target_minutes} ${t("common.minutes")}` : ""}
          </dd>
          {quest.activity === "task" && quest.quest_type !== "weekly" && (
            <>
              <dt>{t("form.difficulty")}</dt>
              <dd>{t(`difficulty.${quest.difficulty}`)}</dd>
            </>
          )}
          {quest.due_at && (
            <>
              <dt>{t("form.due")}</dt>
              <dd>{formatDateTime(quest.due_at, locale)}</dd>
            </>
          )}
          {quest.current_occurrence_date && (
            <>
              <dt>{t("detail.current")}</dt>
              <dd>{formatDay(quest.current_occurrence_date, locale)}</dd>
            </>
          )}
        </dl>
        <div className="row" style={{ flexWrap: "wrap" }}>
          {isActionable(quest) && (
            <>
              <button className="btn btn-primary" onClick={() => actions.complete(quest.id)} disabled={actions.busy}>
                <Icon name="check" />
                {t("quest.complete")}
              </button>
              {quest.status !== "skipped" && (
                <button className="btn" onClick={() => actions.skip(quest.id)} disabled={actions.busy}>
                  <Icon name="skip" />
                  {t("quest.skip")}
                </button>
              )}
            </>
          )}
          {done && (
            <button className="btn" onClick={() => actions.undo(quest.id)} disabled={actions.busy}>
              <Icon name="undo" />
              {t("quest.undo")}
            </button>
          )}
          <button className="btn btn-danger" onClick={onDelete} disabled={remove.isPending} style={{ marginLeft: "auto" }}>
            <Icon name="trash" />
            {t("common.delete")}
          </button>
        </div>
      </section>

      <QuestGoal quest={quest} />
      <Checklist quest={quest} />

      <section className="card">
        <h2 style={{ marginBottom: 8 }}>{t("detail.history")}</h2>
        {quest.occurrences.filter((o) => o.status !== "pending").length === 0 && (
          <p className="muted small">{t("detail.historyEmpty")}</p>
        )}
        {quest.occurrences
          .filter((o) => o.status !== "pending")
          .map((occurrence) => (
            <div key={occurrence.occurrence_date} className="ledger-row" style={{ paddingInline: 0 }}>
              <div>
                <div>{formatDay(occurrence.occurrence_date, locale)}</div>
                <div className="faint small">{t(`status.${occurrence.status === "completed" ? "completed" : "skipped"}`)}</div>
              </div>
              <span className={`ledger-amount num ${occurrence.xp_awarded > 0 ? "plus" : "minus"}`}>
                {occurrence.status === "completed" ? `+${occurrence.xp_awarded}` : "0"}
              </span>
            </div>
          ))}
      </section>
    </main>
  );
}
