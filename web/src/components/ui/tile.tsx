/**
 * Full-bleed tiles — the structural unit of the whole layout.
 *
 * The spec's central layout idea: sections stack edge-to-edge with zero gap and
 * no borders, and the *surface colour change is the divider*. So there is no
 * `border`, no `gap`, and no radius here, and `Tile` deliberately exposes no
 * prop to add any. If a section needs to feel separated, alternate its surface.
 *
 * Three dark surfaces exist because they are one micro-step apart in lightness:
 * tile-2 (#2a2a2c) sits directly above or below tile-1 (#272729) to create the
 * faintest separation, and tile-3 (#252527) anchors the bottom of a stack. They
 * are not interchangeable, which is why the type names them rather than taking
 * a number.
 */
import type { ReactNode } from "react";

type Surface =
  | "light" /** pure white — the dominant canvas */
  | "parchment" /** #f5f5f7 — breaks two consecutive white tiles */
  | "dark" /** #272729 — the primary dark band */
  | "dark-2" /** #2a2a2c — a micro-step lighter, for adjacency */
  | "dark-3" /** #252527 — a micro-step darker, for the bottom of a stack */
  | "black"; /** true void — video frames only */

const SURFACES: Record<Surface, string> = {
  light: "bg-canvas text-ink",
  parchment: "bg-canvas-parchment text-ink",
  dark: "bg-surface-tile-1 text-on-dark",
  "dark-2": "bg-surface-tile-2 text-on-dark",
  "dark-3": "bg-surface-tile-3 text-on-dark",
  black: "bg-surface-black text-on-dark",
};

export function Tile({
  surface = "light",
  children,
  className = "",
  id,
}: {
  surface?: Surface;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} className={`tile ${SURFACES[surface]} ${className}`}>
      {/* 1440px content lock with the margins absorbing extra width, per the
          spec's wide-desktop rule. Text-heavy sections narrow themselves
          further with their own max-width. */}
      <div className="mx-auto w-full max-w-[1440px]">{children}</div>
    </section>
  );
}

/**
 * The centred content stack every product tile uses: headline, one-line
 * tagline, then up to two pill CTAs. Fixed on purpose — the repetition of this
 * exact rhythm across every tile is what makes the page read as one system.
 */
export function TileHeader({
  eyebrow,
  headline,
  tagline,
  children,
  align = "center",
  onDark = false,
}: {
  eyebrow?: string;
  headline: ReactNode;
  tagline?: ReactNode;
  children?: ReactNode;
  align?: "center" | "start";
  onDark?: boolean;
}) {
  const isCentre = align === "center";
  return (
    <div className={`flex flex-col ${isCentre ? "items-center text-center" : "items-start"}`}>
      {eyebrow ? (
        // Eyebrows carry the accent. On a dark tile Action Blue disappears, so
        // the brighter Sky Link Blue takes over — the spec is explicit that
        // these two are not interchangeable across surfaces.
        <p
          className={`mb-[var(--spacing-sm)] text-caption-strong uppercase ${
            onDark ? "text-primary-on-dark" : "text-primary"
          }`}
          style={{ letterSpacing: "0.06em" }}
        >
          {eyebrow}
        </p>
      ) : null}

      {/* -0.01em on top of the token's own tracking: Inter runs wider than SF
          Pro, and the spec's substitution note prescribes exactly this nudge
          to recover the "Apple tight" cadence. */}
      <h2 className="max-w-[18ch] text-display-lg [letter-spacing:-0.01em]">{headline}</h2>

      {tagline ? (
        <p
          className={`mt-[var(--spacing-lg)] max-w-[36ch] text-lead ${
            onDark ? "text-body-muted" : "text-ink-muted-80"
          }`}
        >
          {tagline}
        </p>
      ) : null}

      {children ? (
        <div
          className={`mt-[var(--spacing-xxl)] flex flex-wrap items-center gap-[var(--spacing-sm)] ${
            isCentre ? "justify-center" : ""
          }`}
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}

/**
 * A utility card: white, 1px hairline, 18px radius, 24px padding.
 *
 * No shadow — not by omission. The spec allows exactly one drop-shadow in the
 * system and it belongs to product photography. A card that needs to stand out
 * gets a different surface behind it, not elevation.
 */
export function Card({
  children,
  className = "",
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "li" | "article";
}) {
  return (
    <Tag
      className={`rounded-lg border border-hairline bg-canvas p-[var(--spacing-lg)] text-ink ${className}`}
    >
      {children}
    </Tag>
  );
}
