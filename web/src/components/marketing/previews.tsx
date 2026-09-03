"use client";

/**
 * The product, rendered small inside device frames on the landing page.
 *
 * Apple's product pages put the product in the frame. This product is a
 * screen, so the frames hold live miniature UI built from the same tokens the
 * real screens use — not screenshots, which go stale the day after they are
 * taken.
 */
import { AnimatedList } from "@/components/magicui/animated-list";
import { TypingAnimation } from "@/components/magicui/typing-animation";
import { cn } from "@/lib/utils";

const ANSWER_SOURCES = [
  { n: 1, title: "Cell biology — week 3", text: "Mitochondria produce ATP through oxidative phosphorylation…" },
  { n: 2, title: "Cell biology — week 3", text: "They have a double membrane and their own circular DNA…" },
];

/** A chat exchange with citations, for the Safari frame. */
export function ChatPreview() {
  return (
    <div className="grid h-full grid-cols-[1fr_38%] gap-lg bg-canvas p-lg text-left">
      <div className="flex flex-col justify-end gap-md">
        <p className="self-end rounded-lg rounded-br-xs bg-primary px-md py-xs text-caption text-on-primary">What do mitochondria produce?</p>
        <div className="max-w-[92%] rounded-lg rounded-bl-xs bg-canvas-parchment px-md py-sm text-caption text-ink">
          <TypingAnimation duration={22} pauseDelay={4000} loop words={["Mitochondria produce ATP, the cell's energy currency [1]. They have a double membrane and carry their own DNA [2]."]} />
        </div>
        <p className="self-end rounded-lg rounded-br-xs bg-primary px-md py-xs text-caption text-on-primary">Who wrote Hamlet?</p>
        <p className="max-w-[92%] rounded-lg rounded-bl-xs bg-canvas-parchment px-md py-sm text-caption text-lead-grey">I can&apos;t find that in your notes.</p>
      </div>
      <aside>
        <p className="text-caption-strong text-ink-muted-48">Sources</p>
        <AnimatedList delay={1500} className="mt-xs items-stretch gap-xs">
          {ANSWER_SOURCES.map((s) => (
            <div key={s.n} className="rounded-md border border-hairline bg-canvas p-sm">
              <div className="flex items-center gap-xxs">
                <span className="inline-flex size-4 items-center justify-center rounded-pill bg-primary text-[10px] font-semibold text-on-primary">{s.n}</span>
                <span className="truncate text-[11px] font-semibold text-ink">{s.title}</span>
              </div>
              <p className="mt-xxs line-clamp-2 text-[11px] leading-snug text-ink-muted-80">{s.text}</p>
            </div>
          ))}
        </AnimatedList>
      </aside>
    </div>
  );
}

/** A review card with the four ratings, for the iPhone frame. */
export function ReviewPreview() {
  return (
    <div className="flex h-full flex-col bg-canvas-parchment px-md pt-[14%] pb-md text-left">
      <p className="text-center text-[11px] font-semibold text-ink">Review · 6 to go</p>
      <div className="mt-md flex flex-1 flex-col rounded-lg bg-canvas p-md">
        <p className="text-[10px] text-lead-grey">review · recall 87%</p>
        <p className="mt-sm font-display text-[17px] leading-tight font-semibold text-ink [letter-spacing:-0.01em]">
          Where do the light-dependent reactions happen?
        </p>
        <p className="mt-sm border-t border-divider-soft pt-sm text-[12px] leading-snug text-ink-muted-80">
          In the thylakoid membranes of the chloroplast.
        </p>
        <div className="mt-auto grid grid-cols-4 gap-xxs">
          {[
            ["Again", "1m", "bg-ink text-on-dark"],
            ["Hard", "6m", "bg-canvas-parchment text-ink"],
            ["Good", "10m", "bg-primary text-on-primary"],
            ["Easy", "16d", "bg-surface-pearl text-primary border border-primary"],
          ].map(([label, when, style]) => (
            <div key={label} className={cn("flex flex-col items-center rounded-md py-xs", style)}>
              <span className="text-[10px] font-semibold">{label}</span>
              <span className="text-[9px] opacity-80">{when}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="mx-auto mt-md h-1 w-1/3 rounded-pill bg-ink/70" />
    </div>
  );
}
