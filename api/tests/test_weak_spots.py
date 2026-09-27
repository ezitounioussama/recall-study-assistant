"""Weak spots: which passages this student keeps forgetting, and a quiz on them.

The ranking is tested as a pure function first, because that is where the
judgement lives. The routes are then tested for what they add: grouping by
passage, ownership, and refusing to invent weak spots from no history.
"""

from __future__ import annotations

import json

import pytest

from app.llm import ScriptedChat, get_chat_model
from app.main import app
from app.services.weak_spots import Evidence, excerpt, is_weak, rank, reason, weakness
from tests.conftest import register
from tests.test_cards import CARDS_JSON, make_card
from tests.test_documents import upload
from tests.test_study import QUIZ_JSON


def evidence(key="a", *, reviews=0, forgotten=0, recall=(), difficulty=()):
    return Evidence(
        key=key,
        reviews=reviews,
        forgotten=forgotten,
        retrievabilities=list(recall),
        difficulties=list(difficulty),
    )


class TestRanking:
    def test_never_reviewed_is_untested_not_weak(self):
        assert not is_weak(evidence(reviews=0, recall=[0.1]))

    def test_forgotten_once_is_weak(self):
        assert is_weak(evidence(reviews=3, forgotten=1, recall=[0.99]))

    def test_remembered_and_fresh_is_not_weak(self):
        assert not is_weak(evidence(reviews=2, forgotten=0, recall=[0.97]))

    def test_remembered_but_fading_is_weak(self):
        assert is_weak(evidence(reviews=2, forgotten=0, recall=[0.6]))

    def test_forgotten_more_often_ranks_first(self):
        often = evidence("often", reviews=4, forgotten=3, recall=[0.9])
        once = evidence("once", reviews=4, forgotten=1, recall=[0.9])
        assert [e.key for e in rank([once, often], limit=5)] == ["often", "once"]

    def test_weakness_stays_between_zero_and_one(self):
        worst = evidence(reviews=5, forgotten=5, recall=[0.0], difficulty=[10.0])
        best = evidence(reviews=5, forgotten=0, recall=[1.0], difficulty=[1.0])
        assert weakness(worst) == 1.0
        assert 0.0 <= weakness(best) < 0.1

    def test_limit_and_a_stable_order_on_ties(self):
        tied = [evidence(k, reviews=2, forgotten=1, recall=[0.9]) for k in "cab"]
        assert [e.key for e in rank(tied, limit=2)] == ["a", "b"]

    def test_the_reason_says_what_happened(self):
        assert reason(evidence(reviews=3, forgotten=2)) == "Forgotten 2 of 3 reviews"
        assert reason(evidence(reviews=1, forgotten=1)) == "Forgotten 1 of 1 review"
        assert reason(evidence(reviews=2, recall=[0.62])) == "Recall has faded to 62%"


class TestExcerpt:
    def test_a_fragment_left_by_the_overlap_is_dropped(self):
        text = "address space; a thread is cheap. Round robin gives each thread a quantum of time."
        assert excerpt(text) == "Round robin gives each thread a quantum of time."

    def test_heading_marks_are_removed(self):
        assert excerpt("# Operating systems\n\n## 1. Processes\nA process runs.") == "Operating systems 1. Processes A process runs."

    def test_a_long_passage_is_cut_on_a_word(self):
        cut = excerpt("Mitochondria " * 40, limit=50)
        assert cut.endswith("Mitochondria…")
        assert len(cut) <= 51


@pytest.fixture
def model():
    scripted = ScriptedChat(CARDS_JSON)
    app.dependency_overrides[get_chat_model] = lambda: scripted
    yield scripted
    app.dependency_overrides.pop(get_chat_model, None)


class Quizzer:
    """Writes QUIZ_JSON, then answers the key check with a fixed choice number.

    QUIZ_JSON's correct choice, "ATP", is the first, so `key=1` agrees with it
    and any other number disagrees.
    """

    model = "scripted"
    timeout = 0.0

    def __init__(self, key: object, quiz: str = QUIZ_JSON) -> None:
        self.key = key
        self.quiz = quiz
        self.calls: list[tuple[str, list[dict]]] = []

    async def complete(self, system, messages, *, json_mode: bool = False) -> str:
        self.calls.append((system, messages))
        if system.startswith("You check quiz questions"):
            return json.dumps({"answer": self.key})
        return self.quiz


def use(fake):
    app.dependency_overrides[get_chat_model] = lambda: fake
    return fake


async def generated_cards(client):
    doc = (await upload(client)).json()
    response = await client.post("/cards/generate", json={"document_id": doc["id"]})
    assert response.status_code == 201, response.text
    return doc, response.json()


async def rate(client, card, *ratings):
    for rating in ratings:
        assert (await client.post(f"/cards/{card['id']}/review", json={"rating": rating})).status_code == 200


class TestWeakSpotsRoute:
    async def test_no_history_means_no_weak_spots(self, signed_in, model):
        await generated_cards(signed_in)
        response = await signed_in.get("/cards/weak-spots")
        assert response.status_code == 200
        assert response.json() == []

    async def test_a_forgotten_card_names_its_passage(self, signed_in, model):
        doc, cards = await generated_cards(signed_in)
        forgotten = cards[0]
        await rate(signed_in, forgotten, 1, 1)

        spots = (await signed_in.get("/cards/weak-spots")).json()
        top = spots[0]
        assert top["chunk_id"] == forgotten["chunk_id"]
        assert top["document_id"] == doc["id"]
        assert top["document_title"] == doc["title"]
        assert top["forgotten"] == 2
        assert top["reason"].startswith("Forgotten 2 of")
        assert top["excerpt"]
        # Every card from that passage is listed, not only the forgotten one.
        siblings = {c["id"] for c in cards if c["chunk_id"] == forgotten["chunk_id"]}
        assert {c["id"] for c in top["cards"]} == siblings

    async def test_remembered_easily_is_not_a_weak_spot(self, signed_in, model):
        _, cards = await generated_cards(signed_in)
        for card in cards:
            await rate(signed_in, card, 4)
        assert (await signed_in.get("/cards/weak-spots")).json() == []

    async def test_a_hand_written_card_stands_alone(self, signed_in):
        card = await make_card(signed_in, front="Capital of Morocco?", back="Rabat.")
        await rate(signed_in, card, 1)
        spots = (await signed_in.get("/cards/weak-spots")).json()
        assert len(spots) == 1
        assert spots[0]["chunk_id"] is None
        assert spots[0]["excerpt"] is None
        assert [c["id"] for c in spots[0]["cards"]] == [card["id"]]

    async def test_another_users_history_is_invisible(self, client, model):
        await register(client, email="alice@x.com")
        _, cards = await generated_cards(client)
        await rate(client, cards[0], 1)
        client.cookies.clear()
        await register(client, email="bob@x.com")
        assert (await client.get("/cards/weak-spots")).json() == []

    async def test_limit_is_validated(self, signed_in):
        assert (await signed_in.get("/cards/weak-spots?limit=0")).status_code == 422
        assert (await signed_in.get("/cards/weak-spots?limit=11")).status_code == 422

    async def test_requires_sign_in(self, client):
        assert (await client.get("/cards/weak-spots")).status_code == 401


class TestWeakSpotQuiz:
    async def test_the_quiz_is_built_only_from_weak_passages(self, signed_in, model):
        _, cards = await generated_cards(signed_in)
        await rate(signed_in, cards[0], 1)

        quizzer = use(Quizzer(key=1))
        response = await signed_in.post("/study/weak-spots/quiz", json={"count": 1})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["topic"] == "Your weak spots"
        assert [s["chunk_id"] for s in body["sources"]] == [cards[0]["chunk_id"]]
        question = body["quiz"]["questions"][0]
        assert question["choices"][question["answer_index"]] == "ATP"

        # The writer saw the weak passage, and only that passage.
        system, messages = quizzer.calls[0]
        assert body["sources"][0]["text"] in system + messages[0]["content"]

        history = (await signed_in.get("/study/history?kind=quiz")).json()
        assert any(item["id"] == body["session_id"] for item in history)

    async def test_the_key_check_sees_the_passage_but_not_the_key(self, signed_in, model):
        _, cards = await generated_cards(signed_in)
        await rate(signed_in, cards[0], 1)
        quizzer = use(Quizzer(key=1))
        body = (await signed_in.post("/study/weak-spots/quiz", json={"count": 1})).json()

        system, messages = quizzer.calls[1]
        assert system.startswith("You check quiz questions")
        content = messages[0]["content"]
        assert body["sources"][0]["text"] in content
        assert "1. ATP" in content
        assert "oxidative phosphorylation [1]" not in content  # the explanation gives the answer away

    async def test_a_question_the_check_disagrees_with_is_dropped(self, signed_in, model):
        _, cards = await generated_cards(signed_in)
        await rate(signed_in, cards[0], 1)
        use(Quizzer(key=2))
        response = await signed_in.post("/study/weak-spots/quiz", json={"count": 1})
        assert response.status_code == 502
        assert "answer check" in response.json()["detail"]

    @pytest.mark.parametrize("key", [0, "two", None])
    async def test_an_unsure_or_unreadable_check_drops_the_question(self, signed_in, model, key):
        _, cards = await generated_cards(signed_in)
        await rate(signed_in, cards[0], 1)
        use(Quizzer(key=key))
        assert (await signed_in.post("/study/weak-spots/quiz", json={"count": 1})).status_code == 502

    async def test_two_choices_saying_the_same_thing_are_dropped_before_the_check(self, signed_in, model):
        _, cards = await generated_cards(signed_in)
        await rate(signed_in, cards[0], 1)
        twins = json.dumps(
            {
                "questions": [
                    {
                        "question": "How much cheaper is a thread to create?",
                        "choices": ["An order of magnitude", "One order of magnitude", "Two orders", "The same"],
                        "answer": "An order of magnitude",
                        "explanation": "Roughly an order of magnitude [1].",
                        "source_index": 1,
                    }
                ]
            }
        )
        quizzer = use(Quizzer(key=1, quiz=twins))
        assert (await signed_in.post("/study/weak-spots/quiz", json={"count": 1})).status_code == 502
        assert len(quizzer.calls) == 1  # the checker was never asked

    async def test_no_history_is_422_before_the_model_is_asked(self, signed_in, model):
        await generated_cards(signed_in)
        quizzer = use(Quizzer(key=1))
        response = await signed_in.post("/study/weak-spots/quiz", json={})
        assert response.status_code == 422
        assert "Review some cards first" in response.json()["detail"]
        assert quizzer.calls == []

    async def test_hand_written_cards_alone_cannot_be_quizzed(self, signed_in):
        card = await make_card(signed_in)
        await rate(signed_in, card, 1)
        assert (await signed_in.post("/study/weak-spots/quiz", json={})).status_code == 422

    async def test_an_unusable_reply_is_502(self, signed_in, model):
        _, cards = await generated_cards(signed_in)
        await rate(signed_in, cards[0], 1)
        use(Quizzer(key=1, quiz=json.dumps({"questions": []})))
        assert (await signed_in.post("/study/weak-spots/quiz", json={})).status_code == 502

    async def test_count_is_validated(self, signed_in):
        assert (await signed_in.post("/study/weak-spots/quiz", json={"count": 0})).status_code == 422
        assert (await signed_in.post("/study/weak-spots/quiz", json={"count": 11})).status_code == 422
