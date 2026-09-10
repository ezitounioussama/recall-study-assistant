"""recall-study — an MCP server over one student's Recall account.

Three tools, all backed by the Recall API rather than by a model directly:
the checklist, the search that finds what to make a checklist about, and the
explanation that answers a question from the same material. Everything is
grounded in documents the student uploaded, and everything is scoped to the
one account whose credentials this server holds.

    RECALL_API_URL=http://localhost:8100 \
    RECALL_EMAIL=demo@recall.study RECALL_PASSWORD=… \
    uv run python server.py            # stdio, for a host
    uv run mcp dev server.py           # the Inspector
"""

from __future__ import annotations

import logging
import sys

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from recall_client import RecallClient, RecallError

# stdout is the protocol channel on stdio; logs go to stderr or they corrupt it.
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

mcp = MCPServer(
    "recall-study",
    instructions=(
        "Tools over one student's own study material in Recall. Every answer is grounded in "
        "documents they uploaded: if the material does not cover a topic, the tools say so rather "
        "than answering from general knowledge. Use search_notes first when unsure what the "
        "student has, then generate_revision_checklist or explain_topic."
    ),
)

# Nothing here writes: no tool creates, deletes or changes anything in the
# account. Saying so in the annotations lets a host skip a confirmation it
# does not need.
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=False, open_world_hint=False)

_client: RecallClient | None = None


def client() -> RecallClient:
    """The API client, built on first use so importing this file needs no environment."""
    global _client
    if _client is None:
        _client = RecallClient()
    return _client


def use_client(replacement: RecallClient) -> None:
    """Point the server at another API. For tests."""
    global _client
    _client = replacement


def _topic(value: str) -> str:
    topic = (value or "").strip()
    if len(topic) < 3:
        raise ToolError("topic must be at least 3 characters — it is also the search query.")
    if len(topic) > 500:
        raise ToolError("topic is limited to 500 characters.")
    return topic


def _count(name: str, value: int, low: int, high: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise ToolError(f"{name} must be a whole number between {low} and {high}, got {value!r}.")
    return value


@mcp.tool(annotations=READ_ONLY)
async def generate_revision_checklist(topic: str, items: int = 6) -> dict:
    """Build a revision checklist for a topic from the student's own notes.

    Returns ordered steps, each one an action to perform — recall this without
    looking, explain that out loud, work through an example — from remembering
    the definitions to applying them. Every step cites the passage it came
    from. If the student's material does not cover the topic, that is said
    plainly instead of inventing steps.
    """
    topic = _topic(topic)
    items = _count("items", items, 1, 12)
    try:
        result = await client().post("/study/checklist", {"topic": topic, "items": items})
    except RecallError as exc:
        raise ToolError(str(exc)) from exc

    checklist = result["checklist"]
    return {
        "topic": checklist["topic"],
        "items": [
            {
                "n": i,
                "step": item["step"],
                "why": item["why"],
                "source": _source_label(result["sources"], item.get("source_index")),
            }
            for i, item in enumerate(checklist["items"], 1)
        ],
        "based_on": sorted({s["document_title"] for s in result["sources"]}),
        "saved_as": result["session_id"],
    }


@mcp.tool(annotations=READ_ONLY)
async def search_notes(query: str, limit: int = 5) -> list[dict]:
    """Find passages in the student's uploaded material.

    Use this to see what they actually have before asking for a checklist or
    an explanation. Returns the document, the passage number, a similarity
    score and the text.
    """
    query = _topic(query)
    limit = _count("limit", limit, 1, 20)
    try:
        hits = await client().get("/documents/search", params={"q": query, "k": limit})
    except RecallError as exc:
        raise ToolError(str(exc)) from exc

    return [
        {
            "document": hit["document_title"],
            "passage": hit["position"] + 1,
            "score": hit["score"],
            "text": hit["text"][:600],
        }
        for hit in hits
    ]


@mcp.tool(annotations=READ_ONLY)
async def explain_topic(topic: str, level: str = "beginner") -> dict:
    """Explain a topic using only the student's own notes, with citations.

    `level` is beginner, intermediate or advanced. Returns the explanation,
    whether it was grounded in the material, and which passages it used.
    """
    topic = _topic(topic)
    if level not in ("beginner", "intermediate", "advanced"):
        raise ToolError('level must be "beginner", "intermediate" or "advanced".')
    try:
        result = await client().post("/study/explain", {"topic": topic, "level": level})
    except RecallError as exc:
        raise ToolError(str(exc)) from exc

    explanation = result["explanation"]
    return {
        "topic": explanation["topic"],
        "explanation": explanation["text"],
        "grounded": explanation["grounded"],
        "cited_passages": [
            _source_label(result["sources"], index) for index in explanation["citations"]
        ],
        "saved_as": result["session_id"],
    }


@mcp.resource("recall://documents", mime_type="application/json")
async def documents() -> str:
    """What the student has uploaded: titles, passage counts, dates."""
    import json

    try:
        listed = await client().get("/documents")
    except RecallError as exc:
        raise ValueError(str(exc)) from exc
    return json.dumps(
        [
            {"title": d["title"], "passages": d["chunk_count"], "added": d["created_at"][:10]}
            for d in listed
        ],
        indent=2,
    )


def _source_label(sources: list[dict], index: int | None) -> str | None:
    """"Operating systems notes, part 2" for a citation number."""
    if not index:
        return None
    for source in sources:
        if source["index"] == index:
            return f"{source['document_title']}, part {source['position'] + 1}"
    return None


if __name__ == "__main__":
    mcp.run()
