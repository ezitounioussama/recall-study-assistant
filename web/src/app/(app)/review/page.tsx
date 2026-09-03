"use client";

/**
 * The review session. One card at a time: the question, then the answer on
 * request, then four ratings with the interval each would produce. The
 * scheduler on the server does the rest; this screen just has to make the
 * rating feel light.
 *
 * Keys: Space shows the answer; 1–4 rate it.
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
import { api, ApiError, type CardStats, type DueCard, type Rating } from "@/lib/api";
import { formatDue, formatInterval } from "@/lib/format";
import { cn } from "@/lib/utils";

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
        setError(null);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Could not save that rating.");
      } finally {
        setBusy(false);
      }
    },
    [current, busy],
  );

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

              <footer className="mt-xxl">
                {!revealed ? (
                  <div className="flex flex-col items-center gap-xs">
                    <Button variant="primary" onClick={() => setRevealed(true)}>
                      Show answer
                    </Button>
                    <span className="text-caption text-ink-muted-48">or press Space</span>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-sm md:grid-cols-4">
                    {RATINGS.map(({ rating, label, key, style }) => (
                      <button
                        key={rating}
                        type="button"
                        disabled={busy}
                        onClick={() => void rate(rating)}
                        className={cn(
                          "flex min-h-[64px] cursor-pointer flex-col items-center justify-center rounded-lg border-0 font-[inherit] disabled:cursor-not-allowed disabled:opacity-50",
                          style,
                        )}
                      >
                        <span className="text-body-strong">{label}</span>
                        <span className="mt-xxs text-caption opacity-80">{formatInterval(current.preview[key])}</span>
                      </button>
                    ))}
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
