# recall-study — an MCP server

Gives any MCP host — Claude Code, Claude Desktop, an agent you wrote — three
tools over one student's Recall account. Everything is answered from documents
that student uploaded, and nothing here writes.

| Tool | What it does |
|---|---|
| `generate_revision_checklist(topic, items=6)` | ordered steps to work through, each citing the passage it came from |
| `search_notes(query, limit=5)` | find passages, to see what the student actually has |
| `explain_topic(topic, level="beginner")` | a cited explanation from the same material |

Plus one resource, `recall://documents`: the titles and passage counts of
everything uploaded.

The server is a **client of the Recall API**, not a second copy of its logic.
It signs in with `POST /auth/token`, keeps the bearer token, and re-signs in if
it expires. That is what the tokens added in phase 4 are for: an MCP server has
no cookie jar.

## Run it

```bash
uv venv && uv pip install -r requirements.txt

export RECALL_API_URL=http://localhost:8100
export RECALL_EMAIL=demo@recall.study
export RECALL_PASSWORD=…              # never a tool argument

uv run python client.py    # exercise every tool and resource in process
uv run mcp dev server.py   # the MCP Inspector
uv run python server.py    # stdio, for a host to launch
uv run python -m pytest    # 20 tests against a faked API — no network, no model
```

Registering it with Claude Code:

```json
{
  "mcpServers": {
    "recall-study": {
      "command": "/absolute/path/to/api/.venv/bin/python",
      "args": ["/absolute/path/to/mcp-server/server.py"],
      "env": {
        "RECALL_API_URL": "http://localhost:8100",
        "RECALL_EMAIL": "demo@recall.study",
        "RECALL_PASSWORD": "…"
      }
    }
  }
}
```

## Rules it keeps

- **No secrets as arguments.** Credentials come from the environment. An
  argument is chosen by the model, and a model should not be able to send a
  password anywhere — nor receive one in a result. A test asserts no tool
  takes `password`, `token`, `api_key` or `email`, and that no result contains
  one.
- **Nothing writes.** All three tools are annotated `read_only_hint`, so a host
  need not ask for confirmation it does not need.
- **Validation before the call.** A topic under three characters or an item
  count outside 1–12 is refused by the tool, not by the API, so a mistake costs
  no model time.
- **The API's own words.** When Recall refuses — the material does not cover
  the topic, the model is unreachable — that sentence is what the tool returns,
  rather than a status code or a stack trace.
