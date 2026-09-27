"""Scoring for the trust report. Pure functions, so they are tested like any other code."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import median

_CITE = re.compile(r"\[(\d+)\]")


@dataclass
class QuestionResult:
    question: str
    covered: bool
    expect: list[str]
    sources: int
    grounded: bool
    answer: str
    raw_answer: str
    citations: list[int]
    seconds: float

    @property
    def refused(self) -> bool:
        return not self.grounded

    @property
    def mentions_expected(self) -> bool:
        text = self.answer.lower()
        return any(term.lower() in text for term in self.expect)

    @property
    def invented_citations(self) -> list[int]:
        """Numbers the model wrote that point at no passage it was given."""
        return sorted({int(n) for n in _CITE.findall(self.raw_answer) if not 1 <= int(n) <= self.sources})


@dataclass
class GradeResult:
    question: str
    answer: str
    expect: str
    verdict: str
    rating: int
    seconds: float
    set: str = "development"

    @property
    def exact(self) -> bool:
        return self.verdict == self.expect

    @property
    def dangerous(self) -> bool:
        """The error that matters: a wrong answer graded as right."""
        return self.expect == "incorrect" and self.verdict == "correct"


@dataclass
class Report:
    questions: list[QuestionResult] = field(default_factory=list)
    grades: list[GradeResult] = field(default_factory=list)

    def summary(self) -> dict:
        covered = [q for q in self.questions if q.covered]
        off = [q for q in self.questions if not q.covered]
        answered = [q for q in covered if not q.refused]
        grounded = [q for q in self.questions if q.grounded]

        def ratio(n: int, d: int) -> dict:
            return {"n": n, "of": d, "rate": round(n / d, 3) if d else None}

        verdicts = ("correct", "partial", "incorrect")
        confusion = {e: {v: sum(1 for g in self.grades if g.expect == e and g.verdict == v) for v in verdicts} for e in verdicts}

        def grader_on(name: str) -> dict:
            graded = [g for g in self.grades if g.set == name]
            return {
                "exact_verdict": ratio(sum(g.exact for g in graded), len(graded)),
                "wrong_answer_graded_correct": ratio(sum(g.dangerous for g in graded), len(graded)),
            }
        return {
            "refusal": {
                "off_topic_refused": ratio(sum(q.refused for q in off), len(off)),
                "off_topic_refused_without_model": ratio(sum(q.sources == 0 for q in off), len(off)),
                "covered_wrongly_refused": ratio(sum(q.refused for q in covered), len(covered)),
            },
            "answers": {
                "covered_answered_with_expected_fact": ratio(sum(q.mentions_expected for q in answered), len(covered)),
                "grounded_answers_citing_a_passage": ratio(sum(bool(q.citations) for q in grounded), len(grounded)),
                "answers_where_model_invented_a_citation": ratio(sum(bool(q.invented_citations) for q in self.questions), len(self.questions)),
                "invented_citations_shown_to_student": 0,
            },
            "grader": {
                "exact_verdict": ratio(sum(g.exact for g in self.grades), len(self.grades)),
                "wrong_answer_graded_correct": ratio(sum(g.dangerous for g in self.grades), len(self.grades)),
                "confusion": confusion,
                # The development answers were used to find and fix the
                # grader's bugs, so they flatter it. The held-out answers were
                # written after the last change and never used to tune it.
                "development": grader_on("development"),
                "held_out": grader_on("held-out"),
            },
            "latency_seconds": {
                "chat_median": round(median([q.seconds for q in answered]), 1) if answered else None,
                "refusal_median": round(median([q.seconds for q in off]), 2) if off else None,
                "grade_median": round(median([g.seconds for g in self.grades]), 1) if self.grades else None,
            },
        }
