import { useEffect, useRef, useState } from "react";

interface ProgressBarProps {
  value: number;
  thin?: boolean;
  label?: string;
  /** Any value that grows when XP is gained; a change plays a short shimmer. */
  pulseOn?: number;
}

export function ProgressBar({ value, thin, label, pulseOn }: ProgressBarProps) {
  const [glow, setGlow] = useState(false);
  const previous = useRef(pulseOn);

  useEffect(() => {
    if (pulseOn !== undefined && previous.current !== undefined && pulseOn > previous.current) {
      setGlow(true);
      const timer = setTimeout(() => setGlow(false), 1300);
      previous.current = pulseOn;
      return () => clearTimeout(timer);
    }
    previous.current = pulseOn;
    return undefined;
  }, [pulseOn]);

  const percent = Math.round(Math.min(1, Math.max(0, value)) * 1000) / 10;
  return (
    <div
      className={thin ? "progress thin" : "progress"}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
    >
      <div className={glow ? "progress-fill glow" : "progress-fill"} style={{ width: `${percent}%` }} />
    </div>
  );
}
