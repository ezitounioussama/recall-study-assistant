/**
 * The floating nav island from the iPhone Air page.
 *
 * The analysis document describes a flat, full-width frosted strip. The live
 * page does something else: a rounded white card, inset from both edges, riding
 * above the content with a soft shadow. Product name on the left, a pearl
 * secondary and a blue primary on the right.
 *
 * That means chrome carrying elevation, which docs/design-language.md
 * explicitly forbids. The divergence is deliberate and recorded in
 * docs/design-divergences.md.
 */
import Link from "next/link";
import type { ReactNode } from "react";

/**
 * The thin top bar. The product page's is white with ink text, not the
 * homepage's true-black — a product page is a light surface end to end, and a
 * black bar above a white hero would read as a lid.
 */
export function ProductTopBar({ children }: { children?: ReactNode }) {
  return (
    <nav
      aria-label="Primary"
      className="sticky top-0 z-50 flex h-11 items-center bg-canvas/80 backdrop-blur-xl"
    >
      <div className="mx-auto flex w-full max-w-[1024px] items-center justify-between px-lg">
        <Link href="/" className="text-nav-link font-semibold text-ink">
          Recall
        </Link>
        <div className="flex items-center gap-xl">{children}</div>
      </div>
    </nav>
  );
}

export function TopBarLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="text-nav-link text-ink">
      {children}
    </Link>
  );
}

/**
 * The island. `top-[52px]` parks it just below the 44px top bar with a small
 * gap, so it reads as floating rather than docked — the gap is what makes the
 * shadow legible.
 */
export function FloatingNav({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="sticky top-[52px] z-40 px-lg">
      <div className="mx-auto flex h-[68px] w-full max-w-[1024px] items-center justify-between rounded-lg bg-canvas/90 px-lg shadow-float backdrop-blur-xl">
        <span className="text-tagline text-ink">{title}</span>
        <div className="flex items-center gap-sm">{children}</div>
      </div>
    </div>
  );
}

/**
 * The island's two button sizes. Smaller than the page's main CTAs — the nav's
 * job is to stay available, not to compete with the hero, so these sit at 14px
 * rather than the 17px the body CTAs use.
 */
export function NavPill({
  href,
  children,
  variant = "primary",
}: {
  href: string;
  children: ReactNode;
  variant?: "primary" | "pearl";
}) {
  const styles =
    variant === "primary"
      ? "bg-primary text-on-primary"
      : "bg-canvas-parchment text-ink";
  return (
    <Link
      href={href}
      data-pressable
      className={`inline-flex min-h-8 items-center rounded-pill px-md py-xs text-caption ${styles}`}
    >
      {children}
    </Link>
  );
}
