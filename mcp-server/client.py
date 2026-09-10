"""Exercise every capability of the recall-study MCP server, in process.

Connects to the server object directly — no subprocess, no network — the way
the SDK's own tests do. Needs a running Recall API and credentials:

    RECALL_EMAIL=demo@recall.study RECALL_PASSWORD=… uv run python client.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import Client

from server import mcp


def show(title: str, body: object) -> None:
    print(f"\n── {title} " + "─" * max(0, 78 - len(title)))
    print(body if isinstance(body, str) else json.dumps(body, indent=2, ensure_ascii=False)[:1600])


def payload(result):
    text = "\n".join(getattr(c, "text", "") for c in result.content)
    if result.is_error:
        return "TOOL ERROR: " + text
    if result.structured_content is not None:
        return result.structured_content.get("result", result.structured_content)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


async def main() -> None:
    async with Client(mcp) as client:
        tools = (await client.list_tools()).tools
        show("tools", [t.name for t in tools])
        show("resources", [str(r.uri) for r in (await client.list_resources()).resources])

        show("recall://documents", (await client.read_resource("recall://documents")).contents[0].text)

        show("search_notes('scheduling')", payload(await client.call_tool("search_notes", {"query": "scheduling", "limit": 2})))
        show("generate_revision_checklist('threads')", payload(await client.call_tool("generate_revision_checklist", {"topic": "threads and processes", "items": 5})))
        show("explain_topic('round robin')", payload(await client.call_tool("explain_topic", {"topic": "round robin scheduling"})))

        # Validation, and a topic the material does not cover.
        show("generate_revision_checklist('ab')", payload(await client.call_tool("generate_revision_checklist", {"topic": "ab"})))
        show("generate_revision_checklist(items=99)", payload(await client.call_tool("generate_revision_checklist", {"topic": "threads", "items": 99})))
        show("explain_topic('the rules of cricket')", payload(await client.call_tool("explain_topic", {"topic": "the rules of cricket"})))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
