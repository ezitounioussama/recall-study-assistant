# Product plan — Recall

*AI Study Assistant · Lab phase 1 of 7 · Oussama Ezitouni*

## The idea in one paragraph

Recall turns a student's own material into a practice loop. You upload the
notes, chapters or slides you were actually taught from; you ask questions and
get answers that cite the exact passage they came from; the assistant writes
flashcards from every passage; and a memory model schedules each card for the
moment just before you would forget it. It refuses to answer from general
knowledge: if your material does not cover a question, it says so.

## The problem

Two things go wrong when students study with what they have today.

1. **Re-reading feels like learning and is mostly recognition.** Reading a
   page four times produces familiarity, not recall. What produces recall is
   being asked, and being asked again at increasing intervals. Almost nobody
   builds that schedule by hand.
2. **General chatbots answer confidently from the wrong material.** Asked about
   a course, they answer from the internet, not from what the teacher said, and
   they never show where an answer came from. For revision that is worse than
   no answer: the student cannot check it against the syllabus.

## The target user

A student in a structured course (university module, bootcamp, professional
certification) who has their own notes and lecture material as text or PDF,
studies mostly on a laptop, and wants to spend revision time recalling rather
than re-reading. Secondary user: a teacher who wants to hand students a
question-and-review tool bound to the course material rather than to the open
web.

## What it does

| Area | Feature | What the user sees |
|---|---|---|
| Accounts | Register, sign in, sign out; every document, card and answer belongs to one user | Another user's data is a 404, never visible |
| Library | Upload `.txt`, `.md`, `.pdf`; text is split into passages and embedded locally | Documents with passage counts; passages can be inspected |
| Ask | Retrieval-augmented answers streamed token by token, sources shown first, every `[n]` a clickable citation | Grounded answer or an explicit "I can't find that in your notes" |
| Cards | One click writes flashcards from every passage of a document | Cards appear in the review queue, due now |
| Review | FSRS-5 spaced repetition: stability, difficulty, retrievability per card; four ratings, each showing the interval it would produce | A session, a recall gauge, statistics |
| History | Every generation (answer, cards, quiz, checklist) is saved to the user's account and can be listed and reopened | *planned, phase 5* |

## The AI features

The five features the lab asks for, how each maps onto Recall, and its status.
All of them run against the student's own material through retrieval-augmented
generation (RAG): the relevant passages are retrieved first and the model is
told to answer only from them.

| # | Feature | Endpoint | Input | Output | Status |
|---|---|---|---|---|---|
| 1 | **Explain a topic** | `POST /chat` today; `POST /study/explain` in phase 5 | topic or question, optional document scope | streamed explanation with numbered citations into the user's passages; refusal if nothing relevant | built (as cited Q&A) |
| 2 | **Summarize a lesson** | `POST /chat` today; `POST /study/summarise` in phase 5 | a document, or a question of the form "summarise X" | a cited bullet summary, as many points as the material supports, never padded | built (via the chat prompt) |
| 3 | **Generate quiz questions** | `POST /study/quiz` | document id, number of questions, difficulty | JSON list of `{question, choices[4], answer_index, explanation, source_chunk_id}` | planned, phase 5 |
| 4 | **Generate flashcards** | `POST /cards/generate` | document id, cards per passage | JSON list of `{front, back, chunk_id}`; each card enters the FSRS schedule | built |
| 5 | **Create a revision checklist** | MCP tool `generate_revision_checklist(topic)` and `POST /study/checklist` | topic | structured checklist `{topic, items[{step, why, source}]}` ordered from recall to application | planned, phase 6 |

Design rules that apply to all five:

- **Structured output.** Every AI function returns a Pydantic model, never free
  text the caller has to parse. Small local models drift, so JSON mode is used
  where the model supports it and the parser is defensive (bad items are
  dropped, never invented).
- **Grounded first.** Retrieval decides whether the model is asked at all. A
  question whose best passage scores below the similarity floor (0.6 cosine on
  `nomic-embed-text`) gets a fixed refusal, decided before any model call.
- **Citations are validated.** The server checks that every `[n]` the model
  writes refers to a passage it was given; invented references are dropped from
  the `citations` list the client highlights.
- **Secrets stay out of code.** The session secret and model settings come from
  `.env`; `.env.example` documents them with no real values.

## Architecture

```
 browser ── Next.js 16 (web/) ── fetch + SSE ──► FastAPI (api/app/)
                                                   ├── routers/   auth · documents · chat · cards  (+ study, history: phase 5)
                                                   ├── services   ingest · embeddings · retrieval · llm · fsrs
                                                   ├── SQLAlchemy (async) ── SQLite (Postgres-ready)
                                                   └── Ollama ── nomic-embed-text (768-d embeddings)
                                                             └── llama3.2:3b / qwen3:8b (answers, cards, quiz)
```

- **Backend:** FastAPI, async SQLAlchemy 2.0, Pydantic v2. Every AI call is
  `async` and streamed where the user waits on it.
- **Model provider:** Ollama on the student's machine. Reasons: the material is
  private and never leaves the laptop; there is no per-request cost; the
  provider is one setting, so an OpenAI-compatible endpoint can replace it
  without touching route code (`app/llm.py` is the only file that knows).
- **Authentication:** argon2id password hashes and a signed, HttpOnly,
  SameSite session cookie backed by a server-side session row. This is the
  cookie-session alternative to JWT: sign-out is immediate (the row is
  deleted), and JavaScript cannot read the token. The lab's JWT criterion is
  met in spirit (private routes require a valid signed credential); the
  trade-off is documented in `docs/architecture.md` in phase 7.
- **Scheduling:** FSRS-5 with the published default weights, implemented as
  pure functions with 24 property tests.
- **Front end:** Next.js 16, React 19, Tailwind v4, built to a design-token
  specification with a test that fails on any colour outside it.

## Scope for the lab

**In:** everything in the tables above; one automation workflow; one MCP tool;
tests; documentation; a five-minute demo.

**Out:** mobile apps, collaborative decks, payments, hosted deployment,
fine-tuning. The goal is a complete, explainable backend with a working
product on top, not a commercial platform.

## Plan against the seven lab phases

| Phase | Lab objective | Recall | State |
|---|---|---|---|
| 1 | Product plan, repository structure | this document; structure below | this submission |
| 2 | FastAPI app, `/` and `/health`, Swagger | `api/app/main.py`, `/health`, `/docs` | done (PR #2) |
| 3 | LLM integration, AI functions, `.env` | `app/llm.py` (Ollama adapter, scripted test double), `app/embeddings.py`, prompts for explain/summarise/flashcards | done (PRs #3–#5); quiz added in phase 5 |
| 4 | Database, register/login/me, protected data | `User`, `Session`, `Document`, `Chunk`, `Card`, `ReviewLog`; `/auth/*`; per-user 404s | done (PR #2); `StudySession` + `GeneratedContent` models added in phase 5 |
| 5 | `/study/*` endpoints and history | add `/study/explain`, `/study/summarise`, `/study/quiz`, `/study/flashcards`, `/study/checklist`; save every result; `GET /study/history[/{id}]` | next |
| 6 | Async, timeouts, one automation, one MCP tool | AI calls already async and streamed; add timeouts with friendly errors; automation = the n8n workflow in [study-summary-automation](https://github.com/ezitounioussama/study-summary-automation) (webhook → summarise → email), wired to this API; MCP tool `generate_revision_checklist(topic)` | partly done |
| 7 | Tests, docs, release checklist, demo | 93 API tests today; add `docs/architecture.md`, `docs/final-release-checklist.md`, `docs/demo-script.md`; [`docs/workflow.md`](workflow.md) already walks the product with screenshots | partly done |

The per-pull-request history is in [`docs/roadmap.md`](roadmap.md).

## Repository structure

The lab's layout, and where each part lives in this repository. The project is
a monorepo with the backend in `api/` and the web client in `web/`, so the
Python application sits one level down.

| Lab expects | Here | Contents |
|---|---|---|
| `app/` | [`api/app/`](../api/app) | `main.py`, `config.py`, `db.py`, `models.py`, `schemas.py`, `security.py`, `ingest.py`, `embeddings.py`, `retrieval.py`, `llm.py`, `fsrs.py`, `seed.py`, `routers/` |
| `tests/` | [`api/tests/`](../api/tests) | 93 tests: auth, documents, chat, FSRS, cards |
| `.env.example` | [`.env.example`](../.env.example) (index) · [`api/.env.example`](../api/.env.example) · [`web/.env.example`](../web/.env.example) | every variable, no real values |
| `requirements.txt` | [`requirements.txt`](../requirements.txt) → [`api/requirements.txt`](../api/requirements.txt) | Python dependencies |
| `README.md` | [`README.md`](../README.md) | run, sign in, verify |
| `docs/` | [`docs/`](.) | this plan, roadmap, workflow tour with screenshots, design specification |
| — | [`web/`](../web) | Next.js client |
| — | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | tests, lint, type-check, build on every push |

## Risks and how they are handled

| Risk | Mitigation |
|---|---|
| A small local model invents facts | retrieval decides refusal before the model is called; prompt forbids outside facts; citations validated; `qwen3:8b` available when quality matters more than speed |
| CPU-only inference is slow (a minute per answer with the larger model) | streaming so the user sees progress; `llama3.2:3b` default at a few seconds; card generation bounded to 60 cards per call |
| Users' material is sensitive | everything runs locally; per-user scoping at the query level; no third-party API by default |
| Scope creep in a 28-hour lab | one pull request per feature, each leaving `main` tested; the phase table above is the contract |

## Success criteria

- A new user can register, upload a document, ask a question and get a cited
  answer, generate cards, and complete a review session without reading any
  documentation.
- All five AI features return structured output and are covered by tests that
  need no model.
- Every generated artefact is saved to the user's history and retrievable.
- The automation workflow and the MCP tool can be demonstrated live.
- The whole project is presentable in five minutes.
