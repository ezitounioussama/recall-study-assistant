/**
 * The trust report, rendered from the numbers the evaluation run wrote.
 *
 * Nothing here is typed in by hand: `python -m evaluation.run` measures the
 * real models against labelled questions and answers and writes
 * src/data/trust-report.json, and this page shows exactly that file.
 */
import type { Metadata } from "next";
import Link from "next/link";
import report from "@/data/trust-report.json";
import { FloatingNav, NavPill } from "@/components/ui/floating-nav";
import { Claim, Emphasis, Eyebrow, LeadCopy, Section } from "@/components/ui/product";

export const metadata: Metadata = {
  title: "Trust report — Recall",
  description: "How often Recall refuses, answers, cites and grades correctly, measured against labelled cases.",
};

type Ratio = { n: number; of: number; rate: number | null };

function Figure({ ratio, label, detail }: { ratio: Ratio; label: string; detail: string }) {
  return (
    <div className="rounded-lg border border-hairline bg-canvas p-lg">
      <p className="font-display text-display-lg text-ink">
        {ratio.n}
        <span className="text-lead-grey"> / {ratio.of}</span>
      </p>
      <p className="mt-xs text-body-strong text-ink">{label}</p>
      <p className="mt-xxs text-caption text-lead-grey">{detail}</p>
    </div>
  );
}

export default function TrustPage() {
  const s = report.summary;
  const date = report.generated_at.slice(0, 10);

  return (
    <>
      <FloatingNav title="Trust report">
        <NavPill href="/" variant="pearl">
          Overview
        </NavPill>
        <NavPill href="/sign-in">Sign in</NavPill>
      </FloatingNav>

      <Section>
        <Eyebrow>Measured, not claimed</Eyebrow>
        <Claim>How often is it right?</Claim>
        <LeadCopy className="mt-xxl">
          Every number below comes from running the <Emphasis>real models</Emphasis> against labelled questions and
          answers — nothing mocked. Run on {date} at commit <Emphasis>{report.commit}</Emphasis>.
        </LeadCopy>
      </Section>

      <Section surface="parchment">
        <Eyebrow>Answering from your notes</Eyebrow>
        <div className="mx-auto mt-xxl grid max-w-[1024px] gap-lg md:grid-cols-3">
          <Figure
            ratio={s.refusal.off_topic_refused}
            label="Off-topic questions refused"
            detail={`${s.refusal.off_topic_refused_without_model.n} of them before any model was called.`}
          />
          <Figure
            ratio={s.answers.covered_answered_with_expected_fact}
            label="Covered questions answered with the right fact"
            detail={`${s.refusal.covered_wrongly_refused.n} wrongly refused: the similarity floor is strict by design.`}
          />
          <Figure
            ratio={{ n: s.answers.invented_citations_shown_to_student, of: s.answers.answers_where_model_invented_a_citation.n, rate: 0 }}
            label="Invented citations shown to you"
            detail={`The model invented a citation number in ${s.answers.answers_where_model_invented_a_citation.n} of ${s.answers.answers_where_model_invented_a_citation.of} answers; the server and the app dropped every one.`}
          />
        </div>
      </Section>

      <Section>
        <Eyebrow>Grading your answers</Eyebrow>
        <div className="mx-auto mt-xxl grid max-w-[1024px] gap-lg md:grid-cols-3">
          <Figure
            ratio={s.grader.held_out.exact_verdict}
            label="Held-out answers graded correctly"
            detail="Written after the last change to the grader and never used to tune it. The number to trust."
          />
          <Figure
            ratio={s.grader.wrong_answer_graded_correct}
            label="Wrong answers graded as right"
            detail="The error that matters most in spaced repetition, across every answer tested."
          />
          <Figure
            ratio={s.grader.development.exact_verdict}
            label="Development answers graded correctly"
            detail="These were used to find and fix the grader's bugs, so they flatter it."
          />
        </div>
      </Section>

      <Section surface="parchment">
        <Eyebrow>The fine print</Eyebrow>
        <LeadCopy>
          Models: <Emphasis>{report.models.embedding}</Emphasis>, <Emphasis>{report.models.chat}</Emphasis> for answers,{" "}
          <Emphasis>{report.models.grader}</Emphasis> for grading, on a laptop CPU. Median answer{" "}
          {s.latency_seconds.chat_median} s, refusal {s.latency_seconds.refusal_median} s, grading {s.latency_seconds.grade_median} s.
        </LeadCopy>
        <p className="mx-auto mt-xl max-w-[60ch] text-center text-body text-lead-grey">
          {report.questions.length} questions and {report.grades.length} answers on two short documents is a smoke test of
          behaviour, not a benchmark, and the labels were written by the author of the code. Every case and every result is
          published in the{" "}
          <Link href="https://github.com/ezitounioussama/recall-study-assistant/blob/main/docs/trust-report.md">
            full report
          </Link>
          .
        </p>
      </Section>
    </>
  );
}
