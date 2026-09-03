/**
 * The five button grammars from the design language, and nothing else.
 *
 * Two rules the spec is emphatic about, both enforced here by construction:
 *
 *   1. `pill` radius means "this is an action". It is not decoration, and it is
 *      not available to non-actions.
 *   2. No shadows. Elevation in this system comes from surface colour, and the
 *      single drop-shadow is reserved for product imagery.
 *
 * Hover is deliberately unstyled. The spec documents default and pressed
 * states only, and the press state — scale(0.95) — is applied globally in
 * globals.css so everything pressable shares one micro-interaction.
 */
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant =
  /** Action Blue pill. The signature. 17px/400, 11px x 22px. */
  | "primary"
  /** Ghost pill: transparent with a 1px Action Blue border. The second CTA. */
  | "secondary"
  /** Compact near-black rect at 8px radius. Nav actions. */
  | "dark-utility"
  /** Near-white capsule at 11px radius. Card secondary action. */
  | "pearl"
  /** Larger primary for store heroes. 18px/300 — the rare weight 300. */
  | "store-hero";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-primary text-on-primary rounded-pill px-[22px] py-[11px] text-body",
  secondary:
    "bg-transparent text-primary border border-primary rounded-pill px-[22px] py-[11px] text-body",
  "dark-utility": "bg-ink text-on-dark rounded-sm px-[15px] py-[8px] text-button-utility",
  pearl:
    "bg-surface-pearl text-ink-muted-80 rounded-md px-[14px] py-[8px] text-caption border-[3px] border-divider-soft",
  "store-hero": "bg-primary text-on-primary rounded-pill px-[28px] py-[14px] text-button-large",
};

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  children: ReactNode;
};

export function Button({ variant = "primary", className = "", children, ...rest }: Props) {
  return (
    <button
      type="button"
      // min-h-11 is 44px — the spec's minimum touch target. The pill radius
      // makes the visible hit area feel more generous than the label, but the
      // height still has to be real.
      className={`inline-flex min-h-11 cursor-pointer items-center justify-center border-0 font-[inherit] disabled:cursor-not-allowed disabled:text-ink-muted-48 ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

/**
 * 44x44 circular control that floats over photography. The translucent fill is
 * the spec's chip grey at 64% alpha — the one place a colour token is used with
 * transparency, which is why it goes through color-mix rather than an inline
 * rgba the token checker would reject.
 */
export function IconButton({
  label,
  className = "",
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      className={`inline-flex size-11 cursor-pointer items-center justify-center rounded-pill border-0 text-ink [background-color:color-mix(in_srgb,var(--color-surface-chip-translucent)_64%,transparent)] ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
