import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { client } from "../api/endpoints";
import { useCreateQuest } from "../api/queries";
import {
  ACTIVITIES,
  CATEGORIES,
  DIFFICULTIES,
  QUEST_TYPES,
  type Activity,
  type Difficulty,
  type QuestCategory,
  type QuestDraft,
  type QuestType,
} from "../api/types";
import { useI18n } from "../i18n";
import { fromDateTimeInput } from "../lib/format";
import { newId } from "../lib/id";
import { previewReward, type RewardRules } from "../lib/rewards";
import { useFeedback } from "./Feedback";
import { Sheet } from "./Sheet";

const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7] as const;
const ONE_OFF: QuestType[] = ["personal", "challenge", "milestone"];

function useRewardRules() {
  return useQuery({
    queryKey: ["config", "rewards"],
    queryFn: () => client.request<RewardRules>("GET", "/config/rewards", { auth: false }),
    staleTime: Infinity,
  });
}

interface Choice<T extends string> {
  value: T;
  options: readonly T[];
  label: (option: T) => string;
  onChange: (option: T) => void;
}

function Choices<T extends string>({ value, options, label, onChange }: Choice<T>) {
  return (
    <div className="choice-grid">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          className="choice"
          aria-pressed={option === value}
          onClick={() => onChange(option)}
        >
          {label(option)}
        </button>
      ))}
    </div>
  );
}

export function QuestForm({ initialType = "daily", onClose }: { initialType?: QuestType; onClose: () => void }) {
  const { t, errorText } = useI18n();
  const { toast } = useFeedback();
  const rules = useRewardRules();
  const create = useCreateQuest();
  // One key per opened form: a double tap or a retry cannot create two quests.
  const [idempotencyKey] = useState(newId);

  const [title, setTitle] = useState("");
  const [questType, setQuestType] = useState<QuestType>(initialType);
  const [category, setCategory] = useState<QuestCategory>("learning");
  const [activity, setActivity] = useState<Activity>("task");
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [minutes, setMinutes] = useState(30);
  const [weekdays, setWeekdays] = useState<number[]>([...WEEKDAYS]);
  const [due, setDue] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState(2);
  const [error, setError] = useState<string | null>(null);

  const oneOff = ONE_OFF.includes(questType);
  const showDifficulty = activity === "task" && questType !== "weekly";
  const reward = rules.data
    ? previewReward(rules.data, questType, activity, difficulty, activity === "learning" ? minutes : null)
    : null;

  const toggleWeekday = (day: number) =>
    setWeekdays((current) =>
      current.includes(day) ? current.filter((d) => d !== day) : [...current, day].sort((a, b) => a - b),
    );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const draft: QuestDraft = {
      title: title.trim(),
      quest_type: questType,
      category,
      activity,
      difficulty,
      priority,
      description: description.trim() || null,
      target_minutes: activity === "learning" ? minutes : null,
      weekdays: questType === "daily" && weekdays.length > 0 && weekdays.length < 7 ? weekdays : null,
      due_at: oneOff ? fromDateTimeInput(due) : null,
    };
    create.mutate(
      { draft, key: idempotencyKey },
      {
        onSuccess: () => {
          toast(t("feedback.created"));
          onClose();
        },
        onError: (err) => setError(errorText(err)),
      },
    );
  };

  return (
    <Sheet title={t("quest.newQuest")} onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <label className="field">
          <span>{t("form.title")}</span>
          <input
            className="input"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder={t("form.titlePlaceholder")}
            maxLength={200}
            required
          />
        </label>

        <div className="field">
          <span>{t("form.type")}</span>
          <Choices value={questType} options={QUEST_TYPES} label={(o) => t(`questType.${o}`)} onChange={setQuestType} />
        </div>

        <div className="field">
          <span>{t("form.category")}</span>
          <Choices value={category} options={CATEGORIES} label={(o) => t(`category.${o}`)} onChange={setCategory} />
        </div>

        <div className="field">
          <span>{t("form.activity")}</span>
          <Choices value={activity} options={ACTIVITIES} label={(o) => t(`activity.${o}`)} onChange={setActivity} />
        </div>

        {showDifficulty && (
          <div className="field">
            <span>{t("form.difficulty")}</span>
            <Choices
              value={difficulty}
              options={DIFFICULTIES}
              label={(o) => t(`difficulty.${o}`)}
              onChange={setDifficulty}
            />
          </div>
        )}

        {activity === "learning" && (
          <label className="field">
            <span>{t("form.minutes")}</span>
            <input
              className="input num"
              type="number"
              min={30}
              max={240}
              step={30}
              value={minutes}
              onChange={(event) => setMinutes(Number(event.target.value))}
              required
            />
            <small className="faint">{t("form.minutesHint")}</small>
          </label>
        )}

        {questType === "daily" && (
          <div className="field">
            <span>{t("form.weekdays")}</span>
            <div className="choice-grid">
              {WEEKDAYS.map((day) => (
                <button
                  key={day}
                  type="button"
                  className="choice"
                  aria-pressed={weekdays.includes(day)}
                  onClick={() => toggleWeekday(day)}
                >
                  {t(`weekday.${day}`)}
                </button>
              ))}
            </div>
          </div>
        )}

        {oneOff && (
          <label className="field">
            <span>
              {t("form.due")} <span className="faint">({t("common.optional")})</span>
            </span>
            <input className="input" type="datetime-local" value={due} onChange={(event) => setDue(event.target.value)} />
          </label>
        )}

        <label className="field">
          <span>
            {t("form.description")} <span className="faint">({t("common.optional")})</span>
          </span>
          <textarea
            className="textarea"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            maxLength={5000}
          />
        </label>

        <div className="field">
          <span>{t("form.priority")}</span>
          <div className="segmented">
            {[1, 2, 3].map((value) => (
              <button key={value} type="button" aria-pressed={priority === value} onClick={() => setPriority(value)}>
                {t(value === 1 ? "form.priorityLow" : value === 2 ? "form.priorityNormal" : "form.priorityHigh")}
              </button>
            ))}
          </div>
        </div>

        {error && <div className="form-error">{error}</div>}

        <div className="spread" style={{ marginTop: 4 }}>
          <div>
            {reward !== null && <div className="chip chip-gold num">{t("form.rewardPreview", { xp: reward })}</div>}
            <p className="faint small" style={{ marginTop: 6 }}>
              {t("form.rewardLocked")}
            </p>
          </div>
        </div>
        <button className="btn btn-primary btn-block" type="submit" disabled={create.isPending || !title.trim()}>
          {t("common.create")}
        </button>
      </form>
    </Sheet>
  );
}
