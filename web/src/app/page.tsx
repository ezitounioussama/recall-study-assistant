import Link from "next/link";
import { Button } from "@/components/ui/button";
import { FloatingNav, NavPill } from "@/components/ui/floating-nav";
import {
  Claim,
  Emphasis,
  Eyebrow,
  LeadCopy,
  ProductName,
  ProductTagline,
  Section,
  Stat,
} from "@/components/ui/product";
import { Card } from "@/components/ui/tile";

/**
 * The landing page in the iPhone Air page's grammar.
 *
 * The shape it repeats, all the way down: eyebrow, one big claim at 40px/400,
 * a grey paragraph with the claims marked in ink, then a great deal of air.
 * Light surfaces throughout, stepping white to parchment rather than white to
 * near-black — the product page carries its rhythm through whitespace, and
 * saves the one dark band for a single moment.
 */

const DIFFERENCES = [
  {
    title: "Answers cite the paragraph",
    body: "Every reply points at the chunk of your own material it came from. An answer you cannot verify is not useful for studying.",
  },
  {
    title: "A schedule, not a pile",
    body: "Each card carries its own difficulty and stability. The next interval is computed from a memory model, not picked off a fixed ladder.",
  },
  {
    title: "It says when it does not know",
    body: "If your notes do not cover the question, Recall says so instead of answering from general knowledge.",
  },
] as const;

export default function Home() {
  return (
    <>
      <FloatingNav title="Recall">
        <NavPill href="/#how" variant="pearl">
          How it works
        </NavPill>
        <NavPill href="/sign-in">Sign in</NavPill>
      </FloatingNav>

      {/* ---- hero ---------------------------------------------------------- */}
      <Section tall>
        <ProductName family="Recall" model="Study" />
        <ProductTagline>The thinnest layer between your notes and remembering them.</ProductTagline>

        <div className="mt-xxl flex justify-center">
          <Link href="/library" data-pressable>
            <Button variant="primary">Add your material</Button>
          </Link>
        </div>

        {/* Where the reference page puts a full-bleed product render, this has
            no product to photograph. Rather than fill the space with stock
            imagery the design language would reject, the space stays empty and
            the type carries it — the spec's own instruction is that whitespace
            is the pedestal. */}
        <p className="mx-auto mt-section max-w-[34ch] text-center text-caption text-ink-muted-48">
          Runs locally by default. Your documents never have to leave the machine.
        </p>
      </Section>

      {/* ---- the lead paragraph, two-tone ---------------------------------- */}
      <Section id="how">
        <LeadCopy>
          Reading a page four times <Emphasis>feels like learning</Emphasis> and is mostly
          recognition. Recall is built around <Emphasis>being asked</Emphasis> — it turns what you
          wrote into questions, and schedules them for the moment{" "}
          <Emphasis>just before you would forget</Emphasis>.
        </LeadCopy>
      </Section>

      {/* ---- scheduling ---------------------------------------------------- */}
      <Section surface="parchment" id="scheduling">
        <Eyebrow>Scheduling</Eyebrow>
        <Claim>The interval is computed, not chosen.</Claim>
        <LeadCopy className="mt-xxl">
          FSRS models three things per card: <Emphasis>how stable</Emphasis> the memory is,{" "}
          <Emphasis>how difficult</Emphasis> the card is for you, and{" "}
          <Emphasis>how likely</Emphasis> you are to recall it right now. Rate a card and all three
          update.
        </LeadCopy>

        <div className="mt-section grid gap-xxl md:grid-cols-3">
          <Stat value="Stability" label="Days until recall probability falls to 90%" />
          <Stat value="Difficulty" label="How much this card resists you, and it never fully resets" />
          <Stat value="Retrievability" label="Your chance of recalling it this second" />
        </div>
      </Section>

      {/* ---- citations ----------------------------------------------------- */}
      <Section id="citations">
        <Eyebrow>Citations</Eyebrow>
        <Claim>Every answer knows where it came from.</Claim>
        <LeadCopy className="mt-xxl">
          Retrieval finds the passages, the model answers from them, and the reply carries the
          chunk it used. <Emphasis>Confident and wrong</Emphasis> is the failure mode that matters,
          so an answer your notes do not support is refused rather than improvised.
        </LeadCopy>
      </Section>

      {/* ---- the three differences ----------------------------------------- */}
      <Section surface="parchment">
        <Eyebrow>Points of difference</Eyebrow>
        <Claim>Three things it does differently.</Claim>
        <ul className="mt-section grid list-none gap-lg p-0 md:grid-cols-3">
          {DIFFERENCES.map(({ title, body }) => (
            <Card key={title} as="li">
              <h3 className="text-body-strong">{title}</h3>
              <p className="mt-xs text-body text-lead-grey">{body}</p>
            </Card>
          ))}
        </ul>
      </Section>

      {/* ---- the single dark band ------------------------------------------
          One dark section in the whole page. The reference page uses its dark
          moment sparingly and for a single idea, which is what makes it land. */}
      <Section surface="dark" id="privacy">
        <Eyebrow onDark>Your material</Eyebrow>
        <Claim>
          <span className="text-on-dark">It stays yours.</span>
        </Claim>
        <p className="mx-auto mt-xxl max-w-[30ch] text-center font-display text-lead-copy text-body-muted">
          Documents are scoped to your account, and the default model runs locally through Ollama.
          Nothing has to leave the machine to answer a question.
        </p>
        <div className="mt-xxl flex justify-center">
          <Link href="/library" data-pressable>
            <Button variant="primary">Add your first document</Button>
          </Link>
        </div>
      </Section>
    </>
  );
}
