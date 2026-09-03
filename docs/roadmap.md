# Roadmap

Each item below is one pull request. Merged in order; every PR leaves `main`
working and tested.

| # | Branch | Scope | State |
|---|---|---|---|
| 1 | `feat/design-system` | Apple design tokens as CSS custom properties, Tailwind v4 theme, component primitives, a token-coverage test | merged, #1 |
| 2 | `feat/backend-foundation` | FastAPI app, settings, async SQLAlchemy, `/health` | merged with #2 |
| 3 | `feat/auth` | Session-cookie auth, argon2id hashing, registration and login, per-user data scoping | merged, #2 |
| 4 | `feat/documents-rag` | Upload (txt/md/pdf), paragraph-aware chunking with overlap, nomic embeddings through Ollama, cosine search scoped to the owner | merged, #3 |
| 5 | `feat/chat-streaming` | SSE token streaming with citations back to the retrieved chunks, plus a graceful "I can't find that in your notes" | |
| 6 | `feat/spaced-repetition` | FSRS scheduler — stability, difficulty, retrievability — card state machine and review API | |
| 7 | `feat/web-app` | Next.js app in the Apple design language: marketing tiles, chat, library, review session | |
| 8 | `ci` | GitHub Actions: lint, type-check, backend tests, frontend build, design-token check |

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
