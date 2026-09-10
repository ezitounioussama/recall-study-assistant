# Architecture

How a request becomes an answer, where each decision lives, and what was
traded for what.

## The shape

```
 browser ──── Next.js 16 (web/) ──── fetch + SSE ────┐
                                                     │
 n8n automation ──── bearer token ───────────────────┤
                                                     ├──► FastAPI (api/app/)
 MCP host ──── mcp-server/ ──── bearer token ────────┘         │
                                                               │
   routers/     ops · auth · documents · chat · cards · study   (HTTP only)
   services/    ai_service · study_history                      (prompts, saving)
   the rest     ingest · embeddings · retrieval · fsrs · llm     (one job each)
        │                                    │
        ▼                                    ▼
   SQLAlchemy 2.0 async ── SQLite        Ollama ── nomic-embed-text (768-d)
   (7 tables)                                   └── llama3.2:3b / qwen3:8b
```

Three clients, one API. The web app is the product; the automation and the MCP
server are why bearer tokens exist, since neither has a cookie jar.

## One request, end to end

`POST /study/explain {"topic": "what a process control block holds"}`

1. **FastAPI** matches the route and validates the body against
   `ExplainRequest`. A topic under three characters is a 422 here, before
   anything expensive happens.
2. **`current_user`** reads the `Authorization` header or the session cookie,
   verifies it, and loads the user. No credential is a 401.
3. **`find_sources`** embeds the topic with `nomic-embed-text` and searches
   *this user's* chunks by cosine similarity. Passages below 0.6 are dropped.
   This step is both the security boundary and the grounding decision.
4. **`AiService.explain`** renders the passages into the prompt, numbered, and
   asks the model. If step 3 found nothing, the model is not called at all and
   a fixed refusal is returned.
5. **`study_history.record`** writes a `StudySession` and a
   `GeneratedContent` row: the prose, the structure, and whether it was
   grounded.
6. **The response** carries the explanation, the passages it used, and the
   `session_id` it was saved as.

Steps 3 to 5 are the same four lines in all five study endpoints. Only the
service method and the artefact shape differ.

## Why the layers are where they are

**Routers do HTTP.** Read the request, check who is asking, call something,
shape the response. No prompt, no SQL beyond a scoped query, no parsing of
model output.

**`services/ai_service.py` owns every prompt.** One file to read when an
answer looks wrong, one place to change when a model behaves differently.
Each method returns a Pydantic model, so a route can hand the result straight
back and its shape appears in the OpenAPI schema.

**`llm.py` owns the transport.** A `ChatModel` protocol with `complete()` and
`stream()`, an Ollama implementation, and a scripted one for tests. Swapping
provider is a settings change; testing a prompt needs no network. This is why
292 API tests run in CI without a model.

**`fsrs.py` is pure.** The scheduler takes a memory state and a rating and
returns a new state; the clock is passed in. Twenty-four tests check the
model's shape — R(S) = 0.9 by definition, forgetting shrinks stability, a
late recall gains more than an on-time one — with no database in sight.

## The data model

```
users ─┬─< sessions                     server-side rows; deleting one signs that browser out
       ├─< documents ─< chunks          uploaded material, split and embedded (vector as float32 bytes)
       ├─< cards ─< review_logs         flashcards, their FSRS state, and every rating
       └─< study_sessions ─< generated_content    what was asked for, and what came back
```

Choices worth naming:

- **`chunks.user_id` and `generated_content.user_id` are denormalised.** Every
  query is "this user's rows", and the ownership filter should not need a
  join. The parent row stays the source of truth.
- **Cards outlive their document.** `document_id` is `SET NULL`, so deleting
  material does not erase what you learned from it.
- **Timestamps are stamped in Python.** SQLite's `CURRENT_TIMESTAMP` resolves
  to whole seconds, so rows created in the same second tied and "newest first"
  fell back to a random uuid. A test caught it.
- **Embeddings are packed `float32` in a `BLOB`.** SQLite has no vector type;
  the raw buffer decodes in one numpy call and is six times smaller than a
  JSON array.

## The AI flow

Retrieval-augmented generation, with the retrieval doing more than usual.

```
question ──► embed ──► cosine over this user's chunks ──► above 0.6 ?
                                                            │ no  → refuse, no model call
                                                            │ yes
                                        numbered passages ──► prompt ──► model ──► validate citations
```

- **The similarity floor is calibrated, not guessed.** On
  `nomic-embed-text`, a relevant passage scores 0.8+ and an unrelated one
  0.43–0.57. 0.6 sits in the gap.
- **The refusal is deterministic.** Deciding it by retrieval means the same
  question always gets the same answer about whether the material covers it.
  Leaving that to the model is a coin toss dressed up as a policy.
- **Citations are checked.** A `[2]` when only one passage was supplied is
  dropped from the `citations` list, so the client never highlights something
  that does not exist.
- **Structured output is parsed defensively.** JSON mode where the provider
  supports it, a parser that drops what it cannot read, and — for quizzes —
  the answer identified by *text* rather than by index, because a 3B model
  writes four good options and then points at the wrong one.
- **Streaming where the wait is visible.** `/chat` sends passages first, then
  tokens as they arrive. The study endpoints return once, because their
  callers want the whole structure.

## Authentication

| | Session cookie | Bearer token |
|---|---|---|
| For | the browser | n8n, the MCP server, curl, Swagger |
| From | `/auth/login`, `/auth/register` | `/auth/token` (OAuth2 password flow) |
| Carried in | `recall_session`, HttpOnly, SameSite=Lax | `Authorization: Bearer …` |
| Backed by | a `sessions` row | its signature alone |
| Revocable | yes, instantly | no — so it expires in 12 hours |

`current_user` accepts either and nothing downstream knows which was used. The
JWT carries `sub`, `iat`, `exp`, `jti`, `typ` and nothing else: it is signed,
not encrypted, so anyone holding it can read the payload. The decoder pins
`algorithms=["HS256"]`, because a token whose header says `alg: none` would
otherwise ask the server to accept the attacker's choice of verification.

Passwords are argon2id at the library's defaults, verified by re-hashing and
upgraded on login when the parameters strengthen. Not bcrypt: bcrypt silently
truncates at 72 bytes, turning a long passphrase into a shorter one without
telling anyone. There is a test proving argon2 does not.

## Automation and MCP

Both are **clients of the API**, not extensions of it. Neither imports
application code.

- [`automation/`](../automation) — an n8n workflow that signs in every morning,
  asks how many cards are due, and emails the student the first five
  questions. Nothing due sends nothing.
- [`mcp-server/`](../mcp-server) — an MCP server exposing
  `generate_revision_checklist`, `search_notes` and `explain_topic` to any host
  that speaks the protocol. Credentials come from its environment and can never
  be a tool argument.

Keeping them outside means the API has one contract to honour, and a change to
either cannot break the product.

## Decisions and their costs

| Decision | Why | What it costs |
|---|---|---|
| Local models through Ollama | the material is private and never leaves the laptop; no per-request cost; the provider is one setting | slow on a CPU — 10 s for an explanation, 50 s for a quiz — and a 3B model needs careful prompting |
| SQLite | zero setup, one file, real SQL | one writer at a time; `DATABASE_URL` points at Postgres when that matters |
| Brute-force cosine in numpy | a student's library is thousands of chunks; a dot product over them is under a millisecond | linear in library size; `search()`'s signature does not change when it becomes pgvector |
| Cookie **and** token | the browser gets the safer one, scripts get the practical one | two paths to keep tested — both are, on every protected route |
| FSRS-5 with published weights | a real memory model, not a fixed ladder | the weights are not fitted to *this* student; the review log is exactly what a future optimiser would train on |
| Refusal decided by retrieval | deterministic, and free | a question phrased unluckily can be refused when the material does cover it; the fix is a better embedding model, not a looser floor |

## Verifying it

```bash
cd api        && .venv/bin/python -m pytest -q   # 292
cd mcp-server && .venv/bin/python -m pytest -q   #  20
cd web        && pnpm typecheck && pnpm lint && pnpm test:tokens && pnpm build
```

CI runs all three on every push. No test needs a model, a network or a
container.
