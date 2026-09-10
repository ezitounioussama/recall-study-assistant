"""The study history: what gets recorded, and who can read it.

The isolation tests are the point of the file. Everything else in the
application already scopes by user; history is where a leak would be most
personal, so it is checked from both doors — cookie and bearer token.
"""

from __future__ import annotations

import json

import pytest

from app.llm import ScriptedChat, get_chat_model
from app.main import app
from tests.conftest import register
from tests.test_documents import BIOLOGY, upload


def data(response):
    """The JSON body, so the assertions below read as what they check."""
    return response.json()

CARDS_JSON = json.dumps(
    {"cards": [{"front": "What do mitochondria produce?", "back": "ATP."}, {"front": "Where?", "back": "The matrix."}]}
)


@pytest.fixture
def answering_model():
    scripted = ScriptedChat("Mitochondria produce ATP [1].")
    app.dependency_overrides[get_chat_model] = lambda: scripted
    yield scripted
    app.dependency_overrides.pop(get_chat_model, None)


@pytest.fixture
def card_writing_model():
    scripted = ScriptedChat(CARDS_JSON)
    app.dependency_overrides[get_chat_model] = lambda: scripted
    yield scripted
    app.dependency_overrides.pop(get_chat_model, None)


async def ask(client, question: str, **extra) -> None:
    """Drain the chat stream, which is what triggers the recording."""
    async with client.stream("POST", "/chat", json={"question": question, **extra}) as response:
        assert response.status_code == 200
        async for _ in response.aiter_lines():
            pass


class TestRecording:
    async def test_an_answer_becomes_a_session_with_its_citations(self, signed_in, answering_model):
        await upload(signed_in, content=BIOLOGY)
        await ask(signed_in, "what do mitochondria produce")

        sessions = data(await signed_in.get("/study/history"))
        assert len(sessions) == 1
        assert sessions[0]["kind"] == "chat"
        assert sessions[0]["topic"] == "what do mitochondria produce"

        detail = data(await signed_in.get(f"/study/history/{sessions[0]['id']}"))
        content = detail["contents"][0]
        assert content["kind"] == "answer"
        assert content["text"] == "Mitochondria produce ATP [1]."
        assert content["grounded"] is True
        assert content["data"]["citations"] == [1]
        assert content["data"]["sources"][0]["document_title"] == "notes"

    async def test_the_passage_text_is_referenced_not_copied(self, signed_in, answering_model):
        """The chunk rows already hold it; duplicating it into every entry would not scale."""
        await upload(signed_in, content=BIOLOGY)
        await ask(signed_in, "what do mitochondria produce")

        session_id = data(await signed_in.get("/study/history"))[0]["id"]
        source = data(await signed_in.get(f"/study/history/{session_id}"))["contents"][0]["data"]["sources"][0]
        assert set(source) == {"index", "chunk_id", "document_id", "document_title", "position", "score"}

    async def test_a_refusal_is_recorded_as_ungrounded(self, signed_in, answering_model):
        await ask(signed_in, "who painted the Mona Lisa")

        session_id = data(await signed_in.get("/study/history"))[0]["id"]
        content = data(await signed_in.get(f"/study/history/{session_id}"))["contents"][0]
        assert content["grounded"] is False
        assert content["text"] == "I can't find that in your notes."
        assert answering_model.calls == []  # and no model was asked

    async def test_generating_cards_records_one_session_for_the_batch(self, signed_in, card_writing_model):
        document = data(await upload(signed_in, title="Cell biology"))
        await signed_in.post("/cards/generate", json={"document_id": document["id"], "per_chunk": 2})

        sessions = data(await signed_in.get("/study/history"))
        assert len(sessions) == 1
        assert sessions[0]["kind"] == "flashcards"
        assert sessions[0]["topic"] == "Cell biology"
        assert sessions[0]["document_id"] == document["id"]

        content = data(await signed_in.get(f"/study/history/{sessions[0]['id']}"))["contents"][0]
        assert len(content["data"]) == 2
        assert content["data"][0]["front"] == "What do mitochondria produce?"

    async def test_the_model_that_wrote_it_is_recorded(self, signed_in, answering_model):
        await upload(signed_in, content=BIOLOGY)
        await ask(signed_in, "mitochondria")
        assert data(await signed_in.get("/study/history"))[0]["model"]

    async def test_deleting_the_document_keeps_the_session(self, signed_in, card_writing_model):
        document = data(await upload(signed_in))
        await signed_in.post("/cards/generate", json={"document_id": document["id"]})
        assert (await signed_in.delete(f"/documents/{document['id']}")).status_code == 204

        sessions = data(await signed_in.get("/study/history"))
        assert len(sessions) == 1
        assert sessions[0]["document_id"] is None  # the link goes, the record stays


class TestReading:
    async def test_newest_first(self, signed_in, answering_model):
        await upload(signed_in, content=BIOLOGY)
        for question in ("first question", "second question", "third question"):
            await ask(signed_in, question)

        topics = [s["topic"] for s in data(await signed_in.get("/study/history"))]
        assert topics == ["third question", "second question", "first question"]

    async def test_filtering_by_kind(self, signed_in, card_writing_model):
        document = data(await upload(signed_in))
        await signed_in.post("/cards/generate", json={"document_id": document["id"]})
        await ask(signed_in, "a question")

        assert len(data(await signed_in.get("/study/history"))) == 2
        assert [s["kind"] for s in data(await signed_in.get("/study/history?kind=flashcards"))] == ["flashcards"]
        assert [s["kind"] for s in data(await signed_in.get("/study/history?kind=chat"))] == ["chat"]

    @pytest.mark.parametrize("query", ["limit=0", "limit=500", "kind=nonsense"])
    async def test_bad_query_parameters_are_422(self, signed_in, query):
        assert (await signed_in.get(f"/study/history?{query}")).status_code == 422

    async def test_an_empty_history_is_an_empty_list(self, signed_in):
        assert data(await signed_in.get("/study/history")) == []

    async def test_a_session_that_does_not_exist_is_404(self, signed_in):
        assert (await signed_in.get("/study/history/no-such-id")).status_code == 404


class TestIsolation:
    """One user cannot reach another user's history. The whole point of phase 4."""

    async def test_another_users_session_is_invisible_and_unreachable(self, client, answering_model):
        await register(client, email="alice@x.com")
        await upload(client, content=BIOLOGY)
        await ask(client, "alice's private question")
        alice_session = data(await client.get("/study/history"))[0]["id"]

        client.cookies.clear()
        await register(client, email="bob@x.com")

        assert data(await client.get("/study/history")) == []
        response = await client.get(f"/study/history/{alice_session}")
        assert response.status_code == 404
        assert "alice" not in response.text.lower()

    async def test_isolation_holds_for_bearer_tokens_too(self, client, answering_model):
        await register(client, email="alice@x.com")
        await upload(client, content=BIOLOGY)
        await ask(client, "alice's private question")
        alice_session = data(await client.get("/study/history"))[0]["id"]

        await register(client, email="bob@x.com")
        bob_token = (
            await client.post("/auth/token", data={"username": "bob@x.com", "password": "correct-horse-battery"})
        ).json()["access_token"]
        client.cookies.clear()
        headers = {"Authorization": f"Bearer {bob_token}"}

        assert data(await client.get("/study/history", headers=headers)) == []
        assert (await client.get(f"/study/history/{alice_session}", headers=headers)).status_code == 404

    async def test_history_needs_a_signed_in_user(self, client):
        client.cookies.clear()
        assert (await client.get("/study/history")).status_code == 401
        assert (await client.get("/study/history/anything")).status_code == 401
