# Roadmap

Each item below is one pull request. Merged in order; every PR leaves `main`
working and tested.

| # | Branch | Scope | State |
|---|---|---|---|
| 1 | `feat/design-system` | Apple design tokens as CSS custom properties, Tailwind v4 theme, component primitives, a token-coverage test | merged, #1 |
| 2 | `feat/backend-foundation` | FastAPI app, settings, async SQLAlchemy, `/health` | merged with #2 |
| 3 | `feat/auth` | Session-cookie auth, argon2id hashing, registration and login, per-user data scoping | merged, #2 |
| 4 | `feat/documents-rag` | Upload (txt/md/pdf), paragraph-aware chunking with overlap, nomic embeddings through Ollama, cosine search scoped to the owner | merged, #3 |
| 5 | `feat/chat-streaming` | SSE stream: numbered sources first, then tokens, then a `done` with `grounded`; a fixed refusal when retrieval finds nothing, decided before any model call | merged, #4 |
| 6 | `feat/spaced-repetition` | FSRS-5 scheduler (stability, difficulty, retrievability), learning/review/relearning state machine, card generation from chunks, review API with four-button preview, stats | merged, #5 |
| 7 | `feat/web-app` | The app: library with upload and card generation, streaming chat with numbered sources and citation chips, FSRS review session with four-button preview; landing rebuilt with MagicUI (device mockups with live UI, bento, blur-fade, number tickers, dock navigation) | merged, #6 |
| 8 | `ci` | GitHub Actions: API tests (hash embedder, scripted model — no Ollama needed); web typecheck, lint, token check, build | merged, #7 |

## Why this is not the earlier study-assistant service

An earlier iteration of this idea was a stateless three-endpoint API. It could
answer a question and generate a quiz, and then it forgot you existed. That is a
demo, not a study tool — the thing that makes studying work is the schedule, and
a schedule needs state.

What this adds:

- **Persistence and identity.** Cards, decks, reviews and documents belong to a
  user and survive a restart.
- **A real scheduling algorithm.** FSRS, not "show it again tomorrow". The
  interval is computed from a memory model with per-card difficulty and
  stability.
- **Citations.** An answer that cannot point at the paragraph it came from is
  not usable for study, because you cannot go and read the source.
- **A user interface.** The earlier version had none.
