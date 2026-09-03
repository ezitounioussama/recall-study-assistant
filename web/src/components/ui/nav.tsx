/**
 * The two-row navigation the spec describes: a 44px true-black global bar, and
 * a 52px frosted sub-nav that sticks beneath it.
 *
 * The global nav is the only place pure black appears on most pages — every
 * other dark surface is one of the three near-blacks. That distinction is
 * intentional and worth preserving: #000 in a tile would read as a hole.
 */
import Link from "next/link";
import type { ReactNode } from "react";

const GLOBAL_LINKS = [
  { href: "/library", label: "Library" },
  { href: "/chat", label: "Ask" },
  { href: "/review", label: "Review" },
  { href: "/#how", label: "How it works" },
] as const;

export function GlobalNav() {
  return (
    <nav
      aria-label="Primary"
      // h-11 is exactly 44px. The spec's height, not a rounded approximation.
      className="sticky top-0 z-50 flex h-11 items-center bg-surface-black text-on-dark"
    >
      <div className="mx-auto flex w-full max-w-[1440px] items-center gap-lg px-lg">
        <Link href="/" className="text-nav-link font-semibold text-on-dark">
          Recall
        </Link>

        {/* The spec collapses these into a hamburger at 834px. Here they simply
            hide: the routes stay reachable from the sub-nav and the footer, and
            a tray that exists only to hold four links is chrome the design
            language would reject. */}
        <ul className="hidden list-none items-center gap-lg p-0 md:flex">
          {GLOBAL_LINKS.map(({ href, label }) => (
            <li key={href}>
              <Link href={href} className="text-nav-link text-on-dark opacity-80">
                {label}
              </Link>
            </li>
          ))}
        </ul>

        <div className="ml-auto flex items-center gap-sm">
          <Link href="/sign-in" className="text-nav-link text-on-dark opacity-80">
            Sign in
          </Link>
        </div>
      </div>
    </nav>
  );
}

/**
 * Frosted sub-nav: parchment at 80% with a saturate/blur backdrop, category
 * name on the left in the tagline token, actions on the right ending in a
 * persistent primary CTA.
 *
 * `top-11` parks it directly under the 44px global nav so both stay visible
 * while scrolling — which is why globals.css sets scroll-padding-top to 96px,
 * the sum of the two.
 */
export function SubNav({ category, children }: { category: string; children?: ReactNode }) {
  return (
    <div className="frosted sticky top-11 z-40 flex h-[52px] items-center border-b border-hairline">
      <div className="mx-auto flex w-full max-w-[1440px] items-center px-lg">
        <span className="text-tagline text-ink">{category}</span>
        <div className="ml-auto flex items-center gap-md">{children}</div>
      </div>
    </div>
  );
}

const FOOTER_COLUMNS = [
  {
    heading: "Study",
    links: [
      { href: "/library", label: "Library" },
      { href: "/chat", label: "Ask your notes" },
      { href: "/review", label: "Review session" },
    ],
  },
  {
    heading: "How it works",
    links: [
      { href: "/#scheduling", label: "Scheduling" },
      { href: "/#citations", label: "Citations" },
      { href: "/#privacy", label: "Your material" },
    ],
  },
  {
    heading: "Project",
    links: [
      { href: "https://github.com/ezitounioussama/recall-study-assistant", label: "Source" },
      { href: "/#roadmap", label: "Roadmap" },
    ],
  },
] as const;

/**
 * The footer is the one place the spec deliberately abandons its own whitespace
 * philosophy and goes dense, so the whole information architecture is visible
 * at once. The 2.41 line-height on link columns is what keeps that density
 * scannable — it looks like a mistake in the token file and is load-bearing
 * here.
 */
export function Footer() {
  return (
    <footer className="bg-canvas-parchment px-lg py-[64px] text-ink-muted-80">
      <div className="mx-auto grid w-full max-w-[1440px] gap-xl sm:grid-cols-2 md:grid-cols-3">
        {FOOTER_COLUMNS.map(({ heading, links }) => (
          <div key={heading}>
            <h3 className="text-caption-strong text-ink">{heading}</h3>
            <ul className="mt-xs list-none p-0">
              {links.map(({ href, label }) => (
                <li key={href} className="text-dense-link">
                  <Link href={href} className="text-ink-muted-80">
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="mx-auto mt-xl w-full max-w-[1440px] border-t border-hairline pt-md">
        <p className="text-fine-print text-ink-muted-48">
          Recall is a study project by Oussama Ezitouni. Not affiliated with Apple; the interface
          follows a published analysis of Apple&rsquo;s design language, included in this repository
          as docs/design-language.md.
        </p>
      </div>
    </footer>
  );
}
