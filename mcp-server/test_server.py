"""The MCP server, against a fake Recall API.

No network and no model: an httpx MockTransport answers as the API would, so
these test the tool contracts — validation, the shape of the output, and what
happens when the API says no.
"""

from __future__ import annotations

import json

import httpx
import pytest

from mcp import Client
from recall_client import RecallClient
from server import mcp, use_client

CHECKLIST_RESPONSE = {
    "session_id": "sess-1",
    "kind": "checklist",
    "topic": "threads",
    "model": "llama3.2:3b",
    "created_at": "2026-09-10T10:00:00Z",
    "sources": [
        {"index": 1, "chunk_id": "c1", "document_id": "d1", "document_title": "Operating systems",
         "position": 1, "text": "A thread is a unit of execution…", "score": 0.81},
    ],
    "checklist": {
        "topic": "threads",
        "items": [
            {"step": "Recall what a thread shares with its process", "why": "the definition comes first", "source_index": 1},
            {"step": "Explain out loud why threads are cheaper than processes", "why": "tests understanding, not recall", "source_index": None},
        ],
    },
}

EXPLAIN_RESPONSE = {
    "session_id": "sess-2",
    "kind": "explain",
    "topic": "round robin",
    "model": "llama3.2:3b",
    "created_at": "2026-09-10T10:00:00Z",
    "sources": CHECKLIST_RESPONSE["sources"],
    "explanation": {"topic": "round robin", "text": "Each thread gets a quantum [1].", "grounded": True, "citations": [1]},
}


def fake_api(handler) -> RecallClient:
    return RecallClient(
        "http://recall.test", "demo@recall.study", "password", transport=httpx.MockTransport(handler)
    )


def ok(payload) -> httpx.Response:
    return httpx.Response(200, json=payload)


def default_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/auth/token":
        return ok({"access_token": "a-token", "token_type": "bearer", "expires_in": 3600})
    if request.url.path == "/study/checklist":
        return ok(CHECKLIST_RESPONSE)
    if request.url.path == "/study/explain":
        return ok(EXPLAIN_RESPONSE)
    if request.url.path == "/documents/search":
        return ok([{"chunk_id": "c1", "document_id": "d1", "document_title": "Operating systems",
                    "position": 2, "text": "Round robin gives each thread a quantum." * 40, "score": 0.77}])
    if request.url.path == "/documents":
        return ok([{"id": "d1", "title": "Operating systems", "filename": "os.md", "media_type": "text/markdown",
                    "size_bytes": 100, "chunk_count": 5, "created_at": "2026-09-01T09:00:00Z"}])
    return httpx.Response(404, json={"detail": "not found"})


@pytest.fixture(autouse=True)
def api():
    use_client(fake_api(default_handler))
    yield


def payload(result):
    if result.structured_content is not None:
        return result.structured_content.get("result", result.structured_content)
    return json.loads("\n".join(getattr(c, "text", "") for c in result.content))


def text(result) -> str:
    return "\n".join(getattr(c, "text", "") for c in result.content)


class TestDiscovery:
    async def test_the_required_tool_is_there_and_described(self):
        async with Client(mcp) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}

        assert "generate_revision_checklist" in tools
        assert "revision checklist" in tools["generate_revision_checklist"].description.lower()
        assert {"topic", "items"} <= set(tools["generate_revision_checklist"].input_schema["properties"])

    async def test_nothing_here_writes(self):
        async with Client(mcp) as client:
            tools = (await client.list_tools()).tools
        assert all(t.annotations and t.annotations.read_only_hint for t in tools)

    async def test_the_document_list_is_a_resource(self):
        async with Client(mcp) as client:
            uris = {str(r.uri) for r in (await client.list_resources()).resources}
            body = (await client.read_resource("recall://documents")).contents[0].text
        assert "recall://documents" in uris
        assert json.loads(body)[0]["title"] == "Operating systems"


class TestChecklist:
    async def test_returns_numbered_steps_with_their_sources(self):
        async with Client(mcp) as client:
            result = payload(await client.call_tool("generate_revision_checklist", {"topic": "threads", "items": 5}))

        assert result["topic"] == "threads"
        assert [i["n"] for i in result["items"]] == [1, 2]
        assert result["items"][0]["step"].startswith("Recall what a thread shares")
        assert result["items"][0]["source"] == "Operating systems, part 2"
        assert result["items"][1]["source"] is None  # the model did not say, and it is not invented
        assert result["based_on"] == ["Operating systems"]
        assert result["saved_as"] == "sess-1"

    async def test_the_arguments_reach_the_api(self):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/study/checklist":
                seen.update(json.loads(request.content))
            return default_handler(request)

        use_client(fake_api(handler))
        async with Client(mcp) as client:
            await client.call_tool("generate_revision_checklist", {"topic": "  threads and processes  ", "items": 4})
        assert seen == {"topic": "threads and processes", "items": 4}

    @pytest.mark.parametrize(
        "arguments, message",
        [
            ({"topic": "ab"}, "at least 3 characters"),
            ({"topic": "   "}, "at least 3 characters"),
            ({"topic": "x" * 501}, "500 characters"),
            ({"topic": "threads", "items": 0}, "between 1 and 12"),
            ({"topic": "threads", "items": 99}, "between 1 and 12"),
            # A non-integer is caught by the schema the SDK generates from the
            # signature, before the function runs. Different message, same refusal.
            ({"topic": "threads", "items": "six"}, "items"),
        ],
    )
    async def test_bad_arguments_are_refused_before_the_api_is_called(self, arguments, message):
        called = False

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal called
            if request.url.path != "/auth/token":
                called = True
            return default_handler(request)

        use_client(fake_api(handler))
        async with Client(mcp) as client:
            result = await client.call_tool("generate_revision_checklist", arguments)

        assert result.is_error
        assert message in text(result)
        assert called is False


class TestOtherTools:
    async def test_search_returns_trimmed_passages(self):
        async with Client(mcp) as client:
            hits = payload(await client.call_tool("search_notes", {"query": "scheduling", "limit": 2}))

        assert hits[0]["document"] == "Operating systems"
        assert hits[0]["passage"] == 3  # position 2, shown one-based
        assert len(hits[0]["text"]) <= 600

    async def test_explain_reports_which_passages_it_used(self):
        async with Client(mcp) as client:
            result = payload(await client.call_tool("explain_topic", {"topic": "round robin scheduling"}))

        assert result["grounded"] is True
        assert result["cited_passages"] == ["Operating systems, part 2"]

    async def test_an_unknown_level_is_refused(self):
        async with Client(mcp) as client:
            result = await client.call_tool("explain_topic", {"topic": "round robin", "level": "expert"})
        assert result.is_error and "beginner" in text(result)


class TestApiFailures:
    async def test_the_apis_own_sentence_is_passed_through(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/study/checklist":
                return httpx.Response(422, json={"detail": "Nothing in your material covers that closely enough."})
            return default_handler(request)

        use_client(fake_api(handler))
        async with Client(mcp) as client:
            result = await client.call_tool("generate_revision_checklist", {"topic": "the rules of cricket"})

        assert result.is_error
        assert "Nothing in your material" in text(result)

    async def test_an_unreachable_api_says_so(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        use_client(fake_api(handler))
        async with Client(mcp) as client:
            result = await client.call_tool("search_notes", {"query": "scheduling"})

        assert result.is_error
        assert "Is it running?" in text(result)

    async def test_an_expired_token_is_replaced_once_and_the_call_retried(self):
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            if request.url.path == "/study/checklist" and calls.count("/study/checklist") == 1:
                return httpx.Response(401, json={"detail": "Not signed in."})
            return default_handler(request)

        use_client(fake_api(handler))
        async with Client(mcp) as client:
            result = payload(await client.call_tool("generate_revision_checklist", {"topic": "threads"}))

        assert result["saved_as"] == "sess-1"
        assert calls.count("/auth/token") == 2  # signed in again rather than failing

    async def test_missing_credentials_are_explained_not_guessed(self, monkeypatch):
        for name in ("RECALL_EMAIL", "RECALL_PASSWORD", "RECALL_TOKEN"):
            monkeypatch.delenv(name, raising=False)
        use_client(RecallClient("http://recall.test", "", "", transport=httpx.MockTransport(default_handler)))

        async with Client(mcp) as client:
            result = await client.call_tool("search_notes", {"query": "scheduling"})

        assert result.is_error
        assert "RECALL_EMAIL" in text(result)


class TestSecrets:
    async def test_no_tool_takes_a_credential_as_an_argument(self):
        async with Client(mcp) as client:
            tools = (await client.list_tools()).tools
        for tool in tools:
            names = set(tool.input_schema.get("properties", {}))
            assert not names & {"password", "token", "api_key", "secret", "email"}

    async def test_no_result_carries_one(self):
        async with Client(mcp) as client:
            result = await client.call_tool("generate_revision_checklist", {"topic": "threads"})
        assert "password" not in text(result).lower()
        assert "a-token" not in text(result)
