import { useEffect, useRef, type ReactNode } from "react";

import { useI18n } from "../i18n";
import { Icon } from "./Icon";

interface SheetProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
}

/** Bottom sheet on phones, centered dialog on wider screens. */
export function Sheet({ title, onClose, children }: SheetProps) {
  const { t } = useI18n();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLElement>("input, select, textarea, button")?.focus();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      previous?.focus?.();
    };
  }, [onClose]);

  return (
    <div className="backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div ref={panel} className="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title">
        <div className="sheet-handle" />
        <div className="sheet-header">
          <h2 id="sheet-title">{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label={t("common.close")}>
            <Icon name="close" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
