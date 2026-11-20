import { Link } from "react-router";

import { useAnalysis, useRecommendations } from "../api/queries";
import { useI18n } from "../i18n";
import { percent } from "../lib/adaptive";
import { AdviceCard } from "./AdviceCard";
import { Icon } from "./Icon";

/** Dashboard: the newest pending advice, or a quiet link to the weekly numbers. */
export function InsightsCard() {
  const { t } = useI18n();
  const { data: advice } = useRecommendations();
  const { data: analysis } = useAnalysis();
  const top = advice?.find((item) => item.status === "pending");
  if (top) return <AdviceCard key={top.id} advice={top} compact />;
  if (!analysis) return null;
  const week = analysis.week;
  return (
    <Link to="/insights" className="card spread cycle-card">
      <span className="row" style={{ fontWeight: 600 }}>
        <Icon name="bulb" width={20} height={20} style={{ color: "var(--gold)", flex: "none" }} />
        {week.planned > 0 ? t("insights.weekLink", { rate: percent(week.rate) }) : t("insights.weekLinkEmpty")}
      </span>
      <Icon name="next" width={18} height={18} style={{ flex: "none" }} />
    </Link>
  );
}
