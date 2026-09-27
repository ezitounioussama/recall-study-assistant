import { useId } from "react";

/**
 * The Recall mark: a speech bubble holding an R — ask your notes, say the
 * answer out loud. The same drawing as src/app/icon.svg and docs/brand/, but
 * coloured from the tokens so it follows globals.css.
 */
export function LogoMark({ size = 20, className = "" }: { size?: number; className?: string }) {
  const gradient = useId();
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden className={className}>
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" style={{ stopColor: "var(--color-primary)" }} />
          <stop offset="1" style={{ stopColor: "var(--color-primary-on-dark)" }} />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="15" fill={`url(#${gradient})`} />
      <path
        d="M12 18.5A7.5 7.5 0 0 1 19.5 11h25A7.5 7.5 0 0 1 52 18.5v19A7.5 7.5 0 0 1 44.5 45H30l-11 9v-9.3A7.5 7.5 0 0 1 12 37.5z"
        style={{ fill: "var(--color-on-primary)" }}
      />
      <path
        d="M26 38V18h7.5a6 6 0 0 1 0 12H26M32.5 30l6.5 8"
        fill="none"
        strokeWidth="5.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ stroke: "var(--color-primary)" }}
      />
    </svg>
  );
}
