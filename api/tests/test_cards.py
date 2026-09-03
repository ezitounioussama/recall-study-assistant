"""Cards, generation, and the review loop through the API."""

from __future__ import annotations

import datetime as dt
import json

import pytest

from app.llm import ScriptedChat, get_chat_model
from app.main import app
from app.routers.cards import parse_cards
from tests.conftest import register
from tests.test_documents import BIOLOGY, upload

CARDS_JSON = json.dumps(
    {
        "cards": [
            {"front": "What do mitochondria produce?", "back": "ATP, via oxidative phosphorylation."},
            {"front": "Where do light-dependent reactions occur?", "back": "In the thylakoid membranes."},
            {"front": "What pigment captures light?", "back": "Chlorophyll."},
        ]
    }
)


@pytest.fixture
def model():
    scripted = ScriptedChat(CARDS_JSON)
    app.dependency_overrides[get_chat_model] = lambda: scripted
    yield scripted
    app.dependency_overrides.pop(get_chat_model, None)


async def make_card(client, front="Q?", back="A.", **extra):
    response = await client.post("/cards", json={"front": front, "back": back, **extra})
    assert response.status_code == 201, response.text
    return response.json()


class TestCreate:
    async def test_a_new_card_is_due_now_in_learning(self, signed_in):
        card = await make_card(signed_in)
        assert card["state"] == "learning"
        assert card["stability"] is None
        assert card["retrievability"] == 1.0
        assert dt.datetime.fromisoformat(card["due"]) <= dt.datetime.now(dt.timezone.utc)

    async def test_linking_to_someone_elses_document_is_404(self, client):
        await register(client, email="alice@x.com")
        doc = (await upload(client)).json()
        client.cookies.clear()
        await register(client, email="bob@x.com")
        response = await client.post("/cards", json={"front": "Q", "back": "A", "document_id": doc["id"]})
        assert response.status_code == 404


class TestGenerate:
    async def test_cards_come_from_chunks_and_point_back_at_them(self, signed_in, model):
        doc = (await upload(signed_in)).json()
        response = await signed_in.post("/cards/generate", json={"document_id": doc["id"]})
        assert response.status_code == 201
        cards = response.json()
        assert len(cards) == 3 * doc["chunk_count"]
        assert {c["document_id"] for c in cards} == {doc["id"]}
        assert all(c["chunk_id"] for c in cards)

        system, messages = model.calls[0]
        assert "exactly 3 flashcards" in system
        assert "Mitochondria" in messages[0]["content"]

    async def test_generating_twice_does_not_double_the_deck(self, signed_in, model):
        doc = (await upload(signed_in)).json()
        await signed_in.post("/cards/generate", json={"document_id": doc["id"]})
        again = await signed_in.post("/cards/generate", json={"document_id": doc["id"]})
        assert again.status_code == 201
        assert again.json() == []
        assert len((await signed_in.get("/cards")).json()) == 3

    async def test_unusable_model_output_is_502(self, signed_in):
        app.dependency_overrides[get_chat_model] = lambda: ScriptedChat("I would rather not.")
        try:
            doc = (await upload(signed_in)).json()
            response = await signed_in.post("/cards/generate", json={"document_id": doc["id"]})
            assert response.status_code == 502
        finally:
            app.dependency_overrides.pop(get_chat_model, None)

    async def test_due_cards_carry_their_source_passage(self, signed_in, model):
        doc = (await upload(signed_in, title="Bio week 1")).json()
        await signed_in.post("/cards/generate", json={"document_id": doc["id"]})
        due = (await signed_in.get("/cards/due")).json()
        assert due[0]["source_title"] == "Bio week 1"
        assert "Mitochondria" in due[0]["source_text"]


class TestParseCards:
    def test_accepts_the_asked_for_shape(self):
        assert parse_cards(CARDS_JSON)[0][0] == "What do mitochondria produce?"

    def test_accepts_a_bare_list_wrapped_in_prose(self):
        text = 'Here you go:\n[{"front": "Q", "back": "A"}]\nHope that helps!'
        assert parse_cards(text) == [("Q", "A")]

    def test_drops_half_cards_and_garbage(self):
        text = '{"cards": [{"front": "Q"}, {"back": "A"}, "nope", {"front": "Q2", "back": "A2"}]}'
        assert parse_cards(text) == [("Q2", "A2")]

    def test_nothing_usable_is_an_empty_list(self):
        assert parse_cards("no json here") == []
        assert parse_cards('{"cards": "not a list"}') == []


class TestReview:
    async def test_good_walks_the_first_learning_step(self, signed_in):
        card = await make_card(signed_in)
        result = await signed_in.post(f"/cards/{card['id']}/review", json={"rating": 3})
        assert result.status_code == 200
        body = result.json()

        assert body["card"]["state"] == "learning"
        assert body["card"]["step"] == 1
        assert body["card"]["reps"] == 1
        assert body["card"]["stability"] is not None
        assert body["log"]["rating"] == 3
        assert body["log"]["state_before"] == "learning"
        assert body["log"]["scheduled_seconds"] == 600

    async def test_easy_graduates_to_review_days_out(self, signed_in):
        card = await make_card(signed_in)
        body = (await signed_in.post(f"/cards/{card['id']}/review", json={"rating": 4})).json()
        assert body["card"]["state"] == "review"
        assert body["log"]["scheduled_seconds"] >= 86400
        assert (await signed_in.get("/cards/due")).json() == []

    async def test_a_lapse_is_counted_only_from_review(self, signed_in):
        card = await make_card(signed_in)
        url = f"/cards/{card['id']}/review"
        assert (await signed_in.post(url, json={"rating": 1})).json()["card"]["lapses"] == 0
        await signed_in.post(url, json={"rating": 4})  # graduate
        lapsed = (await signed_in.post(url, json={"rating": 1})).json()["card"]
        assert lapsed["lapses"] == 1
        assert lapsed["state"] == "relearning"

    async def test_rating_outside_one_to_four_is_422(self, signed_in):
        card = await make_card(signed_in)
        assert (await signed_in.post(f"/cards/{card['id']}/review", json={"rating": 5})).status_code == 422
        assert (await signed_in.post(f"/cards/{card['id']}/review", json={"rating": 0})).status_code == 422

    async def test_due_preview_orders_the_four_buttons(self, signed_in):
        await make_card(signed_in)
        due = (await signed_in.get("/cards/due")).json()[0]
        p = due["preview"]
        assert p["again"] < p["hard"] < p["good"] < p["easy"]
        assert p["again"] == 60 and p["good"] == 600


class TestStats:
    async def test_counts_and_retention(self, signed_in):
        a = await make_card(signed_in, front="a")
        b = await make_card(signed_in, front="b")
        await signed_in.post(f"/cards/{a['id']}/review", json={"rating": 4})
        await signed_in.post(f"/cards/{b['id']}/review", json={"rating": 1})

        stats = (await signed_in.get("/cards/stats")).json()
        assert stats["total"] == 2
        assert stats["review"] == 1
        assert stats["learning"] == 1
        assert stats["due_now"] == 0  # b is due in a minute, a in days
        assert stats["reviewed_today"] == 2
        assert stats["retention_30d"] == 0.5
        assert stats["next_due"] is not None
        assert 0 < stats["mean_retrievability"] <= 1

    async def test_empty_deck(self, signed_in):
        stats = (await signed_in.get("/cards/stats")).json()
        assert stats["total"] == 0
        assert stats["retention_30d"] is None
        assert stats["next_due"] is None


class TestScopingAndDeletion:
    async def test_another_users_card_is_404(self, client):
        await register(client, email="alice@x.com")
        card = await make_card(client)
        client.cookies.clear()
        await register(client, email="bob@x.com")

        assert (await client.get(f"/cards/{card['id']}")).status_code == 404
        assert (await client.post(f"/cards/{card['id']}/review", json={"rating": 3})).status_code == 404
        assert (await client.delete(f"/cards/{card['id']}")).status_code == 404
        assert (await client.get("/cards/due")).json() == []

    async def test_deleting_a_document_keeps_the_cards(self, signed_in, model):
        doc = (await upload(signed_in)).json()
        await signed_in.post("/cards/generate", json={"document_id": doc["id"]})
        assert (await signed_in.delete(f"/documents/{doc['id']}")).status_code == 204

        cards = (await signed_in.get("/cards")).json()
        assert len(cards) == 3
        assert all(c["document_id"] is None and c["chunk_id"] is None for c in cards)
        assert (await signed_in.get("/cards/due")).json()[0]["source_text"] is None

    async def test_deleting_a_card_removes_it(self, signed_in):
        card = await make_card(signed_in)
        assert (await signed_in.delete(f"/cards/{card['id']}")).status_code == 204
        assert (await signed_in.get("/cards")).json() == []

    async def test_requires_sign_in(self, client):
        assert (await client.get("/cards/due")).status_code == 401
