import Link from "next/link";
import { AnimatedList } from "@/components/magicui/animated-list";
import { AnimatedCircularProgressBar } from "@/components/magicui/animated-circular-progress-bar";
import { BentoCard, BentoGrid } from "@/components/magicui/bento-grid";
import { BlurFade } from "@/components/magicui/blur-fade";
import { BorderBeam } from "@/components/magicui/border-beam";
import { DotPattern } from "@/components/magicui/dot-pattern";
import { Iphone } from "@/components/magicui/iphone";
import { NumberTicker } from "@/components/magicui/number-ticker";
import { Safari } from "@/components/magicui/safari";
import { ScrollProgress } from "@/components/magicui/scroll-progress";
import { TextAnimate } from "@/components/magicui/text-animate";
import { TypingAnimation } from "@/components/magicui/typing-animation";
import { WordRotate } from "@/components/magicui/word-rotate";
import { ChatPreview, ReviewPreview } from "@/components/marketing/previews";
import { Button } from "@/components/ui/button";
import { FloatingNav, NavPill } from "@/components/ui/floating-nav";
import { Claim, Emphasis, Eyebrow, LeadCopy, ProductName, Section } from "@/components/ui/product";

/**
 * The landing page in the iPhone Air page's grammar, with the product shown
 * working.
 *
 * The shape it repeats, all the way down: eyebrow, one big claim at 40px/400,
 * a grey paragraph with the claims marked in ink, then a great deal of air.
 * Light surfaces throughout, stepping white to parchment, and one dark band.
 * Where the reference page puts a product render, this puts the product —
 * live miniatures of the chat and review screens inside device frames — and
 * every section arrives with the same blur-fade so the page reads as one
 * motion, not a collection of effects.
 */

const HERO_ROTATION = ["remembering them.", "a cited answer.", "the next review.", "knowing what you know."];

export default function Home() {
  return (
    <>
      <ScrollProgress />
      <FloatingNav title="Recall">
        <NavPill href="/#how" variant="pearl">
          How it works
        </NavPill>
        <NavPill href="/sign-in">Sign in</NavPill>
      </FloatingNav>

      {/* ---- hero ---------------------------------------------------------- */}
      <Section tall className="relative overflow-hidden">
        <DotPattern />
        <div className="relative">
          <BlurFade inView={false} duration={0.7}>
            <ProductName family="Recall" model="Study" />
          </BlurFade>
          <BlurFade inView={false} delay={0.15} duration={0.7}>
            <p className="mx-auto mt-lg max-w-[26ch] text-center font-display text-product-tagline text-lead-grey">
              The thinnest layer between your notes and <WordRotate words={HERO_ROTATION} className="text-ink" />
            </p>
          </BlurFade>
          <BlurFade inView={false} delay={0.3}>
            <div className="mt-xxl flex flex-wrap justify-center gap-sm">
              <Link href="/library" data-pressable>
                <Button variant="primary">Add your material</Button>
              </Link>
              <Link href="/sign-in" data-pressable>
                <Button variant="secondary">Try the demo account</Button>
              </Link>
            </div>
          </BlurFade>

          {/* the product, in frames */}
          <BlurFade inView={false} delay={0.45} duration={0.9} offset={24}>
            <div className="relative mx-auto mt-section max-w-[1040px] px-lg md:px-0">
              <Safari url="recall.study/chat" className="shadow-product">
                <ChatPreview />
              </Safari>
              <div className="absolute right-[-2%] bottom-[-12%] hidden w-[24%] md:block">
                <Iphone className="drop-shadow-[3px_5px_30px_rgba(0,0,0,0.22)]">
                  <ReviewPreview />
                </Iphone>
              </div>
            </div>
          </BlurFade>
        </div>
      </Section>

      {/* ---- the lead paragraph, two-tone ---------------------------------- */}
      <Section id="how" className="pt-[200px] md:pt-section">
        <BlurFade>
          <LeadCopy>
            Reading a page four times <Emphasis>feels like learning</Emphasis> and is mostly recognition. Recall is built
            around <Emphasis>being asked</Emphasis> — it turns what you wrote into questions, and schedules them for the
            moment <Emphasis>just before you would forget</Emphasis>.
          </LeadCopy>
        </BlurFade>
      </Section>

      {/* ---- scheduling ---------------------------------------------------- */}
      <Section surface="parchment" id="scheduling">
        <BlurFade>
          <Eyebrow>Scheduling</Eyebrow>
          <Claim>The interval is computed, not chosen.</Claim>
          <LeadCopy className="mt-xxl">
            FSRS models three things per card: <Emphasis>how stable</Emphasis> the memory is,{" "}
            <Emphasis>how difficult</Emphasis> the card is for you, and <Emphasis>how likely</Emphasis> you are to recall
            it right now. Rate a card and all three update.
          </LeadCopy>
        </BlurFade>

        <div className="mt-section grid gap-xxl md:grid-cols-3">
          <BlurFade delay={0.05}>
            <Figure value={90} suffix="%" label="the recall probability each interval aims for — stability is defined by it" />
          </BlurFade>
          <BlurFade delay={0.15}>
            <Figure value={19} label="fitted parameters in the memory model, none of them hand-picked" />
          </BlurFade>
          <BlurFade delay={0.25}>
            <Figure value={4} label="ratings. Again, Hard, Good, Easy — and each shows the interval it would produce" />
          </BlurFade>
        </div>
      </Section>

      {/* ---- citations ----------------------------------------------------- */}
      <Section id="citations">
        <BlurFade>
          <Eyebrow>Citations</Eyebrow>
          <Claim>Every answer knows where it came from.</Claim>
          <LeadCopy className="mt-xxl">
            Retrieval finds the passages, the model answers from them, and the reply carries the chunk it used.{" "}
            <Emphasis>Confident and wrong</Emphasis> is the failure mode that matters, so an answer your notes do not
            support is refused rather than improvised.
          </LeadCopy>
        </BlurFade>
      </Section>

      {/* ---- the bento ----------------------------------------------------- */}
      <Section surface="parchment">
        <BlurFade>
          <Eyebrow>Points of difference</Eyebrow>
          <Claim>Four things it does differently.</Claim>
        </BlurFade>
        <BlurFade delay={0.1}>
          <BentoGrid className="mt-section">
            <BentoCard
              name="Answers cite the paragraph"
              description="Every reply points at the passage of your own material it came from, numbered as the answer cites it."
              href="/chat"
              cta="Ask a question"
              className="md:col-span-2"
              background={<SourcesDemo />}
            />
            <BentoCard
              name="Recall, as a number"
              description="Retrievability is the probability you remember a card right now. The deck's mean is one honest figure."
              href="/review"
              cta="Open review"
              background={<GaugeDemo />}
            />
            <BentoCard
              name="It says when it does not know"
              description="Nothing above the similarity floor means a fixed refusal — decided before any model is asked."
              href="/chat"
              cta="See it refuse"
              background={<RefusalDemo />}
            />
            <BentoCard
              name="Local by default"
              description="Embeddings and answers come from Ollama on your machine. Your documents never have to leave it."
              href="/library"
              cta="Add material"
              className="md:col-span-2"
              background={<LocalDemo />}
            />
          </BentoGrid>
        </BlurFade>
      </Section>

      {/* ---- the single dark band ------------------------------------------ */}
      <Section surface="dark" id="privacy">
        <BlurFade>
          <Eyebrow onDark>Your material</Eyebrow>
          <Claim>
            <span className="text-on-dark">It stays yours.</span>
          </Claim>
          <p className="mx-auto mt-xxl max-w-[30ch] text-center font-display text-lead-copy text-body-muted">
            Documents are scoped to your account, and the default model runs locally through Ollama. Nothing has to
            leave the machine to answer a question.
          </p>
        </BlurFade>
        <BlurFade delay={0.15}>
          <div className="relative mx-auto mt-xxl flex max-w-[520px] flex-col items-center gap-md rounded-lg bg-surface-tile-2 p-xl text-center">
            <BorderBeam size={140} duration={8} />
            <TextAnimate as="p" by="word" animation="blurInUp" className="font-display text-tagline text-on-dark">
              Sign in with the demo account and add your first document.
            </TextAnimate>
            <Link href="/sign-in" data-pressable>
              <Button variant="primary">Get started</Button>
            </Link>
          </div>
        </BlurFade>
      </Section>
    </>
  );
}

/* ---- pieces ------------------------------------------------------------------ */

function Figure({ value, suffix = "", label }: { value: number; suffix?: string; label: string }) {
  return (
    <div className="text-center">
      <p className="font-display text-hero-display text-ink">
        <NumberTicker value={value} />
        {suffix}
      </p>
      <p className="mx-auto mt-xs max-w-[28ch] text-body text-lead-grey">{label}</p>
    </div>
  );
}

const DEMO_SOURCES = [
  { n: 1, title: "Cell biology — week 3", text: "Mitochondria are the organelles that produce ATP through oxidative phosphorylation." },
  { n: 2, title: "Cell biology — week 3", text: "Chloroplasts capture light energy with chlorophyll and use it to fix carbon dioxide." },
  { n: 3, title: "Photosynthesis lecture", text: "The light-dependent reactions happen in the thylakoid membranes." },
];

function SourcesDemo() {
  return (
    <div className="absolute inset-x-lg top-lg bottom-[46%] overflow-hidden mask-[linear-gradient(black_55%,transparent)]">
      <AnimatedList delay={1300} className="items-stretch gap-xs">
        {DEMO_SOURCES.map((s) => (
          <div key={s.n} className="rounded-md border border-hairline bg-canvas p-sm">
            <div className="flex items-center gap-xs">
              <span className="inline-flex size-5 items-center justify-center rounded-pill bg-primary text-caption-strong text-on-primary">{s.n}</span>
              <span className="text-caption-strong text-ink">{s.title}</span>
            </div>
            <p className="mt-xxs line-clamp-1 text-caption text-ink-muted-80">{s.text}</p>
          </div>
        ))}
      </AnimatedList>
    </div>
  );
}

function GaugeDemo() {
  return (
    <div className="absolute inset-x-0 top-lg flex justify-center">
      <AnimatedCircularProgressBar value={87} gaugePrimaryColor="var(--color-primary)" gaugeSecondaryColor="var(--color-hairline)" className="size-36 text-display-md text-ink">
        <span className="flex flex-col items-center leading-none">
          <span className="font-display text-display-md text-ink">87</span>
          <span className="mt-xxs text-caption text-lead-grey">% recall</span>
        </span>
      </AnimatedCircularProgressBar>
    </div>
  );
}

function RefusalDemo() {
  return (
    <div className="absolute inset-x-lg top-lg bottom-[46%] flex flex-col gap-xs overflow-hidden">
      <p className="self-end rounded-lg rounded-br-xs bg-primary px-md py-xs text-caption text-on-primary">Who wrote Hamlet?</p>
      <p className="self-start rounded-lg rounded-bl-xs bg-canvas-parchment px-md py-xs text-caption text-lead-grey">
        <TypingAnimation duration={40} pauseDelay={3500} loop words={["I can't find that in your notes."]} />
      </p>
    </div>
  );
}

function LocalDemo() {
  const models = ["nomic-embed-text · embeddings", "llama3.2:3b · answers", "qwen3:8b · when you want better", "127.0.0.1:11434"];
  return (
    <div className="absolute inset-x-lg top-lg bottom-[46%] flex flex-wrap content-start gap-xs overflow-hidden">
      {models.map((m, i) => (
        <span key={m} className={i === models.length - 1 ? "rounded-pill bg-ink px-md py-xs text-caption text-on-dark" : "rounded-pill border border-hairline bg-canvas px-md py-xs text-caption text-ink"}>
          {m}
        </span>
      ))}
    </div>
  );
}
