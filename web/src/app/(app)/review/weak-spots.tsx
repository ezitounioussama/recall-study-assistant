"use client";

/**
 * Weak spots: the passages this student keeps forgetting, read from their own
 * review history, and a quiz drawn only from those passages.
 *
 * Nothing shows until there is history. A passage never reviewed is untested,
 * not weak, and an empty panel is more honest than a guess.
 */
import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Button } from "@/components/ui/button";
import { api, ApiError, type QuizResult, type WeakSpot } from "@/lib/api";
import { cn } from "@/lib/utils";

export function WeakSpots() {
  const [spots, setSpots] = useState<WeakSpot[] | null>(null);
  const [quiz, setQuiz] = useState<QuizResult | null>(null);
  const [making, setMaking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // The panel is extra: if it cannot load, the review screen still works.
    api.cards.weakSpots(3).then(setSpots).catch(() => setSpots([]));
  }, []);

  const start = async () => {
    setMaking(true);
    setError(null);
    try {
      // Three questions: on a CPU-only machine writing them and checking every
      // answer key with a second model takes about a minute.
      setQuiz(await api.study.weakSpotQuiz(3));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The quiz could not be made. Try again.");
    } finally {
      setMaking(false);
    }
  };

  if (!spots?.length) return null;

  return (
    <section aria-labelledby="weak-spots-title" className="mx-auto w-full max-w-[760px]">
      <header className="flex flex-wrap items-end justify-between gap-md">
        <div>
          <p className="text-body-strong text-ink-muted-48">From your review history</p>
          <h2 id="weak-spots-title" className="mt-xs text-display-md text-ink">
            Your weak spots
          </h2>
        </div>
        {!quiz ? (
          <Button variant="primary" onClick={() => void start()} disabled={making}>
            {making ? "Writing your quiz…" : "Quiz me on these"}
          </Button>
        ) : null}
      </header>

      {making ? (
        <p className="mt-md text-caption text-lead-grey" aria-live="polite">
          Writing questions from these passages, then checking every answer key with a second model. About a minute.
        </p>
      ) : null}

      {error ? (
        <p role="alert" className="mt-md text-body text-ink">
          {error}
        </p>
      ) : null}

      {quiz ? (
        <Quiz result={quiz} onClose={() => setQuiz(null)} />
      ) : (
        <ol className="m-0 mt-lg flex list-none flex-col gap-sm p-0">
          {spots.map((spot, i) => (
            <li key={spot.chunk_id ?? spot.cards[0]?.id ?? i} className="rounded-lg border border-hairline bg-canvas p-md">
              <div className="flex flex-wrap items-center justify-between gap-sm text-caption">
                <span className="text-caption-strong text-ink">
                  {spot.document_title ?? "Your own card"}
                  {spot.position !== null ? <span className="text-lead-grey"> · passage {spot.position + 1}</span> : null}
                </span>
                <span className="rounded-pill bg-canvas-parchment px-sm py-xxs text-ink">{spot.reason}</span>
              </div>
              {spot.excerpt ? <p className="mt-sm text-caption text-ink-muted-80">{spot.excerpt}</p> : null}
              <CardList cards={spot.cards} />
              <div className="mt-sm h-1 w-full rounded-pill bg-divider-soft" aria-hidden>
                <div className="h-1 rounded-pill bg-primary" style={{ width: `${Math.round(spot.weakness * 100)}%` }} />
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function CardList({ cards }: { cards: WeakSpot["cards"] }) {
  // A deck generated twice can hold the same question twice; list it once.
  const fronts = [...new Set(cards.map((c) => c.front))];
  const shown = fronts.slice(0, 3);
  return (
    <ul className="m-0 mt-sm flex list-none flex-col gap-xxs p-0 text-caption text-lead-grey">
      {shown.map((front) => (
        <li key={front}>{front}</li>
      ))}
      {fronts.length > shown.length ? <li>and {fronts.length - shown.length} more</li> : null}
    </ul>
  );
}

function Quiz({ result, onClose }: { result: QuizResult; onClose: () => void }) {
  const questions = result.quiz.questions;
  const [picked, setPicked] = useState<(number | null)[]>(() => questions.map(() => null));
  const answered = picked.filter((p) => p !== null).length;
  const score = picked.filter((p, i) => p === questions[i]?.answer_index).length;
  const done = answered === questions.length;

  return (
    <div className="mt-lg flex flex-col gap-md">
      {questions.map((q, i) => {
        const choice = picked[i];
        const source = q.source_index ? result.sources.find((s) => s.index === q.source_index) : undefined;
        return (
          <article key={i} className="rounded-lg border border-hairline bg-canvas p-md">
            <p className="text-caption text-lead-grey">
              Question {i + 1} of {questions.length}
            </p>
            <h3 className="mt-xs text-body-strong text-ink">{q.question}</h3>
            <div className="mt-sm grid gap-xs md:grid-cols-2">
              {q.choices.map((text, c) => {
                const isAnswer = c === q.answer_index;
                const isPicked = c === choice;
                return (
                  <button
                    key={c}
                    type="button"
                    disabled={choice !== null}
                    onClick={() => setPicked((p) => p.map((v, j) => (j === i ? c : v)))}
                    className={cn(
                      "min-h-11 cursor-pointer rounded-md border border-hairline bg-surface-pearl px-md py-sm text-left font-[inherit] text-body text-ink disabled:cursor-default",
                      choice !== null && isAnswer && "border-primary bg-primary text-on-primary",
                      choice !== null && isPicked && !isAnswer && "bg-ink text-on-dark",
                      choice !== null && !isAnswer && !isPicked && "opacity-60",
                    )}
                  >
                    {text}
                  </button>
                );
              })}
            </div>
            <AnimatePresence initial={false}>
              {choice !== null ? (
                <motion.p
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-sm text-caption text-ink-muted-80"
                >
                  <span className="text-caption-strong text-ink">{choice === q.answer_index ? "Right. " : "Not quite. "}</span>
                  {/* The source is named after it, so the bracket number adds nothing here. */}
                  {q.explanation.replace(/\s*\[\d+\]/g, "")}
                  {source ? <span className="text-lead-grey"> · {source.document_title}</span> : null}
                </motion.p>
              ) : null}
            </AnimatePresence>
          </article>
        );
      })}

      <footer className="flex flex-wrap items-center justify-between gap-md">
        <p className="text-body text-ink" aria-live="polite">
          {done ? `${score} of ${questions.length} right.` : `${answered} of ${questions.length} answered.`}
        </p>
        <Button variant="secondary" onClick={onClose}>
          {done ? "Back to weak spots" : "Stop the quiz"}
        </Button>
      </footer>
    </div>
  );
}
