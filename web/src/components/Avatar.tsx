import { useId } from "react";

import { useI18n } from "../i18n";
import { initials } from "../lib/format";

interface AvatarProps {
  name: string;
  imageUrl?: string | null;
  level: number;
  /** 0..1 progress inside the current level, drawn as a ring. */
  progress: number;
  size?: number;
}

export function Avatar({ name, imageUrl, level, progress, size = 72 }: AvatarProps) {
  const { t } = useI18n();
  // useId output may contain characters that break url(#...) references.
  const gradientId = `ring${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const radius = size / 2 - 3;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.min(1, Math.max(0, progress));
  return (
    <div className="avatar" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#ffd27a" />
            <stop offset="1" stopColor="#d98f22" />
          </linearGradient>
        </defs>
        <circle className="avatar-ring-track" cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={4} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={4}
          strokeLinecap="round"
          stroke={`url(#${gradientId})`}
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - clamped)}
          style={{ transition: "stroke-dashoffset 0.9s cubic-bezier(0.22, 1, 0.36, 1)" }}
        />
      </svg>
      <div className="avatar-face">{imageUrl ? <img src={imageUrl} alt="" /> : initials(name)}</div>
      <span className="level-chip num">
        {t("common.levelShort")} {level}
      </span>
    </div>
  );
}
