# Workflow

The whole product, walked end to end on 2026-09-03 against a fresh database.
Every screenshot below was taken during that walk, in a real browser, with
the real local models. Nothing is mocked.

## Credentials and addresses

| | |
|---|---|
| Web app | http://localhost:3100 |
| API | http://localhost:8100 — interactive docs at http://localhost:8100/docs |
| Ollama | http://127.0.0.1:11434 (must run as your user, not the systemd unit) |
| Demo account | **demo@recall.study** / **study-out-loud-2026** |
| Session secret | generated once into `api/.env` — `python -c "import secrets; print(secrets.token_urlsafe(48))"` — never committed |

The demo account is created by `python -m app.seed`, which is idempotent: run it
again and it resets that password instead of failing. Register any other account
from the sign-in page; accounts only see their own documents and cards.

## Start everything

```bash
# 0. models (once)
ollama pull nomic-embed-text      # embeddings, 274 MB
ollama pull llama3.2:3b           # answers and card writing, 2 GB
ollama serve                      # if it is not already running

# 1. API on :8100
cd api
uv venv --python 3.12 && uv pip install -r requirements.txt
cp .env.example .env               # put a SESSION_SECRET in it (see above)
.venv/bin/python -m app.seed
.venv/bin/uvicorn app.main:app --port 8100

# 2. web on :3100
cd web
pnpm install
cp .env.example .env.local         # NEXT_PUBLIC_API_URL=http://localhost:8100
pnpm dev --port 3100
```

The API is started without `--reload`; after a backend change, restart it.

Optional: `CHAT_MODEL=qwen3:8b` in `api/.env` for noticeably better answers
(about a minute per answer on a CPU instead of a few seconds).

## The tour

### 1. Landing

The product page in the iPhone Air grammar: two-tone product name, one big
claim per section, grey lead copy with the claims in ink, one dark band. The
device frames hold live miniatures of the chat and review screens, not
screenshots.

![landing hero](screens/tour/01-landing-hero.png)
![the product in frames](screens/tour/02-landing-product.png)
![scheduling](screens/tour/03-landing-scheduling.png)
![four differences](screens/tour/04-landing-bento.png)
![the dark band](screens/tour/05-landing-dark.png)

On a phone the display sizes step down one rung of the same type ladder, so
nothing overflows the viewport.

<p><img src="screens/tour/06-landing-mobile.png" width="260"> <img src="screens/tour/07-landing-mobile-product.png" width="260"> <img src="screens/tour/08-landing-mobile-bento.png" width="260"></p>

### 2. Sign in

Visiting `/library` signed out sends you to `/sign-in?next=/library`, and back
again once you are in. A wrong password gets one message — the same one for an
unknown email, so the form cannot be used to check which addresses exist.
**Use the demo account** fills both fields.

![redirected to sign in](screens/tour/09-redirect-to-sign-in.png)
![wrong password](screens/tour/10-sign-in-wrong-password.png)
![demo credentials filled](screens/tour/11-sign-in-demo-filled.png)
![signed in](screens/tour/12-signed-in.png)

Behind it: argon2id password hashes, a signed `HttpOnly; SameSite=Lax` session
cookie, and a server-side session row — sign-out deletes the row, so a copied
cookie stops working immediately.

### 3. Library — upload and generate

Drop `.txt`, `.md` or `.pdf` (10 MB max). The API extracts the text, splits it
into ~1,800-character passages along paragraph boundaries with a 200-character
overlap, embeds each with `nomic-embed-text`, and stores the vectors. A 7 KB
lecture note became 5 passages; a one-page PDF and a short `.txt` one each.

![empty library](screens/tour/13-library-empty.png)
![three documents](screens/tour/14-library-three-documents.png)

**Generate cards** sends each passage to the chat model in JSON mode and asks
for three flashcards. Fifteen cards from five passages, in about 90 seconds on
a CPU. It is idempotent — passages that already have cards are skipped, so
clicking again does not double the deck. **Show passages** reveals the chunks
as the retriever sees them.

![cards generated](screens/tour/15-library-cards-generated.png)
![passages](screens/tour/16-library-passages.png)

### 4. Ask — cited answers, streamed

Retrieval runs first: the question is embedded, the closest passages above a
similarity floor of 0.6 are picked, and they appear in the Sources panel,
numbered, before the first word of the answer arrives. The answer streams over
server-sent events; each `[n]` becomes a chip that highlights its passage.

![empty chat with suggestions](screens/tour/17-chat-empty.png)
![a cited answer](screens/tour/18-chat-cited-answer.png)
![a citation highlighted](screens/tour/19-chat-citation-highlight.png)

Follow-ups keep the topic: the previous question is folded into the retrieval
query, so "and how is that different from what CFS does?" finds the CFS
passage instead of drifting.

![a follow-up](screens/tour/20-chat-follow-up.png)

**Scope** limits retrieval to one document. A question the material does not
cover is refused before any model is called — the refusal is a fixed
sentence, decided by retrieval, and the hint under it says why.

![scoped to one document](screens/tour/21-chat-scoped-to-document.png)
![a refusal](screens/tour/22-chat-refusal.png)

<p><img src="screens/tour/23-chat-mobile.png" width="260"></p>

### 5. Review — the FSRS session

One card at a time. **Space** (or the button) shows the answer; **1–4** (or the
four buttons) rate it. Under each rating is the interval it would produce,
computed by the scheduler before you choose. The passage the card came from is
one capsule away.

![a question](screens/tour/24-review-question.png)
![the answer](screens/tour/25-review-answer.png)
![the source passage](screens/tour/26-review-source-passage.png)
![mid-session](screens/tour/27-review-mid-session.png)

The gauge is the deck's mean retrievability — the probability, right now, that
you remember a card — and it moves as you rate. When the queue empties the
session ends; come back and the schedule says when the next card is due.

![session done](screens/tour/28-review-session-done.png)
![nothing due](screens/tour/29-review-nothing-due.png)

FSRS-5, with the published default weights: each card carries stability (days
until recall falls to 90%), difficulty (1–10) and retrievability. A new card
walks learning steps of 1 and 10 minutes before graduating; a lapse drops it
into a 10-minute relearning step. Every rating is appended to a review log.

<p><img src="screens/tour/30-library-mobile.png" width="260"></p>

### 6. Sign out

The last dock icon. It returns you to the landing page and every app route is
protected again.

![signed out](screens/tour/32-signed-out-landing.png)

## The API

FastAPI, documented at `/docs`. Every route except `/health`, `/auth/register`
and `/auth/login` needs the session cookie, and every query is scoped to the
signed-in user — another user's document or card is a 404, not a 403.

![swagger](screens/tour/31-api-swagger.png)

| Route | Purpose |
|---|---|
| `POST /auth/register` · `POST /auth/login` · `POST /auth/logout` · `GET /auth/me` | session-cookie auth |
| `POST /documents` · `GET /documents` · `GET /documents/{id}` · `DELETE /documents/{id}` | upload, list, inspect (with passages), delete |
| `GET /documents/search?q=&k=` | cosine search over the user's passages |
| `POST /chat` | SSE stream: `sources`, `token`…, `done {answer, grounded, citations}` |
| `POST /cards/generate` · `POST /cards` · `GET /cards` · `GET /cards/{id}` · `DELETE /cards/{id}` | flashcards |
| `GET /cards/due` · `POST /cards/{id}/review` · `GET /cards/stats` | the review loop |

## The AI

| Piece | Choice | Why |
|---|---|---|
| Embeddings | `nomic-embed-text` via Ollama, with the model's `search_document:` / `search_query:` prefixes | local, 768 dimensions, good separation: relevant passages score 0.8+, unrelated ones under 0.57 |
| Similarity floor | 0.6 | calibrated on the above; below it, refuse without asking the model |
| Answers and cards | `llama3.2:3b` (default) or `qwen3:8b` | seconds vs. a minute per answer on a CPU; the prompt shows the answer format rather than describing it, which is what small models follow |
| Grounding | passages in the prompt, citations validated server-side, follow-ups retrieved with the previous question | the `citations` list in `done` only contains numbers that exist |
| Scheduling | FSRS-5, default weights | a memory model, not a ladder of fixed intervals |

## Verify it yourself

```bash
cd api && .venv/bin/python -m pytest -q        # 93 tests, no model needed
cd web && pnpm typecheck && pnpm lint && pnpm test:tokens && pnpm build
```

CI runs the same on every push and pull request (`.github/workflows/ci.yml`).

## When something looks wrong

| Symptom | Cause | Fix |
|---|---|---|
| `Module not found: Can't resolve '@swc/helpers/…'` in the browser | dependencies were reinstalled while `next dev` was running | stop the dev server, `rm -rf web/.next`, start it again, hard-reload the tab |
| Library or chat shows `Not Found` / 404s in the console | the API process predates a backend change | restart uvicorn |
| Every question is refused | Ollama is not running, or `nomic-embed-text` is not pulled | `ollama serve` as your user; `ollama pull nomic-embed-text` |
| `pnpm install` exits 1 with `ERR_PNPM_IGNORED_BUILDS` | pnpm 11 blocks unapproved postinstalls | already handled by `allowBuilds` in `web/pnpm-workspace.yaml`; if a new one appears, `pnpm approve-builds --all` |
| Answers invent facts | a 3B model filling gaps | `CHAT_MODEL=qwen3:8b`, or ask more specifically; the prompt forbids it but cannot always stop it |
