# Recall

An AI study assistant that answers **only from your own notes**, cites the
exact passage behind every sentence, and schedules what you got wrong with a
real memory model. Everything runs on your machine.

![the landing page](docs/screens/landing.png)

Reading a page four times feels like learning and is mostly recognition. What
produces recall is being asked, and being asked again just before you would
forget — and an answer you cannot check against the syllabus is worse than no
answer. Recall is those two ideas in one loop: upload the material, ask it
questions, review what it turns into cards.

## Run it

```bash
ollama pull nomic-embed-text && ollama pull llama3.2:3b   # once
ollama serve

cd api                                         # terminal 1 — the API on :8100
uv venv --python 3.12 && uv pip install -r requirements.txt
cp .env.example .env    # then set SESSION_SECRET:
                        # python -c "import secrets; print(secrets.token_urlsafe(48))"
.venv/bin/python -m app.seed
.venv/bin/uvicorn app.main:app --port 8100

cd web                                         # terminal 2 — the app on :3100
pnpm install && cp .env.example .env.local
pnpm dev --port 3100
```

Open **http://localhost:3100** and sign in with `demo@recall.study` /
`study-out-loud-2026`. Interactive API docs are at
**http://localhost:8100/docs**.

## Where things are

| | |
|---|---|
| [`api/`](api) | the FastAPI backend — routers, the AI service, FSRS, 292 tests |
| [`web/`](web) | the Next.js client, built to a design-token specification |
| [`automation/`](automation) | an n8n workflow that emails what is due each morning |
| [`mcp-server/`](mcp-server) | an MCP server exposing the revision-checklist tool |
| [`docs/`](docs) | everything below |

## Read about it

- [**Architecture**](docs/architecture.md) — a request end to end, the layers, the data model, the AI flow, and what each decision cost.
- [**Product plan**](docs/product-plan.md) — the problem, the user, the five AI features.
- [**Demo script**](docs/demo-script.md) — a timed five-minute walkthrough.
- [**Workflow tour**](docs/workflow.md) — the whole product, screenshot by screenshot.
- [**Release checklist**](docs/final-release-checklist.md) — what is verified, and the limitations that remain.
- [**Design**](docs/design-language.md) and [its divergences](docs/design-divergences.md) — the Apple design language the interface is built to.

Phase write-ups: [1 plan](docs/product-plan.md) · [2 backend](docs/phase-2-backend-foundation.md) · [3 LLM](docs/phase-3-llm-integration.md) · [4 database and auth](docs/phase-4-database-and-auth.md) · [5 study features](docs/phase-5-study-features.md) · [6 async, automation, MCP](docs/phase-6-async-automation-mcp.md) · [7 tests, docs, demo](docs/final-release-checklist.md)

## Verify it

```bash
cd api        && .venv/bin/python -m pytest -q   # 292 passed
cd mcp-server && .venv/bin/python -m pytest -q   #  20 passed
cd web        && pnpm typecheck && pnpm lint && pnpm test:tokens && pnpm build
```

No test needs a model, a network or a container. CI runs all three on every
push.

---

Author: **Oussama Ezitouni**
