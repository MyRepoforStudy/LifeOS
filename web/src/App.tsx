import { BrowserRouter, Navigate, Route, Routes } from "react-router";

import { useAuth } from "./auth/AuthProvider";
import { Layout } from "./components/Layout";
import { useI18n } from "./i18n";
import { AchievementsPage } from "./pages/AchievementsPage";
import { AuthPage } from "./pages/AuthPage";
import { CycleDetailPage } from "./pages/CycleDetailPage";
import { CyclesPage } from "./pages/CyclesPage";
import { DashboardPage } from "./pages/DashboardPage";
import { HabitDetailPage } from "./pages/HabitDetailPage";
import { HabitsPage } from "./pages/HabitsPage";
import { ProfilePage } from "./pages/ProfilePage";
import { QuestDetailPage } from "./pages/QuestDetailPage";
import { QuestsPage } from "./pages/QuestsPage";

function RequireAuth() {
  const { status, retry } = useAuth();
  const { t } = useI18n();
  if (status === "loading") {
    return (
      <div className="center-screen" style={{ minHeight: "100dvh" }}>
        <div className="spinner" aria-label={t("common.loading")} />
      </div>
    );
  }
  if (status === "unreachable") {
    return (
      <div className="center-screen" style={{ minHeight: "100dvh" }}>
        <div className="empty">
          <strong>{t("errors.network_error")}</strong>
          <button className="btn" onClick={retry}>
            {t("common.retry")}
          </button>
        </div>
      </div>
    );
  }
  if (status === "anonymous") return <Navigate to="/login" replace />;
  return <Layout />;
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<RequireAuth />}>
          <Route index element={<DashboardPage />} />
          <Route path="quests" element={<QuestsPage />} />
          <Route path="quests/:id" element={<QuestDetailPage />} />
          <Route path="habits" element={<HabitsPage />} />
          <Route path="habits/:id" element={<HabitDetailPage />} />
          <Route path="cycles" element={<CyclesPage />} />
          <Route path="cycles/:id" element={<CycleDetailPage />} />
          <Route path="achievements" element={<AchievementsPage />} />
          <Route path="profile" element={<ProfilePage />} />
        </Route>
        <Route path="login" element={<AuthPage mode="login" />} />
        <Route path="register" element={<AuthPage mode="register" />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
