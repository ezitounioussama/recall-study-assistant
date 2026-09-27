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
