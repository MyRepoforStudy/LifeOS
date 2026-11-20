import { useState, type FormEvent } from "react";

import { useCreateHabit } from "../api/queries";
import { CATEGORIES, type HabitDraft, type HabitFrequency, type QuestCategory } from "../api/types";
import { useI18n, type MessageKey } from "../i18n";
import { newId } from "../lib/id";
import { useFeedback } from "./Feedback";
import { useRewardRules } from "./QuestForm";
import { Sheet } from "./Sheet";

const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7];
const FREQUENCIES: { value: HabitFrequency; label: MessageKey }[] = [
  { value: "daily", label: "habits.frequencyDaily" },
  { value: "weekdays", label: "habits.frequencyWeekdays" },
  { value: "weekly", label: "habits.frequencyWeekly" },
];

export function HabitForm({ onClose }: { onClose: () => void }) {
  const { t, errorText } = useI18n();
  const { toast } = useFeedback();
  const rules = useRewardRules();
  const create = useCreateHabit();
  // One key per opened form: a double tap or a retry cannot create two habits.
  const [idempotencyKey] = useState(newId);

  const [title, setTitle] = useState("");
  const [category, setCategory] = useState<QuestCategory>("health");
  const [frequency, setFrequency] = useState<HabitFrequency>("daily");
  const [weekdays, setWeekdays] = useState<number[]>([1, 3, 5]);
  const [timesPerWeek, setTimesPerWeek] = useState(3);
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  const toggleWeekday = (day: number) =>
    setWeekdays((current) =>
      current.includes(day) ? current.filter((d) => d !== day) : [...current, day].sort((a, b) => a - b),
    );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const draft: HabitDraft = {
      title: title.trim(),
      category,
      frequency,
      description: description.trim() || null,
      weekdays: frequency === "weekdays" ? weekdays : null,
      times_per_week: frequency === "weekly" ? timesPerWeek : null,
    };
    create.mutate(
      { draft, key: idempotencyKey },
      {
        onSuccess: () => {
          toast(t("feedback.habitCreated"));
          onClose();
        },
        onError: (err) => setError(errorText(err)),
      },
    );
  };

  const invalid = !title.trim() || (frequency === "weekdays" && weekdays.length === 0);

  return (
    <Sheet title={t("habits.newHabit")} onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <label className="field">
          <span>{t("form.title")}</span>
          <input
            className="input"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder={t("habits.titlePlaceholder")}
            maxLength={200}
            required
          />
        </label>

        <div className="field">
          <span>{t("form.category")}</span>
          <div className="choice-grid">
            {CATEGORIES.map((option) => (
              <button
                key={option}
                type="button"
                className="choice"
                aria-pressed={option === category}
                onClick={() => setCategory(option)}
              >
                {t(`category.${option}`)}
              </button>
            ))}
          </div>
        </div>

        <div className="field">
          <span>{t("habits.frequency")}</span>
          <div className="segmented">
            {FREQUENCIES.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={frequency === option.value}
                onClick={() => setFrequency(option.value)}
              >
                {t(option.label)}
              </button>
            ))}
          </div>
        </div>

        {frequency === "weekdays" && (
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
                  {t(`weekday.${day}` as MessageKey)}
                </button>
              ))}
            </div>
          </div>
        )}

        {frequency === "weekly" && (
          <div className="field">
            <span>{t("habits.timesPerWeekLabel")}</span>
            <div className="choice-grid">
              {[1, 2, 3, 4, 5, 6, 7].map((n) => (
                <button
                  key={n}
                  type="button"
                  className="choice num"
                  aria-pressed={timesPerWeek === n}
                  onClick={() => setTimesPerWeek(n)}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>
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

        {error && <div className="form-error">{error}</div>}

        <div>
          <span className="chip chip-gold num">{t("form.rewardPreview", { xp: rules.data?.habit ?? 15 })}</span>
          <p className="faint small" style={{ marginTop: 6 }}>
            {t("habits.scheduleLocked")}
          </p>
        </div>
        <button className="btn btn-primary btn-block" type="submit" disabled={create.isPending || invalid}>
          {t("common.create")}
        </button>
      </form>
    </Sheet>
  );
}
