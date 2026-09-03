/**
 * MagicUI Safari mockup, vendored: a browser chrome around a screenshot or
 * live children. Greys are the system's; the URL text uses the muted ink.
 */
import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

const SAFARI_WIDTH = 1203;
const SAFARI_HEIGHT = 753;
const SCREEN_X = 1;
const SCREEN_Y = 52;
const SCREEN_WIDTH = 1200;
const SCREEN_HEIGHT = 700;

const LEFT_PCT = (SCREEN_X / SAFARI_WIDTH) * 100;
const TOP_PCT = (SCREEN_Y / SAFARI_HEIGHT) * 100;
const WIDTH_PCT = (SCREEN_WIDTH / SAFARI_WIDTH) * 100;
const HEIGHT_PCT = (SCREEN_HEIGHT / SAFARI_HEIGHT) * 100;

export interface SafariProps extends HTMLAttributes<HTMLDivElement> {
  url?: string;
  imageSrc?: string;
  children?: ReactNode;
}

export function Safari({ imageSrc, url, children, className, style, ...props }: SafariProps) {
  const hasMedia = Boolean(imageSrc || children);
  return (
    <div
      className={cn("relative inline-block w-full align-middle leading-none", className)}
      style={{ aspectRatio: `${SAFARI_WIDTH}/${SAFARI_HEIGHT}`, ...style }}
      {...props}
    >
      {hasMedia ? (
        <div
          className="absolute z-0 overflow-hidden bg-canvas"
          style={{
            left: `${LEFT_PCT}%`,
            top: `${TOP_PCT}%`,
            width: `${WIDTH_PCT}%`,
            height: `${HEIGHT_PCT}%`,
            borderRadius: "0 0 11px 11px",
          }}
        >
          {children ?? (
            // eslint-disable-next-line @next/next/no-img-element -- a mockup, not a content image
            <img src={imageSrc} alt="" className="block size-full object-cover object-top" />
          )}
        </div>
      ) : null}

      <svg
        viewBox={`0 0 ${SAFARI_WIDTH} ${SAFARI_HEIGHT}`}
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="pointer-events-none absolute inset-0 z-10 size-full"
        style={{ transform: "translateZ(0)" }}
      >
        <defs>
          <mask id="safariPunch" maskUnits="userSpaceOnUse">
            <rect x="0" y="0" width={SAFARI_WIDTH} height={SAFARI_HEIGHT} fill="white" />
            <path d="M1 52H1201V741C1201 747.075 1196.08 752 1190 752H12C5.92486 752 1 747.075 1 741V52Z" fill="black" />
          </mask>
        </defs>
        <g mask={hasMedia ? "url(#safariPunch)" : undefined}>
          <path d="M0 52H1202V741C1202 747.627 1196.63 753 1190 753H12C5.37258 753 0 747.627 0 741V52Z" className="fill-hairline" />
          <path
            fillRule="evenodd"
            clipRule="evenodd"
            d="M0 12C0 5.37258 5.37258 0 12 0H1190C1196.63 0 1202 5.37258 1202 12V52H0L0 12Z"
            className="fill-hairline"
          />
          <path
            fillRule="evenodd"
            clipRule="evenodd"
            d="M1.06738 12C1.06738 5.92487 5.99225 1 12.0674 1H1189.93C1196.01 1 1200.93 5.92487 1200.93 12V51H1.06738V12Z"
            className="fill-canvas-parchment"
          />
          <circle cx="27" cy="25" r="6" className="fill-hairline" />
          <circle cx="47" cy="25" r="6" className="fill-hairline" />
          <circle cx="67" cy="25" r="6" className="fill-hairline" />
          <path
            d="M286 17C286 13.6863 288.686 11 292 11H946C949.314 11 952 13.6863 952 17V35C952 38.3137 949.314 41 946 41H292C288.686 41 286 38.3137 286 35V17Z"
            className="fill-canvas"
          />
          <text x="600" y="30" textAnchor="middle" fontSize="12" fontFamily="system-ui, sans-serif" className="fill-ink-muted-48">
            {url}
          </text>
        </g>
      </svg>
    </div>
  );
}
