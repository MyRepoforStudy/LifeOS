import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";

import type { Completion } from "../api/types";
import { useI18n } from "../i18n";
import { Icon } from "./Icon";

type ToastKind = "xp" | "info" | "error";

interface Toast {
  id: number;
  kind: ToastKind;
  text: string;
}

interface Feedback {
  toast: (text: string, kind?: ToastKind) => void;
  /** Toast with the XP gained, limit notes and the level-up screen. */
  celebrate: (result: Completion) => void;
}

const FeedbackContext = createContext<Feedback | null>(null);

const SPARKS = Array.from({ length: 14 }, (_, i) => {
  const angle = (i / 14) * Math.PI * 2;
  const distance = 110 + (i % 3) * 26;
  return { dx: Math.cos(angle) * distance, dy: Math.sin(angle) * distance, delay: (i % 4) * 0.05 };
});

function LevelUp({ level, onClose }: { level: number; onClose: () => void }) {
  const { t } = useI18n();
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    button.current?.focus();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="levelup" role="dialog" aria-modal="true" aria-labelledby="levelup-title" onClick={onClose}>
      <div className="levelup-card" onClick={(event) => event.stopPropagation()}>
        <div className="sparks" aria-hidden="true">
          {SPARKS.map((spark, i) => (
            <span
              key={i}
              style={
                {
                  "--dx": `${spark.dx}px`,
                  "--dy": `${spark.dy}px`,
                  animationDelay: `${spark.delay}s`,
                } as CSSProperties
              }
            />
          ))}
        </div>
        <span className="chip chip-gold">
          <Icon name="sparkle" width={14} height={14} /> {t("common.level")}
        </span>
        <div className="levelup-number num">{level}</div>
        <h2 id="levelup-title">{t("feedback.levelUpTitle")}</h2>
        <p className="muted" style={{ marginTop: 6 }}>
          {t("feedback.levelUpBody", { level })}
        </p>
        <button ref={button} className="btn btn-primary btn-block" style={{ marginTop: 22 }} onClick={onClose}>
          {t("feedback.levelUpClose")}
        </button>
      </div>
    </div>
  );
}

export function FeedbackProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [levelUp, setLevelUp] = useState<number | null>(null);
  const nextId = useRef(1);

  const toast = useCallback((text: string, kind: ToastKind = "info") => {
    const id = nextId.current++;
    setToasts((current) => [...current.slice(-2), { id, kind, text }]);
    setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), kind === "error" ? 4200 : 2600);
  }, []);

  const celebrate = useCallback(
    (result: Completion) => {
      if (result.xp_awarded > 0) toast(t("feedback.xpGain", { xp: result.xp_awarded }), "xp");
      if (result.xp_limit_reason === "simple_task_daily_limit") toast(t("feedback.limitSimple"));
      if (result.xp_limit_reason === "learning_daily_cap") {
        toast(t("feedback.limitLearning", { minutes: result.occurrence.minutes_credited ?? 0 }));
      }
      if (result.player.leveled_up) setLevelUp(result.player.level);
    },
    [t, toast],
  );

  const value = useMemo(() => ({ toast, celebrate }), [toast, celebrate]);
  const closeLevelUp = useCallback(() => setLevelUp(null), []);

  return (
    <FeedbackContext.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((item) => (
          <div key={item.id} className={`toast ${item.kind}`}>
            {item.kind === "xp" && <Icon name="sparkle" />}
            {item.text}
          </div>
        ))}
      </div>
      {levelUp !== null && <LevelUp level={levelUp} onClose={closeLevelUp} />}
    </FeedbackContext.Provider>
  );
}

export function useFeedback(): Feedback {
  const value = useContext(FeedbackContext);
  if (!value) throw new Error("useFeedback must be used inside FeedbackProvider");
  return value;
}
