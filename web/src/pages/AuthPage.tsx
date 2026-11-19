import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router";

import { useAuth } from "../auth/AuthProvider";
import { LanguageSwitch } from "../components/LanguageSwitch";
import { useI18n } from "../i18n";
import { browserTimeZone } from "../lib/format";

export function AuthPage({ mode }: { mode: "login" | "register" }) {
  const { t, errorText } = useI18n();
  const auth = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const timezone = browserTimeZone();

  if (auth.status === "authenticated") return <Navigate to="/" replace />;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      if (mode === "login") await auth.login(email, password);
      else await auth.register({ email, password, display_name: displayName.trim(), timezone });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setPending(false);
    }
  };

  const isLogin = mode === "login";
  return (
    <main className="auth">
      <div className="auth-card">
        <div className="auth-brand">
          <img src="/favicon.svg" alt="" />
          <h1>{t("app.name")}</h1>
          <p className="muted">{t("app.tagline")}</p>
        </div>
        <form className="card stack" onSubmit={submit}>
          <div className="spread">
            <h2>{isLogin ? t("auth.loginTitle") : t("auth.registerTitle")}</h2>
            <LanguageSwitch />
          </div>
          {!isLogin && (
            <label className="field">
              <span>{t("auth.displayName")}</span>
              <input
                className="input"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                autoComplete="nickname"
                maxLength={100}
                required
              />
            </label>
          )}
          <label className="field">
            <span>{t("auth.email")}</span>
            <input
              className="input"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              required
            />
          </label>
          <label className="field">
            <span>{t("auth.password")}</span>
            <input
              className="input"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={isLogin ? "current-password" : "new-password"}
              minLength={isLogin ? 1 : 8}
              maxLength={128}
              required
            />
            {!isLogin && <small className="faint">{t("auth.passwordHint")}</small>}
          </label>
          {!isLogin && <p className="faint small">{t("auth.timezoneHint", { tz: timezone })}</p>}
          {error && <div className="form-error">{error}</div>}
          <button className="btn btn-primary btn-block" type="submit" disabled={pending}>
            {isLogin ? t("auth.submitLogin") : t("auth.submitRegister")}
          </button>
          <Link className="link" to={isLogin ? "/register" : "/login"} style={{ textAlign: "center" }}>
            {isLogin ? t("auth.toRegister") : t("auth.toLogin")}
          </Link>
        </form>
      </div>
    </main>
  );
}
