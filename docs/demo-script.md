# Demo script — five minutes

The order below moves from the problem to the proof. Every command is one
line, and each has a fallback if the machine is being slow.

## Before you start

```bash
ollama serve                                            # models on the host
cd api  && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100
cd web  && pnpm dev --port 3100
cd automation && docker compose up -d                   # only if showing the automation
```

Open four tabs: **localhost:3100** (the app), **localhost:8100/docs**
(Swagger), **localhost:5679** (n8n), **localhost:8026** (Mailpit). Sign in as
`demo@recall.study` / `study-out-loud-2026`. Have one document already
uploaded and one question already asked, so the history is not empty.

Warm the model once — `curl localhost:11434/api/generate -d '{"model":"llama3.2:3b","prompt":"hi"}'` —
so the first live answer is not paying for a cold load.

## 0:00 — the problem (30 seconds)

> Reading a page four times feels like learning. It is mostly recognition.
> What produces recall is being asked, and being asked again just before you
> would forget. And when you ask a general chatbot about your course, it
> answers from the internet, not from what your lecturer said, and it never
> shows you where the answer came from.
>
> Recall does three things: it answers only from the material you uploaded, it
> cites the exact passage, and it schedules what you got wrong.

## 0:30 — the product (90 seconds)

On **localhost:3100**:

1. **Library** — drop a file. Say: *split into passages, embedded locally, no
   upload leaves the machine.*
2. **Ask** — type a question the notes answer. Point at the Sources panel
   filling in **before** the first word: *retrieval happens first.* Click a
   `[1]` chip and show it highlighting its passage.
3. Ask something the notes do not cover — *"who painted the Mona Lisa?"* —
   and show the refusal. Say: *no model was called for that one; retrieval
   already knew.*
4. **Review** — show a card, press **Space**, then point at the four buttons:
   *each shows the interval it would produce, computed by FSRS before you
   choose.*

*If the model is slow:* talk over it — the Sources panel is already on screen
and is the point.

## 2:00 — the backend (60 seconds)

On **localhost:8100/docs**:

> Twenty-four routes. Everything except the root, health, register, login and
> token needs a credential.

- Expand `POST /study/explain`. Say: *four things happen — find the passages
  in this user's material, ask the AI service, save the result, return it with
  the id it was saved as.*
- Expand `GET /study/history`. Show a previous session.
- Say the layering in one sentence: *routers do HTTP, one service owns every
  prompt, one module owns the transport — which is why 292 tests run in CI
  with no model at all.*

## 3:00 — authentication and isolation (45 seconds)

In a terminal:

```bash
TOKEN=$(curl -s -X POST localhost:8100/auth/token \
  -d 'username=demo@recall.study&password=study-out-loud-2026' | jq -r .access_token)

curl -s -H "Authorization: Bearer $TOKEN" localhost:8100/study/history | jq '.[0]'
curl -s localhost:8100/study/history          # 401 — no credential
```

> A browser gets an HttpOnly cookie backed by a row, so signing out is
> instant. A script gets this token, because n8n and the MCP server have no
> cookie jar. Passwords are argon2id, and one student's history is a 404 to
> another — the owner is in the `WHERE` clause, not checked afterwards.

## 3:45 — the automation (40 seconds)

On **localhost:5679**, open *Recall daily review reminder* and press
**Execute workflow**. Then switch to **localhost:8026**.

> Every morning: sign in, ask how many cards are due, and if any are, email
> the first five questions. If nothing is due it sends nothing — a reminder
> that arrives with nothing to do teaches people to ignore reminders.

*If Docker is not up:* show `automation/n8n/workflow.json` and the screenshot
in `docs/phase-6-async-automation-mcp.md`.

## 4:25 — the MCP tool (25 seconds)

```bash
cd mcp-server && RECALL_EMAIL=demo@recall.study RECALL_PASSWORD=… \
  ../api/.venv/bin/python client.py
```

> Any MCP host can call `generate_revision_checklist(topic)` and get ordered
> steps, each citing a passage. The server is a client of this API using that
> same bearer token — it holds no copy of the logic.

## 4:50 — close (10 seconds)

```bash
cd api && .venv/bin/python -m pytest -q      # 292 passed
```

> Three hundred and twelve tests across the API and the MCP server, none of
> them needing a model or a network, all of them running in CI on every push.

## Questions you should expect

**Why not OpenAI?** The material is private and this runs on a laptop with no
per-request cost. The provider is one setting — `app/llm.py` is the only file
that knows, and it already sends a bearer key when one is configured.

**Why a cookie and a token?** Different clients. The browser gets the one that
JavaScript cannot read and that logout can revoke instantly; scripts get the
one they can actually carry. Both are tested on every protected route.

**How do you know it is not making things up?** Retrieval decides first: below
a calibrated similarity floor the model is never called. Above it, the answer
carries the passage numbers, and citations the model invents are dropped
server-side before the client sees them.

**Why is FSRS better than "review in three days"?** It tracks stability,
difficulty and current recall probability per card, so the interval is
computed from your history with that card rather than from a fixed ladder.
The four buttons show what each rating would do before you press one.

**What would you change next?** Fit the FSRS weights to the student's own
review log — the log is already recorded for exactly that — and swap the
brute-force cosine for pgvector when a library outgrows one machine.
