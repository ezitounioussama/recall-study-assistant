"""Chat over SSE.

The model is scripted, so what is under test is the router: what it retrieves,
what it sends the model, how it relays the stream, and — most of all — that a
question the notes do not cover is refused without asking the model.
"""

from __future__ import annotations

import json

import pytest

from app.llm import ScriptedChat, get_chat_model
from app.main import app
from app.routers.chat import HISTORY_TURNS, REFUSAL
from tests.conftest import register
from tests.test_documents import BIOLOGY, HISTORY, upload


@pytest.fixture
def model():
    scripted = ScriptedChat("Mitochondria produce ATP [1].")
    app.dependency_overrides[get_chat_model] = lambda: scripted
    yield scripted
    app.dependency_overrides.pop(get_chat_model, None)


async def ask(client, question, **extra):
    """POST /chat and collect the SSE stream as (event, data) pairs."""
    events: list[tuple[str, object]] = []
    async with client.stream("POST", "/chat", json={"question": question, **extra}) as response:
        assert response.status_code == 200, await response.aread()
        assert response.headers["content-type"].startswith("text/event-stream")
        event = None
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                events.append((event, json.loads(line[len("data: ") :])))
    return events


def by_type(events, kind):
    return [data for event, data in events if event == kind]


class TestRefusal:
    async def test_no_relevant_notes_means_no_model_call(self, signed_in, model):
        await upload(signed_in, content=BIOLOGY)
        events = await ask(signed_in, "zebra quantum tango xylophone")

        assert by_type(events, "sources") == [[]]
        assert by_type(events, "done") == [{"answer": REFUSAL, "grounded": False, "citations": []}]
        assert model.calls == [], "the model must not be consulted for an ungrounded question"

    async def test_empty_library_is_refused(self, signed_in, model):
        events = await ask(signed_in, "what do mitochondria produce")
        assert by_type(events, "done")[0]["grounded"] is False
        assert model.calls == []

    async def test_a_model_that_refuses_is_marked_ungrounded(self, signed_in):
        scripted = ScriptedChat(f"Sorry. {REFUSAL}")
        app.dependency_overrides[get_chat_model] = lambda: scripted
        try:
            await upload(signed_in, content=BIOLOGY)
            events = await ask(signed_in, "mitochondria ATP")
            assert by_type(events, "done")[0]["grounded"] is False
        finally:
            app.dependency_overrides.pop(get_chat_model, None)


class TestGroundedAnswer:
    async def test_sources_arrive_first_then_tokens_then_done(self, signed_in, model):
        await upload(signed_in, name="bio.md", content=BIOLOGY)
        events = await ask(signed_in, "what do mitochondria produce")

        kinds = [event for event, _ in events]
        assert kinds[0] == "sources"
        assert kinds[-1] == "done"
        assert all(k == "token" for k in kinds[1:-1])

        sources = by_type(events, "sources")[0]
        assert sources[0]["index"] == 1
        assert sources[0]["document_title"] == "bio"
        assert "Mitochondria" in sources[0]["text"]

        tokens = "".join(t["text"] for t in by_type(events, "token"))
        done = by_type(events, "done")[0]
        assert tokens == done["answer"] == "Mitochondria produce ATP [1]."
        assert done["grounded"] is True
        assert done["citations"] == [1]

    async def test_invented_citations_are_dropped(self, signed_in):
        scripted = ScriptedChat("ATP [1]. Also DNA [7].")
        app.dependency_overrides[get_chat_model] = lambda: scripted
        try:
            await upload(signed_in, content=BIOLOGY)
            events = await ask(signed_in, "mitochondria")
            assert by_type(events, "done")[0]["citations"] == [1]
        finally:
            app.dependency_overrides.pop(get_chat_model, None)

    async def test_the_model_sees_the_passages_and_the_question(self, signed_in, model):
        await upload(signed_in, content=BIOLOGY)
        await ask(signed_in, "what do mitochondria produce")

        system, messages = model.calls[0]
        assert "[1]" in system
        assert "oxidative phosphorylation" in system
        assert REFUSAL in system
        assert messages[-1] == {"role": "user", "content": "what do mitochondria produce"}

    async def test_history_is_forwarded_but_bounded(self, signed_in, model):
        await upload(signed_in, content=BIOLOGY)
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i}"}
            for i in range(20)
        ]
        await ask(signed_in, "mitochondria", history=history)

        _, messages = model.calls[0]
        assert len(messages) == HISTORY_TURNS + 1
        assert messages[0]["content"] == f"turn {20 - HISTORY_TURNS}"

    async def test_a_follow_up_retrieves_with_the_previous_question(self, signed_in, model):
        """"What about them?" alone matches nothing; with the last user turn it finds the passage."""
        await upload(signed_in, content=BIOLOGY)
        cold = await ask(signed_in, "what about them?")
        assert by_type(cold, "sources") == [[]]

        warm = await ask(
            signed_in,
            "what about them?",
            history=[{"role": "user", "content": "tell me about mitochondria, ATP and oxidative phosphorylation"}, {"role": "assistant", "content": "They make ATP."}],
        )
        assert by_type(warm, "sources")[0], "the previous question should carry the topic into retrieval"
        _, messages = model.calls[-1]
        assert messages[-1]["content"] == "what about them?", "the model still sees the question as asked"

    async def test_document_filter_restricts_sources(self, signed_in, model):
        bio = (await upload(signed_in, name="bio.md", content=BIOLOGY)).json()
        await upload(signed_in, name="hist.md", content=HISTORY)

        events = await ask(signed_in, "Westphalia treaty war", document_ids=[bio["id"]])
        titles = {s["document_title"] for s in by_type(events, "sources")[0]}
        assert titles <= {"bio"}


class TestSafety:
    async def test_requires_sign_in(self, client, model):
        response = await client.post("/chat", json={"question": "hi"})
        assert response.status_code == 401

    async def test_never_cites_another_users_notes(self, client, model):
        await register(client, email="alice@x.com")
        await upload(client, content=BIOLOGY)
        client.cookies.clear()
        await register(client, email="bob@x.com")

        events = await ask(client, "what do mitochondria produce")
        assert by_type(events, "sources") == [[]]
        assert model.calls == []

    async def test_model_failure_is_an_error_event_not_a_500(self, signed_in):
        class Broken:
            async def stream(self, system, messages):
                raise ConnectionError("no ollama")
                yield  # pragma: no cover - makes this an async generator

        app.dependency_overrides[get_chat_model] = Broken
        try:
            await upload(signed_in, content=BIOLOGY)
            events = await ask(signed_in, "mitochondria")
            assert [e for e, _ in events] == ["sources", "error"]
            assert "Ollama" in by_type(events, "error")[0]["detail"]
        finally:
            app.dependency_overrides.pop(get_chat_model, None)

    async def test_question_length_is_bounded(self, signed_in, model):
        response = await signed_in.post("/chat", json={"question": "x" * 2001})
        assert response.status_code == 422
