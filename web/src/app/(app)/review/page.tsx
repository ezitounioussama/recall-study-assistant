"use client";

/**
 * The review session. One card at a time: the question, then the answer on
 * request, then four ratings with the interval each would produce. The
 * scheduler on the server does the rest; this screen just has to make the
 * rating feel light.
 *
 * "Explain it back": instead of flipping the card, the student can write the
 * answer in their own words and have it checked fact by fact against the
 * card. The check suggests a rating; the student still presses it.
 *
 * Weak spots sit under the card: the passages the history says are slipping,
 * and a quiz on them. They reload when a session ends, so what was just
 * forgotten shows up straight away.
 *
 * Keys: Space shows the answer; Ctrl+Enter checks a written answer; 1–4 rate.
 */
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { AnimatedCircularProgressBar } from "@/components/magicui/animated-circular-progress-bar";
import { BlurFade } from "@/components/magicui/blur-fade";
import { BorderBeam } from "@/components/magicui/border-beam";
import { Confetti, type ConfettiRef } from "@/components/magicui/confetti";
import { NumberTicker } from "@/components/magicui/number-ticker";
import { Button } from "@/components/ui/button";
import { ExpandCapsule } from "@/components/ui/product";
import { api, ApiError, type CardStats, type DueCard, type Grade, type Rating } from "@/lib/api";
import { formatDue, formatInterval } from "@/lib/format";
import { cn } from "@/lib/utils";
import { WeakSpots } from "./weak-spots";

const RATINGS: { rating: Rating; label: string; key: keyof DueCard["preview"]; style: string }[] = [
  { rating: 1, label: "Again", key: "again", style: "bg-ink text-on-dark" },
  { rating: 2, label: "Hard", key: "hard", style: "bg-canvas-parchment text-ink" },
  { rating: 3, label: "Good", key: "good", style: "bg-primary text-on-primary" },
  { rating: 4, label: "Easy", key: "easy", style: "bg-surface-pearl text-primary border border-primary" },
];

export default function ReviewPage() {
  const [stats, setStats] = useState<CardStats | null>(null);
  const [queue, setQueue] = useState<DueCard[] | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [answer, setAnswer] = useState("");
  const [grade, setGrade] = useState<Grade | null>(null);
  const [grading, setGrading] = useState(false);
  const [showSource, setShowSource] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState({ reviewed: 0, again: 0, startedWith: 0 });
  const [lastScheduled, setLastScheduled] = useState<number | null>(null);
  const confetti = useRef<ConfettiRef>(null);
  const celebrated = useRef(false);

  const load = useCallback(
    () =>
      Promise.all([api.cards.stats(), api.cards.due(50)])
        .then(([s, due]) => {
          setStats(s);
          setQueue(due);
          setSession((x) => ({ ...x, startedWith: due.length }));
          setError(null);
        })
        .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "Something went wrong.")),
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const current = queue?.[0];
  const finished = queue !== null && queue.length === 0 && session.reviewed > 0;

  useEffect(() => {
    if (finished && !celebrated.current) {
      celebrated.current = true;
      confetti.current?.fire();
      api.cards.stats().then(setStats).catch(() => undefined);
    }
  }, [finished]);

  const rate = useCallback(
    async (rating: Rating) => {
      if (!current || busy) return;
      setBusy(true);
      try {
        const result = await api.cards.review(current.id, rating);
        setLastScheduled(result.log.scheduled_seconds);
        setQueue((q) => (q ?? []).slice(1));
        setSession((s) => ({ ...s, reviewed: s.reviewed + 1, again: s.again + (rating === 1 ? 1 : 0) }));
        setRevealed(false);
        setShowSource(false);
        setAnswer("");
        setGrade(null);
        setError(null);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Could not save that rating.");
      } finally {
        setBusy(false);
      }
    },
    [current, busy],
  );

  const check = useCallback(async () => {
    if (!current || grading || !answer.trim()) return;
    setGrading(true);
    setError(null);
    try {
      const result = await api.cards.grade(current.id, answer.trim());
      setGrade(result.grade);
      setRevealed(true);
    } catch (e) {
      // The check is optional: if it fails, the card still works the old way.
      setError(e instanceof ApiError ? e.message : "The answer could not be checked. Show the answer and rate it yourself.");
    } finally {
      setGrading(false);
    }
  }, [current, grading, answer]);

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.target instanceof HTMLElement && ["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) return;
      if (e.key === " " && current && !revealed) {
        e.preventDefault();
        setRevealed(true);
      } else if (revealed && ["1", "2", "3", "4"].includes(e.key)) {
        void rate(Number(e.key) as Rating);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, revealed, rate]);

  const remaining = queue?.length ?? 0;
  const progress = session.startedWith ? Math.round((session.reviewed / session.startedWith) * 100) : 0;

  return (
    <div className="flex flex-col gap-xxl">
      <Confetti ref={confetti} className="pointer-events-none fixed inset-0 z-[70] size-full" />

      <BlurFade inView={false}>
        <header className="grid items-center gap-lg md:grid-cols-[auto_1fr]">
          <AnimatedCircularProgressBar
            value={Math.round((stats?.mean_retrievability ?? 0) * 100)}
            gaugePrimaryColor="var(--color-primary)"
            gaugeSecondaryColor="var(--color-divider-soft)"
            className="size-32 text-display-md"
          >
            <span className="flex flex-col items-center leading-none">
              <span className="font-display text-display-md text-ink">
                <NumberTicker value={Math.round((stats?.mean_retrievability ?? 0) * 100)} />
              </span>
              <span className="mt-xxs text-caption text-lead-grey">recall now</span>
            </span>
          </AnimatedCircularProgressBar>
          <div>
            <p className="text-body-strong text-ink-muted-48">Review</p>
            <h1 className="mt-xs text-display-lg text-ink">
              {current ? `${remaining} to go.` : finished ? "All caught up." : queue === null ? "Loading…" : "Nothing due."}
            </h1>
            <dl className="mt-md flex flex-wrap gap-xl">
              <Stat label="due now" value={stats?.due_now ?? 0} />
              <Stat label="reviewed today" value={stats?.reviewed_today ?? 0} />
              <Stat label="retention · 30d" value={stats?.retention_30d == null ? null : Math.round(stats.retention_30d * 100)} suffix="%" />
              <Stat label="cards" value={stats?.total ?? 0} />
            </dl>
          </div>
        </header>
      </BlurFade>

      {/* progress hairline */}
      <div className="h-px w-full bg-divider-soft">
        <motion.div className="h-px bg-primary" animate={{ width: `${progress}%` }} transition={{ duration: 0.5, ease: "easeOut" }} />
      </div>

      {error ? (
        <p role="alert" className="text-body text-ink">
          {error}
        </p>
      ) : null}

      <AnimatePresence mode="wait">
        {current ? (
          <motion.section
            key={current.id}
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -16, scale: 0.98 }}
            transition={{ duration: 0.28, ease: "easeOut" }}
            className="mx-auto w-full max-w-[760px]"
          >
            <article className="relative rounded-lg border border-hairline bg-canvas px-xl py-xxl">
              <BorderBeam size={120} duration={7} />
              <header className="flex items-center justify-between gap-md text-caption text-lead-grey">
                <span className="inline-flex items-center gap-xs">
                  <span className={cn("inline-block size-2 rounded-pill", current.state === "review" ? "bg-primary" : "bg-ink-muted-48")} />
                  {current.state} {current.source_title ? `· ${current.source_title}` : ""}
                </span>
                <span>
                  {current.stability ? `recall ${Math.round(current.retrievability * 100)}% · stability ${current.stability.toFixed(1)}d` : "new card"}
                </span>
              </header>

              <h2 className="mt-xl text-display-md text-ink [letter-spacing:-0.01em]">{current.front}</h2>

              <AnimatePresence initial={false}>
                {revealed ? (
                  <motion.div
                    initial={{ opacity: 0, y: 8, filter: "blur(4px)" }}
                    animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                    transition={{ duration: 0.3 }}
                    className="mt-lg border-t border-divider-soft pt-lg"
                  >
                    <p className="text-lead text-ink-muted-80">{current.back}</p>
                    {current.source_text ? (
                      <div className="mt-lg">
                        <ExpandCapsule label={showSource ? "Hide the passage" : "From your notes"} expanded={showSource} onClick={() => setShowSource((v) => !v)} />
                        <AnimatePresence initial={false}>
                          {showSource ? (
                            <motion.blockquote
                              initial={{ height: 0, opacity: 0 }}
                              animate={{ height: "auto", opacity: 1 }}
                              exit={{ height: 0, opacity: 0 }}
                              className="m-0 mt-md overflow-hidden rounded-md bg-canvas-parchment p-md text-caption text-ink-muted-80"
                            >
                              {current.source_text}
                            </motion.blockquote>
                          ) : null}
                        </AnimatePresence>
                      </div>
                    ) : null}
                  </motion.div>
                ) : null}
              </AnimatePresence>

              {grade ? <GradePanel grade={grade} answer={answer} /> : null}

              <footer className="mt-xxl">
                {!revealed ? (
                  <div className="flex flex-col gap-md">
                    <label className="flex flex-col gap-xs">
                      <span className="text-caption-strong text-ink">Explain it back</span>
                      <textarea
                        value={answer}
                        onChange={(e) => setAnswer(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                            e.preventDefault();
                            void check();
                          }
                        }}
                        rows={3}
                        maxLength={2000}
                        disabled={grading}
                        placeholder="Answer in your own words, then check it against your notes."
                        className="w-full resize-y rounded-lg border border-hairline bg-surface-pearl px-md py-sm font-[inherit] text-body text-ink outline-none placeholder:text-ink-muted-48 focus:border-primary"
                      />
                    </label>
                    <div className="flex flex-wrap items-center justify-center gap-sm">
                      <Button variant="primary" onClick={() => void check()} disabled={grading || !answer.trim()}>
                        {grading ? "Checking…" : "Check my answer"}
                      </Button>
                      <Button variant="secondary" onClick={() => setRevealed(true)} disabled={grading}>
                        Just show the answer
                      </Button>
                    </div>
                    <span className="text-center text-caption text-ink-muted-48">Ctrl+Enter to check · Space to show when not typing</span>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-sm md:grid-cols-4">
                    {RATINGS.map(({ rating, label, key, style }) => {
                      const suggested = grade?.suggested_rating === rating;
                      return (
                        <button
                          key={rating}
                          type="button"
                          disabled={busy}
                          onClick={() => void rate(rating)}
                          aria-label={suggested ? `${label} (suggested)` : label}
                          className={cn(
                            "relative flex min-h-[64px] cursor-pointer flex-col items-center justify-center rounded-lg border-0 font-[inherit] disabled:cursor-not-allowed disabled:opacity-50",
                            style,
                            suggested && "ring-2 ring-primary ring-offset-2 ring-offset-canvas",
                          )}
                        >
                          {suggested ? (
                            <span className="absolute -top-sm rounded-pill bg-primary px-xs text-[11px] font-semibold text-on-primary">suggested</span>
                          ) : null}
                          <span className="text-body-strong">{label}</span>
                          <span className="mt-xxs text-caption opacity-80">{formatInterval(current.preview[key])}</span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </footer>
            </article>
            {lastScheduled !== null ? (
              <p className="mt-md text-center text-caption text-lead-grey">Last card comes back in {formatInterval(lastScheduled)}.</p>
            ) : null}
          </motion.section>
        ) : finished ? (
          <motion.section key="done" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="mx-auto w-full max-w-[560px] text-center">
            <p className="font-display text-display-lg text-ink">Session done.</p>
            <p className="mt-sm text-lead text-lead-grey">
              {session.reviewed} card{session.reviewed === 1 ? "" : "s"}, {session.again} forgotten. Next one is due {formatDue(stats?.next_due ?? null)}.
            </p>
            <div className="mt-xl flex justify-center gap-sm">
              <Link href="/library" data-pressable>
                <Button variant="primary">Back to the library</Button>
              </Link>
              <Link href="/chat" data-pressable>
                <Button variant="secondary">Ask a question</Button>
              </Link>
            </div>
          </motion.section>
        ) : queue !== null ? (
          <motion.section key="empty" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="mx-auto w-full max-w-[560px] text-center">
            <p className="font-display text-display-lg text-ink">{stats?.total ? "Nothing due right now." : "No cards yet."}</p>
            <p className="mt-sm text-lead text-lead-grey">
              {stats?.total
                ? `The next card comes back ${formatDue(stats.next_due)}. The schedule is doing its job.`
                : "Generate cards from a document in the library and they will show up here, due immediately."}
            </p>
            <div className="mt-xl flex justify-center">
              <Link href="/library" data-pressable>
                <Button variant="primary">{stats?.total ? "Add more material" : "Go to the library"}</Button>
              </Link>
            </div>
          </motion.section>
        ) : null}
      </AnimatePresence>

      <WeakSpots key={finished ? "after" : "before"} />
    </div>
  );
}

function Stat({ label, value, suffix = "" }: { label: string; value: number | null; suffix?: string }) {
  return (
    <div>
      <dt className="text-caption text-lead-grey">{label}</dt>
      <dd className="m-0 font-display text-display-md text-ink">
        {value === null ? <span className="text-ink-muted-48">—</span> : <NumberTicker value={value} />}
        {value === null ? "" : suffix}
      </dd>
    </div>
  );
}

const VERDICT: Record<Grade["verdict"], { label: string; style: string }> = {
  correct: { label: "You had it", style: "bg-primary text-on-primary" },
  partial: { label: "Partly there", style: "bg-canvas-parchment text-ink" },
  incorrect: { label: "Not yet", style: "bg-ink text-on-dark" },
};

function GradePanel({ grade, answer }: { grade: Grade; answer: string }) {
  const verdict = VERDICT[grade.verdict];
  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      aria-label="How your answer compares"
      className="mt-lg rounded-lg border border-hairline bg-surface-pearl p-md"
    >
      <header className="flex flex-wrap items-center gap-sm">
        <span className={cn("rounded-pill px-sm py-xxs text-caption-strong", verdict.style)}>{verdict.label}</span>
        <span className="text-caption text-lead-grey">{Math.round(grade.score * 100)}% of the key points</span>
      </header>
      <p className="mt-sm text-caption text-ink-muted-48">
        You wrote: <span className="text-ink-muted-80">“{answer}”</span>
      </p>
      <ul className="m-0 mt-sm flex list-none flex-col gap-xxs p-0 text-caption">
        {grade.correct.map((point) => (
          <li key={`c-${point}`} className="text-ink">
            <span aria-hidden className="mr-xs text-primary">✓</span>
            {point}
          </li>
        ))}
        {grade.incorrect.map((point) => (
          <li key={`i-${point}`} className="text-ink">
            <span aria-hidden className="mr-xs">✕</span>
            Your answer conflicts with: {point}
          </li>
        ))}
        {grade.missing
          .filter((point) => !grade.incorrect.includes(point))
          .map((point) => (
            <li key={`m-${point}`} className="text-lead-grey">
              <span aria-hidden className="mr-xs">○</span>
              Missing: {point}
            </li>
          ))}
      </ul>
      {grade.feedback ? <p className="mt-sm text-caption text-ink-muted-80">{grade.feedback}</p> : null}
    </motion.section>
  );
}
