# Automation — the daily review reminder

Spaced repetition only works if you come back. This is the part that asks.

```
every morning at 08:00
        ↓
POST /auth/token          sign in as the student (bearer token, from $env)
        ↓
GET  /cards/stats         how many cards are due, and how the deck is doing
        ↓
due_now > 0 ?             no  → stop quietly, no email
        ↓ yes
GET  /cards/due?limit=5   what the first few actually ask
        ↓
compose                   subject, the five questions, the deck's state
        ↓
send email                to the student
```

**Trigger:** a schedule (08:00 daily), plus a manual trigger so it can be run
on demand while presenting. **Action:** four API calls and an email.
**Result:** a message in the inbox, or deliberate silence when nothing is due.

## Run it

The API must be reachable from inside the container, so bind it to all
interfaces rather than loopback:

```bash
cd api && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100

cd automation
cp .env.example .env          # put the account's password in it
docker compose up -d          # n8n :5679, mailpit :8026

docker compose exec n8n n8n import:credentials --input=/workflows/credentials.json
docker compose exec n8n n8n import:workflow    --input=/workflows/workflow.json
```

Then either open <http://localhost:5679>, choose *Recall daily review
reminder* and press **Execute workflow**, or run it from the command line:

```bash
docker compose exec -e N8N_RUNNERS_BROKER_PORT=5690 n8n n8n execute --id recall-daily-review
```

The port override is needed because the container's own task broker already
holds 5679; without it the CLI refuses to start a second one.

The delivered mail is at <http://localhost:8026>. Nothing leaves the machine:
Mailpit is a real SMTP server that accepts everything and forwards nothing.

To have it run on the schedule rather than on demand, activate the workflow in
the editor.

## Why the ports are odd

5679 and 8026, not the usual 5678 and 8025, so this stack can run beside
another n8n without either winning. The `study-summary-automation` project
uses the defaults.

## No secrets in the workflow file

The email and password are read at run time with `{{ $env.RECALL_EMAIL }}` and
`{{ $env.RECALL_PASSWORD }}`, which come from `automation/.env` through the
compose file. `n8n/workflow.json` is exported and committed with no credential
in it; the SMTP password lives in n8n's encrypted credential store, seeded
from `n8n/credentials.json` (a local Mailpit that checks nothing).
