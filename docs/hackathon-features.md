# Built on hackathon day — 27 September 2026

Three features added during the GOMYCODE × NVIDIA "Come Build with AI"
hackathon, on top of the existing Recall app. Each landed as its own pull
request with tests.

## 1. Explain it back

Flashcard apps ask you to grade yourself, and people are generous with
themselves. On the review screen you can now **write the answer in your own
words** and have it checked, fact by fact, against the card.

![a graded answer](screens/hackathon/explain-it-back.png)

The result lists which facts you stated, which you missed and which you got
wrong, and suggests an FSRS rating. It never presses the button for you: the
suggestion is advice, and the schedule stays your decision.

**How it grades.** It took four designs to get this reliable, each measured
against labelled answers:

1. *One prompt listing right, missing and wrong points.* `llama3.2:3b` pulled
   facts from the passage instead of the card, filed correct facts under
   "wrong", and gave a wrong answer the same grade as a right one.
2. *The model splits the card into facts, then judges each one three ways.*
   The split changed between calls and sometimes invented a fact, so the same
   answer could earn two grades.
3. *Two yes/no questions per fact on `llama3.2:3b`.* It answered "yes, this
   contradicts the fact" for every answer, including correct ones.
4. **What shipped.** The card's answer is split into facts **in code**, by its
   own punctuation, so the split is deterministic. **Word overlap** decides
   the clear cases without any model call. The model is asked only two narrow
   yes/no questions: "does this answer say the fact?" for paraphrases, and
   "is this claim false?" when the answer introduces a new term. A wrong claim
   always brings one — "glucose", "father", "lower". Judging runs on
   `qwen3:8b` (`GRADER_MODEL`), while chat stays on the faster `llama3.2:3b`.

On eleven labelled answers, `qwen3:8b` with this design graded **10 of 11**
correctly, identically on two runs. The one miss was conservative: a wrong
answer got Hard rather than Again, never Good. Grading a five-fact card takes
about 9 s once the model is loaded, with the facts checked concurrently. An
answer sharing no word with the card returns instantly as "Not yet".

The rating rules are code, so they are tested exactly:

| Answer | Suggested rating |
|---|---|
| every fact, nothing wrong | Good — never Easy, because a grader reading text cannot see how fast you recalled it |
| at least half the facts | Hard |
| less than half, or nothing | Again |
| anything wrong | at most Hard, and Again under half — a confident wrong answer is exactly what spaced repetition must catch |

Known limit: a paraphrase that shares **no** content word with the card's
answer ("passed down maternally" for "inherited from the mother") counts as
missing. A test pins that behaviour so any change to it is deliberate.

`POST /cards/{id}/grade` · 32 tests in `api/tests/test_grading.py`.

## 2. The trust report

Most AI demos say they are accurate. This one measures it.
`python -m evaluation.run` builds a scratch database, uploads a fixed corpus
with real embeddings, asks 20 labelled questions through the real `/chat`
endpoint (12 the notes answer, 8 they don't), grades 28 labelled answers with
the real grader, and writes the numbers to
[`docs/trust-report.md`](trust-report.md) and to the app's
[`/trust`](http://localhost:3100/trust) page. Nothing is mocked.

![the trust page](screens/hackathon/trust-report.png)

**It found real problems, and they were fixed before the numbers were
published.** The first run:

| | First run | After fixes |
|---|---|---|
| Off-topic questions refused | 8 / 8 | 8 / 8 |
| Covered questions wrongly refused | 3 / 12 | **1 / 12** |
| Covered questions answered with the right fact | 9 / 12 | **11 / 12** |
| Answers graded with the right verdict (development set) | 11 / 16 | 16 / 16 |
| Wrong answers graded as correct | 1 / 16 | **0 / 28** |

- *Wrong refusals* came from chunking. At 1800 characters a short lecture was
  a single chunk whose embedding averaged every topic in it, so "Where does
  the Calvin cycle run?" scored 0.552, under the 0.6 floor. Measured at four
  sizes, 600 characters took it from three misses to one without letting any
  off-topic question over the floor.
- *Grading errors* came from the contradiction check seeing a fact ("The
  address space") without the question it answered, and from word overlap
  passing "keep running" for "preempts the running thread". The check now gets
  the question and the full answer, and overlap alone decides only when every
  content word of a fact is present.

Because the grader was fixed using those sixteen answers, they now flatter
it. So **twelve held-out answers** were written after the last change and run
once: **10 / 12 correct, and no wrong answer graded as right.** The two misses
are the known limits — a paraphrase with no word in common ("ten times" for
"an order of magnitude") and a fact that bundles two things ("registers and
stack"). They were left unfixed so the held-out number stays honest.

5 tests on the report's own arithmetic in `api/tests/test_evaluation_metrics.py`.
