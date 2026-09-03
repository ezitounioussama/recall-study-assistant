/**
 * The iPhone Air page's grammar, which is a quieter dialect of the design
 * language than the analysis document describes.
 *
 * All spacing, colour and type below uses Tailwind utilities generated from the
 * `@theme` tokens — `p-lg`, `text-lead-copy`, `bg-canvas-parchment` — rather
 * than the arbitrary bracket syntax this file used first. Tailwind v4 derives a
 * utility for every custom property in the `--spacing-*`, `--text-*` and `--color-*`
 * namespaces, so the token layer and the class names stay one system. The
 * arbitrary-value syntax works and reads as an escape hatch, which invites more
 * of them.
 */
import type { ReactNode } from "react";

/**
 * Full-bleed section. Light-dominant, unlike the homepage's alternating dark
 * bands: the product page carries its rhythm through whitespace and a
 * white/parchment step rather than through contrast.
 */
export function Section({
  surface = "light",
  children,
  className = "",
  id,
  tall = false,
}: {
  surface?: "light" | "parchment" | "pearl" | "dark";
  children: ReactNode;
  className?: string;
  id?: string;
  /** Hero-scale vertical air. The product page's opening screen is well over
   *  one viewport, and the emptiness is the design. */
  tall?: boolean;
}) {
  const surfaces = {
    light: "bg-canvas text-ink",
    parchment: "bg-canvas-parchment text-ink",
    pearl: "bg-surface-pearl text-ink",
    dark: "bg-surface-tile-1 text-on-dark",
  } as const;

  return (
    <section
      id={id}
      className={`${surfaces[surface]} px-lg ${tall ? "py-[140px]" : "py-section"} ${className}`}
    >
      <div className="mx-auto w-full max-w-[1440px]">{children}</div>
    </section>
  );
}

/**
 * The two-tone product name: the family in full ink, the model in grey.
 *
 * On the reference page "iPhone" is set in ink and "Air" in a lighter tone, in
 * one line of continuous type. It reads as a single lockup rather than a
 * headline with a modifier, which is the whole effect.
 */
export function ProductName({ family, model }: { family: string; model: string }) {
  return (
    <h1 className="text-center font-display text-display-lg md:text-product-name">
      <span className="text-ink">{family}</span>{" "}
      <span className="font-normal text-lead-grey">{model}</span>
    </h1>
  );
}

/**
 * The 40px/400 tagline under the product name. Two short lines, centred, grey.
 *
 * Weight 400 at 40px is the thing that makes the reference page feel calm where
 * a 600 would make it feel like marketing. The analysis document specifies 600
 * for display sizes; this follows the live page instead.
 */
export function ProductTagline({ children }: { children: ReactNode }) {
  return (
    <p className="mx-auto mt-lg max-w-[24ch] text-center font-display text-lead-copy text-lead-grey md:text-product-tagline">
      {children}
    </p>
  );
}

/**
 * Long-form lead copy in grey, with emphasis in full ink.
 *
 * The reference page's body treatment: a grey paragraph with two or three
 * phrases in near-black, so the eye lands on the claims without a heading. Pass
 * emphasis as `<Emphasis>` children rather than `<strong>`, so the weight stays
 * 400 — the emphasis here is *colour*, not weight, and a bold run would break
 * the 300/400/600/700 ladder by implying 500.
 */
export function LeadCopy({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <p
      className={`mx-auto max-w-[30ch] text-center font-display text-tagline text-lead-grey md:text-lead-copy ${className}`}
    >
      {children}
    </p>
  );
}

export function Emphasis({ children }: { children: ReactNode }) {
  return <span className="text-ink">{children}</span>;
}

/**
 * The pearl capsule with a blue circular icon — the reference page's
 * expand-for-detail control ("Comparer le design des iPhone" with a blue plus).
 *
 * Two radii in one control, which the analysis document warns against mixing:
 * the capsule is a pill and the icon is a circle. On the live page they nest,
 * and it works because the circle is a distinct affordance inside the capsule
 * rather than a second button beside it.
 */
export function ExpandCapsule({
  label,
  onClick,
  expanded = false,
}: {
  label: string;
  onClick?: () => void;
  expanded?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={expanded}
      className="inline-flex min-h-11 cursor-pointer items-center gap-sm rounded-pill border-0 bg-canvas-parchment py-xs pr-xs pl-lg text-body-strong text-ink"
    >
      {label}
      <span className="inline-flex size-8 items-center justify-center rounded-pill bg-primary text-on-primary">
        {/* An inline SVG rather than an icon dependency: two glyphs do not
            justify a package, and the plus/minus has to animate between states
            anyway. */}
        <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" fill="currentColor">
          <rect x="1" y="7" width="14" height="2" rx="1" />
          {!expanded ? <rect x="7" y="1" width="2" height="14" rx="1" /> : null}
        </svg>
      </span>
    </button>
  );
}

/**
 * A section eyebrow — "Design", "Caméras", "Performances et autonomie" on the
 * reference page. Small, ink, and sitting well above its heading rather than
 * tucked against it.
 */
export function Eyebrow({ children, onDark = false }: { children: ReactNode; onDark?: boolean }) {
  return (
    <p
      className={`mb-lg text-center text-body-strong ${onDark ? "text-body-muted" : "text-ink-muted-48"}`}
    >
      {children}
    </p>
  );
}

/**
 * A big claim: a 40px/400 statement, centred, with optional grey continuation.
 * The reference page repeats this shape down the whole document — a claim, then
 * a paragraph, then air.
 */
export function Claim({ children }: { children: ReactNode }) {
  return (
    <h2 className="mx-auto max-w-[26ch] text-center font-display text-display-md text-ink md:text-section-head">
      {children}
    </h2>
  );
}

/**
 * A statistic set large, as the reference page does with "40 % plus rapide" and
 * "8 heures de plus". The number carries the weight; the label stays quiet.
 */
export function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="text-center">
      <p className="font-display text-display-md text-ink md:text-section-head">{value}</p>
      <p className="mt-xs text-body text-lead-grey">{label}</p>
    </div>
  );
}
