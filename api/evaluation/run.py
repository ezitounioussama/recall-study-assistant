"""Run the trust report against the real models.

    cd api && .venv/bin/python -m evaluation.run

Builds a throwaway database, uploads the corpus in evaluation/corpus with real
embeddings, asks every labelled question through the real /chat endpoint,
grades every labelled answer with the real grader, and writes the results to
docs/trust-report.md and web/src/data/trust-report.json.

Needs Ollama running with the configured embedding, chat and grader models.
Nothing here is mocked; that is the point.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent

# Settings are read once at import, so the environment is fixed first: a
# scratch database, and the real embedder rather than the tests' hash one.
_db = Path(tempfile.mkdtemp(prefix="recall-eval-")) / "eval.sqlite3"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_db}"
os.environ["EMBEDDING_PROVIDER"] = "ollama"
os.environ.setdefault("SESSION_SECRET", "evaluation-only-secret-" + "x" * 32)

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import create_all  # noqa: E402
from app.llm import get_chat_model, get_grader_model  # noqa: E402
from app.main import app  # noqa: E402
from app.services.ai_service import AiService  # noqa: E402
from evaluation.metrics import GradeResult, QuestionResult, Report  # noqa: E402


async def ask(client: AsyncClient, question: str) -> tuple[list, str, dict, float]:
    started = time.perf_counter()
    sources: list = []
    tokens: list[str] = []
    done: dict = {}
    event = None
    async with client.stream("POST", "/chat", json={"question": question}) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                if event == "sources":
                    sources = data
                elif event == "token":
                    tokens.append(data["text"])
                elif event == "done":
                    done = data
                elif event == "error":
                    raise RuntimeError(data["detail"])
    return sources, "".join(tokens), done, time.perf_counter() - started


async def main() -> None:
    cases = json.loads((HERE / "cases.json").read_text())
    cfg = settings()
    await create_all()
    report = Report()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://eval", timeout=600) as client:
        response = await client.post(
            "/auth/register",
            json={"email": "evaluation@recall.study", "password": "evaluation-password-1", "display_name": "Evaluation"},
        )
        response.raise_for_status()
        for doc in sorted((HERE / "corpus").glob("*.md")):
            (await client.post("/documents", files={"file": (doc.name, doc.read_bytes())})).raise_for_status()

        for case in cases["questions"]:
            sources, raw, done, seconds = await ask(client, case["q"])
            result = QuestionResult(
                question=case["q"], covered=case["covered"], expect=case.get("expect", []),
                sources=len(sources), grounded=done.get("grounded", False), answer=done.get("answer", ""),
                raw_answer=raw, citations=done.get("citations", []), seconds=seconds,
            )
            report.questions.append(result)
            mark = "refused" if result.refused else ("ok" if result.mentions_expected else "answered")
            print(f"  {'covered' if case['covered'] else 'off-topic':<9} {mark:<8} {seconds:5.1f}s  {case['q']}", flush=True)

    grader = AiService(get_chat_model(), get_grader_model())
    for case in cases["answers"]:
        started = time.perf_counter()
        grade = await grader.grade_answer(case["q"], case["ref"], case["a"])
        seconds = time.perf_counter() - started
        verdict = grade.verdict if grade else "unreadable"
        report.grades.append(
            GradeResult(case["q"], case["a"], case["expect"], verdict, grade.suggested_rating if grade else 0, seconds, case.get("set", "development"))
        )
        print(f"  grade  {case.get('set', 'development'):<11} {case['expect']:<9} -> {verdict:<9} {seconds:4.1f}s  {case['a'][:55]}", flush=True)

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "commit": commit,
        "models": {"embedding": cfg.embedding_model, "chat": cfg.chat_model, "grader": cfg.grader_model or cfg.chat_model},
        "similarity_floor": cfg.retrieval_min_score,
        "corpus": sorted(p.name for p in (HERE / "corpus").glob("*.md")),
        "summary": report.summary(),
        "questions": [
            {"question": q.question, "covered": q.covered, "sources": q.sources, "grounded": q.grounded,
             "mentions_expected": q.mentions_expected, "invented_citations": q.invented_citations,
             "answer": q.answer, "seconds": round(q.seconds, 2)}
            for q in report.questions
        ],
        "grades": [
            {"question": g.question, "answer": g.answer, "expected": g.expect, "verdict": g.verdict,
             "rating": g.rating, "seconds": round(g.seconds, 2), "set": g.set}
            for g in report.grades
        ],
    }
    out = ROOT / "web" / "src" / "data" / "trust-report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")
    (ROOT / "docs" / "trust-report.md").write_text(render(payload))
    print(json.dumps(payload["summary"], indent=2))


def render(p: dict) -> str:
    s = p["summary"]

    def r(x: dict) -> str:
        return f"**{x['n']} / {x['of']}**"

    rows_q = "\n".join(
        f"| {q['question']} | {'covered' if q['covered'] else 'not covered'} | {q['sources']} | "
        f"{'answered' if q['grounded'] else 'refused'} | {'✓' if (not q['covered'] and not q['grounded']) or (q['covered'] and q['mentions_expected']) else '✗'} |"
        for q in p["questions"]
    )
    rows_g = "\n".join(
        f"| {g['set']} | {g['answer']} | {g['expected']} | {g['verdict']} | {'✓' if g['expected'] == g['verdict'] else '✗'} |"
        for g in p["grades"]
    )
    c = s["grader"]["confusion"]
    return f"""# Trust report

How often Recall is right, measured rather than claimed. Generated by
`python -m evaluation.run` against the real models — nothing mocked — on
{p['generated_at'][:10]} at commit `{p['commit']}`.

Models: `{p['models']['embedding']}` (embeddings), `{p['models']['chat']}`
(answers), `{p['models']['grader']}` (grading). Similarity floor
{p['similarity_floor']}. Corpus: {', '.join(f'`{c}`' for c in p['corpus'])} in
`api/evaluation/corpus/`. Cases: `api/evaluation/cases.json`.

## Headline

| | |
|---|---|
| Questions the notes do not cover, refused | {r(s['refusal']['off_topic_refused'])} |
| … refused before any model was called | {r(s['refusal']['off_topic_refused_without_model'])} |
| Questions the notes cover, wrongly refused | {r(s['refusal']['covered_wrongly_refused'])} |
| Covered questions answered with the expected fact | {r(s['answers']['covered_answered_with_expected_fact'])} |
| Grounded answers citing a passage | {r(s['answers']['grounded_answers_citing_a_passage'])} |
| Answers where the model invented a citation number | {r(s['answers']['answers_where_model_invented_a_citation'])} |
| Invented citations shown to the student | **{s['answers']['invented_citations_shown_to_student']}** — the server and the client both drop them |
| Free-text answers graded with the right verdict — **held-out** | {r(s['grader']['held_out']['exact_verdict'])} |
| … on the development answers used to fix the grader | {r(s['grader']['development']['exact_verdict'])} |
| Wrong answers graded as correct (all answers) | {r(s['grader']['wrong_answer_graded_correct'])} |

Median time: {s['latency_seconds']['chat_median']} s for an answer,
{s['latency_seconds']['refusal_median']} s for a refusal,
{s['latency_seconds']['grade_median']} s to grade an answer — on a laptop CPU.

## Questions

| Question | Notes | Passages | Result | Right? |
|---|---|---|---|---|
{rows_q}

"Right" means a covered question was answered and mentioned the expected
fact, or an uncovered one was refused.

## Grading

| Set | Answer | Expected | Graded | Right? |
|---|---|---|---|---|
{rows_g}

The **development** answers were used to find and fix the grader's bugs, so
they flatter it. The **held-out** answers were written after the last change
to the grader and were never used to tune it: that is the number to trust.

Confusion (rows expected, columns graded):

| | correct | partial | incorrect |
|---|---|---|---|
| **correct** | {c['correct']['correct']} | {c['correct']['partial']} | {c['correct']['incorrect']} |
| **partial** | {c['partial']['correct']} | {c['partial']['partial']} | {c['partial']['incorrect']} |
| **incorrect** | {c['incorrect']['correct']} | {c['incorrect']['partial']} | {c['incorrect']['incorrect']} |

## Limits of this report

Twenty questions and {len(p['grades'])} answers on two short documents is a smoke test
of behaviour, not a benchmark. The labels were written by the author of the
code. The questions, unlike the held-out answers, were also used while tuning
the chunk size. The expected-fact check is a substring match, so a correct paraphrase
can count as a miss. The numbers are what this commit did on this machine on
this day; run it again to check them.
"""


if __name__ == "__main__":
    asyncio.run(main())
