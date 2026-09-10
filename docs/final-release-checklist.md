# Final release checklist

Checked on 2026-09-10 against `main`. Every claim below names the file or the
command that backs it, so a reviewer can verify rather than trust.

## Does it work

- [x] **The API starts clean.** `uvicorn app.main:app --port 8100`, then
      `GET /health` → `{"status":"ok","service":"recall-api","version":"0.6.0",…}`.
- [x] **The web app builds.** `pnpm build` — 6 routes, TypeScript strict, no errors.
- [x] **The whole journey runs against real models.** Register → upload →
      cited answer → generated cards → FSRS review → history. Walked with
      screenshots in [`workflow.md`](workflow.md) and
      [`phase-5-study-features.md`](phase-5-study-features.md).
- [x] **The demo account exists and is idempotent.** `python -m app.seed`
      re-seeds `demo@recall.study` rather than failing on a second run.

## The five AI features

| Feature | Endpoint | Verified |
|---|---|---|
| [x] Explain a topic | `POST /study/explain` | live, 10 s, cited |
| [x] Summarise | `POST /study/summarise` | live, 20 s, 4 cited points |
| [x] Quiz | `POST /study/quiz` | live, 48 s, 3 questions, keys correct |
| [x] Flashcards | `POST /study/flashcards`, `POST /cards/generate` | live, cards saved and scheduled |
| [x] Revision checklist | `POST /study/checklist`, MCP `generate_revision_checklist` | live, ordered steps with sources |

All five return Pydantic models, not free text.

## Tests

- [x] **312 automated tests**, none needing a model, a network or a container.
      292 in `api/tests/` (11 files), 20 in `mcp-server/test_server.py`.
- [x] **The rubric's list is covered explicitly** in
      [`api/tests/test_acceptance.py`](../api/tests/test_acceptance.py):
      health, registration, login, protected routes, invalid input, a study
      endpoint end to end, and isolation between two students.
- [x] **76 design-token assertions** on the web side (`pnpm test:tokens`),
      failing on any hex outside the token layer.
- [x] **CI runs all three suites on every push** —
      [`.github/workflows/ci.yml`](../.github/workflows/ci.yml), jobs `api`,
      `mcp`, `web`. Green on `main`.

```bash
cd api        && .venv/bin/python -m pytest -q   # 292 passed
cd mcp-server && .venv/bin/python -m pytest -q   #  20 passed
cd web        && pnpm typecheck && pnpm lint && pnpm test:tokens && pnpm build
```

## Security

- [x] **No secret is committed.** `.env`, `api/.env`, `web/.env.local` and
      `automation/.env` are gitignored; every `.env.example` ships names with
      no values. `git ls-files | grep '\.env$'` returns nothing.
- [x] **`SESSION_SECRET` has no default** and is `min_length=32`. The app
      refuses to start without one.
- [x] **Passwords are argon2id**, hashed before the row is written, verified
      by re-hashing, upgraded on login when parameters strengthen. A test
      asserts the stored hash starts with `$argon2id$` and does not contain
      the password.
- [x] **Login does not leak which addresses exist.** A wrong password and an
      unknown email return the same status and the same body — asserted.
- [x] **Sessions are revocable.** Logout deletes the row; a test proves a
      copied cookie stops working immediately.
- [x] **Tokens are pinned to HS256**, carry no personal data, and expire in
      12 hours. Tampered, foreign-signed, unsigned (`alg: none`), expired,
      wrong-type and orphaned tokens are each refused by a test.
- [x] **Every user query is scoped by owner in the `WHERE` clause.** Another
      student's document, card or session is a 404, not a 403 — confirming an
      id exists is itself a disclosure.
- [x] **The MCP server cannot be handed a credential.** Tests assert no tool
      accepts `password`, `token`, `api_key` or `email`, and that no result
      contains one.
- [x] **The n8n workflow holds no credential.** It reads `$env` at run time;
      the committed JSON was grepped for the demo password.
- [x] **Uploads are bounded**: 10 MB, three extensions, decided by extension
      rather than by the browser's `Content-Type` guess.

## Documentation

- [x] [`README.md`](../README.md) — what it is, how to run it, where everything is.
- [x] [`docs/architecture.md`](architecture.md) — the request lifecycle, the layers, the data model, the AI flow, auth, and the trade-offs.
- [x] [`docs/product-plan.md`](product-plan.md) — the problem, the user, the features.
- [x] [`docs/demo-script.md`](demo-script.md) — a timed five-minute demo with fallbacks.
- [x] [`docs/workflow.md`](workflow.md) — the whole product walked with 32 screenshots.
- [x] Seven phase write-ups, one per lab phase, each with its evidence.
- [x] [`automation/README.md`](../automation/README.md) and [`mcp-server/README.md`](../mcp-server/README.md) — how to run each, and the rules they keep.

## Known limitations

Stated rather than hidden.

- **A 3B model on a CPU is slow and literal.** 10 s for an explanation, ~50 s
  for a quiz. `CHAT_MODEL=qwen3:8b` is better and slower. Quiz keys are
  derived from the answer *text* precisely because the small model cannot
  reliably number its own correct choice.
- **Retrieval can refuse something the notes do cover** if the question is
  phrased with none of the material's words. The fix is a better embedding
  model, not a looser floor.
- **Bearer tokens cannot be revoked** before they expire. That is why they
  last 12 hours and why the browser uses the cookie instead.
- **SQLite allows one writer at a time.** Fine for one student; `DATABASE_URL`
  points at Postgres when that stops being true.
- **Search is a linear scan.** Under a millisecond for thousands of chunks,
  wrong for millions. `retrieval.search()` keeps its signature when the
  storage changes.
- **Not deployed.** Everything runs locally on purpose: the material is
  private, and hosting it would mean sending someone's notes to a third party.
  `COOKIE_SECURE` and `WEB_ORIGIN` are the two settings that would change.

## Not done, deliberately

Mobile apps, shared decks, payments, fine-tuning, and per-student FSRS weight
optimisation. The review log records exactly what the last of these would
need, which is the point at which stopping is a decision rather than an
omission.
