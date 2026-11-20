import { useState } from "react";
import { Link } from "react-router";

import { useApplyRecommendation, useDismissRecommendation } from "../api/queries";
import type { AdaptiveRecommendation } from "../api/types";
import { useI18n } from "../i18n";
import { adviceText, adviceTitle, changeText } from "../lib/adaptive";
import { useFeedback } from "./Feedback";
import { Icon } from "./Icon";

interface AdviceCardProps {
  advice: AdaptiveRecommendation;
  /** The dashboard version: the text and a link to the full advice. */
  compact?: boolean;
}

/** A recommendation: nothing in the plan changes until the player presses Apply. */
export function AdviceCard({ advice, compact }: AdviceCardProps) {
  const { t, locale, errorText } = useI18n();
  const { toast } = useFeedback();
  const apply = useApplyRecommendation();
  const dismiss = useDismissRecommendation();
  // Every change is chosen at first; the player can untick the ones they do not want.
  const [selected, setSelected] = useState<Set<number>>(() => new Set(advice.changes.map((_, index) => index)));
  const busy = apply.isPending || dismiss.isPending;
  const onError = (error: unknown) => toast(errorText(error), "error");

  const toggle = (index: number) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });

  const onApply = () =>
    apply.mutate(
      { id: advice.id, changes: [...selected].sort((a, b) => a - b) },
      { onSuccess: () => toast(t("insights.applied")), onError },
    );
  const onDismiss = () => dismiss.mutate(advice.id, { onSuccess: () => toast(t("insights.dismissed")), onError });

  const head = (
    <div className="advice-head">
      <span className="advice-icon" aria-hidden="true">
        <Icon name="bulb" />
      </span>
      <div className="advice-titles">
        <span className="eyebrow">{t("insights.adviceTitle")}</span>
        <strong>{adviceTitle(t, advice)}</strong>
      </div>
    </div>
  );

  if (compact) {
    return (
      <section className="card advice stack" style={{ gap: 12 }}>
        {head}
        <p className="muted small">{adviceText(t, advice)}</p>
        <div className="row" style={{ flexWrap: "wrap" }}>
          <Link className="btn btn-small btn-primary" to="/insights">
            {advice.changes.length > 0 ? t("insights.changesCount", { n: advice.changes.length }) : t("insights.more")}
          </Link>
          <button className="btn btn-small btn-ghost" onClick={onDismiss} disabled={busy}>
            {t("insights.dismiss")}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="card advice stack" style={{ gap: 12 }}>
      {head}
      <p className="muted">{adviceText(t, advice)}</p>
      {advice.changes.length > 0 && (
        <ul className="change-list">
          {advice.changes.map((change, index) => (
            <li key={index}>
              <label className="change-item">
                <input
                  type="checkbox"
                  checked={selected.has(index)}
                  onChange={() => toggle(index)}
                  disabled={busy}
                />
                <span>{changeText(t, change, locale)}</span>
              </label>
            </li>
          ))}
        </ul>
      )}
      <div className="row" style={{ flexWrap: "wrap" }}>
        {advice.changes.length > 0 && (
          <button className="btn btn-primary" onClick={onApply} disabled={busy || selected.size === 0}>
            <Icon name="check" />
            {selected.size === advice.changes.length ? t("insights.apply") : t("insights.applySelected")}
          </button>
        )}
        <button className="btn btn-ghost" onClick={onDismiss} disabled={busy}>
          {t("insights.dismiss")}
        </button>
      </div>
    </section>
  );
}
