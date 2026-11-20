import type { ReactNode } from "react";

/** A small labelled number tile. */
export function Stat({ label, value, gold }: { label: string; value: ReactNode; gold?: boolean }) {
  return (
    <div className="stat">
      <div className="faint small">{label}</div>
      <div className={gold ? "stat-value num gold" : "stat-value num"}>{value}</div>
    </div>
  );
}
