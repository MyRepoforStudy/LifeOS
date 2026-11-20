import { Link, useNavigate, useParams } from "react-router";

import { ApiError } from "../api/client";
import { useCycle } from "../api/queries";
import { CycleView } from "../components/CycleView";
import { Icon } from "../components/Icon";
import { useI18n } from "../i18n";

export function CycleDetailPage() {
  const { id = "" } = useParams();
  const { t, errorText } = useI18n();
  const navigate = useNavigate();
  const { data: cycle, error, isLoading } = useCycle(id);

  if (isLoading) {
    return (
      <main className="page center-screen">
        <div className="spinner" />
      </main>
    );
  }
  if (!cycle) {
    const notFound = error instanceof ApiError && (error.status === 404 || error.status === 422);
    return (
      <main className="page">
        <div className="empty card">
          <strong>{notFound ? t("errors.cycle_not_found") : errorText(error)}</strong>
          <Link className="link" to="/cycles">
            {t("common.back")}
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="page stack">
      <div className="row">
        <button className="icon-btn" onClick={() => navigate("/cycles")} aria-label={t("common.back")}>
          <Icon name="back" />
        </button>
        <span className="muted small">{t("nav.cycles")}</span>
      </div>
      <CycleView cycle={cycle} />
    </main>
  );
}
