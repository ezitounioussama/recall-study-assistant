import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, Tile, TileHeader } from "@/components/ui/tile";

/**
 * The landing page, built on the spec's section pulse:
 *
 *   light hero -> dark tile -> parchment utility -> dark-2 tile -> light -> footer
 *
 * Every break between sections is a surface-colour change and nothing else.
 * There are no dividers, no borders between tiles, and no gaps — which is why
 * this file contains no separator markup at all.
 */

const CAPABILITIES = [
  {
    title: "Answers that cite the paragraph",
    body: "Every reply points at the chunk of your own material it came from, so you can go and read the source. An answer you cannot verify is not useful for studying.",
  },
  {
    title: "A schedule, not a pile",
    body: "Cards are scheduled with FSRS — each one carries its own difficulty and stability, and the next interval is computed from a memory model rather than a fixed ladder.",
  },
  {
    title: "It says when it does not know",
    body: "If your notes do not cover the question, Recall says so instead of answering from general knowledge. Confident and wrong is the failure mode that matters.",
  },
] as const;

export default function Home() {
  return (
    <>
      {/* ---- hero: light ------------------------------------------------- */}
      <Tile surface="light" className="pt-[var(--spacing-xxl)]">
        <div className="flex flex-col items-center text-center">
          <h1 className="max-w-[20ch] text-hero-display [letter-spacing:-0.01em]">
            Study from what you already wrote.
          </h1>
          <p className="mt-[var(--spacing-lg)] max-w-[46ch] text-lead text-ink-muted-80">
            Upload your notes. Ask them questions. Review the answers on a schedule that adapts to
            what you keep forgetting.
          </p>
          <div className="mt-[var(--spacing-xxl)] flex flex-wrap items-center justify-center gap-[var(--spacing-sm)]">
            <Link href="/library" data-pressable>
              <Button variant="primary">Add your material</Button>
            </Link>
            <Link href="/#how" data-pressable>
              <Button variant="secondary">How it works</Button>
            </Link>
          </div>
        </div>
      </Tile>

      {/* ---- dark tile: the loop ----------------------------------------- */}
      <Tile surface="dark" id="how">
        <TileHeader
          onDark
          eyebrow="The loop"
          headline="Read once. Recall many times."
          tagline="Reading a page four times feels like learning and is mostly recognition. Retrieval is what moves material into memory, so the whole product is built around being asked."
        >
          <Link href="/review" data-pressable>
            <Button variant="primary">Start a review</Button>
          </Link>
        </TileHeader>
      </Tile>

      {/* ---- parchment: capabilities ------------------------------------- */}
      <Tile surface="parchment" id="citations">
        <TileHeader
          align="start"
          headline="Three things it does differently"
          tagline="Each of these exists because the obvious version of this product gets it wrong."
        />
        <ul className="mt-[var(--spacing-xxl)] grid list-none gap-[var(--spacing-lg)] p-0 md:grid-cols-3">
          {CAPABILITIES.map(({ title, body }) => (
            <Card key={title} as="li">
              <h3 className="text-body-strong">{title}</h3>
              <p className="mt-[var(--spacing-xs)] text-body text-ink-muted-80">{body}</p>
            </Card>
          ))}
        </ul>
      </Tile>

      {/* ---- dark-2: the scheduler --------------------------------------- */}
      <Tile surface="dark-2" id="scheduling">
        <TileHeader
          onDark
          align="start"
          eyebrow="Scheduling"
          headline="The interval is computed, not chosen."
          tagline="FSRS models three things per card: how stable the memory is, how difficult the card is for you, and how likely you are to recall it right now. Rate a card and all three update."
        />
        <dl className="mt-[var(--spacing-section)] grid gap-[var(--spacing-lg)] md:grid-cols-3">
          {[
            ["Stability", "How many days until recall probability falls to 90%. Grows every time you succeed."],
            ["Difficulty", "How much this particular card resists you. Rises on a lapse, and never fully resets."],
            ["Retrievability", "The chance you would recall it this second. Decays on a curve, not a calendar."],
          ].map(([term, definition]) => (
            <div key={term}>
              <dt className="text-tagline text-on-dark">{term}</dt>
              <dd className="mt-[var(--spacing-xxs)] ml-0 text-body text-body-muted">
                {definition}
              </dd>
            </div>
          ))}
        </dl>
      </Tile>

      {/* ---- light: your material stays yours ---------------------------- */}
      <Tile surface="light" id="privacy">
        <TileHeader
          headline="Your material stays your material."
          tagline="Documents are scoped to your account. The default model runs locally through Ollama, so nothing has to leave the machine to answer a question."
        >
          <Link href="/library" data-pressable>
            <Button variant="store-hero">Add your first document</Button>
          </Link>
        </TileHeader>
      </Tile>
    </>
  );
}
