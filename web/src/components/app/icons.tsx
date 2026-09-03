/** The four glyphs the dock needs. Inline, 24px grid, stroke-only, so they take the current colour. */
import type { SVGProps } from "react";

const base = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export function LibraryIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H9a1.5 1.5 0 0 1 1.5 1.5v14A1.5 1.5 0 0 1 9 21H5.5A1.5 1.5 0 0 1 4 19.5z" />
      <path d="M12 5.5A1.5 1.5 0 0 1 13.5 4H16a1.5 1.5 0 0 1 1.5 1.5v14A1.5 1.5 0 0 1 16 21h-2.5a1.5 1.5 0 0 1-1.5-1.5z" />
      <path d="m18.2 6.1 1.9-.5 3 12.6-1.9.5z" />
    </svg>
  );
}

export function AskIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v7a2.5 2.5 0 0 1-2.5 2.5H10l-4.4 3.5V16H6.5A2.5 2.5 0 0 1 4 13.5z" />
      <path d="M8.5 9h7M8.5 12h4.5" />
    </svg>
  );
}

export function ReviewIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <rect x="6" y="7" width="14" height="13" rx="2" />
      <path d="M4 15V6a2 2 0 0 1 2-2h10" />
      <path d="m10 14 2 2 4-4" />
    </svg>
  );
}

export function SignOutIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M10 4H6.5A2.5 2.5 0 0 0 4 6.5v11A2.5 2.5 0 0 0 6.5 20H10" />
      <path d="M14 8l4 4-4 4M18 12H9" />
    </svg>
  );
}

export function UploadIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M12 16V5M7.5 9.5 12 5l4.5 4.5" />
      <path d="M5 15v2.5A2.5 2.5 0 0 0 7.5 20h9a2.5 2.5 0 0 0 2.5-2.5V15" />
    </svg>
  );
}
