"""The four study endpoints: what they return, what they save, and who can use them.

The model is scripted throughout. What is under test is the route — that it
retrieves from the right user's material, refuses rather than invents, saves
what it produced, and validates what it was asked for.
"""

from __future__ import annotations

import json

import pytest

from app.llm import get_chat_model
from app.main import app
from tests.conftest import register
from tests.test_documents import BIOLOGY, upload

# The hash embedder used by the tests matches on shared words, so a topic made
# of words the material never uses retrieves nothing.
UNRELATED = "zebra tango xylophone bassoon"

QUIZ_JSON = json.dumps(
    {
        "questions": [
            {
                "question": "What do mitochondria produce?",
                "choices": ["ATP", "Glucose", "Chlorophyll", "DNA"],
                "answer": "ATP",
                "explanation": "Mitochondria produce ATP through oxidative phosphorylation [1].",
                "source_index": 1,
            }
        ]
    }
)
SUMMARY_JSON = json.dumps(
    {"title": "Cell biology", "points": ["Mitochondria produce ATP [1].", "Chloroplasts capture light [1]."]}
)
CARDS_JSON = json.dumps({"cards": [{"front": "What produces ATP?", "back": "Mitochondria."}]})
CHECKLIST_JSON = json.dumps(
    {
        "items": [
            {"step": "Recall what mitochondria produce, without looking", "why": "the fact comes first", "source_index": 1},
            {"step": "Explain oxidative phosphorylation out loud", "why": "shows the mechanism is understood", "source_index": 1},
        ]
    }
)


class Scripted:
    """Returns a fixed reply, and records every call."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[tuple[str, list[dict]]] = []

    async def complete(self, system, messages, *, json_mode: bool = False) -> str:
        self.calls.append((system, messages))
        return self.reply

    async def stream(self, system, messages):
        self.calls.append((system, messages))
        yield self.reply


class Broken:
    async def complete(self, system, messages, *, json_mode: bool = False) -> str:
        raise ConnectionError("no ollama")

    async def stream(self, system, messages):
        raise ConnectionError("no ollama")
        yield  # pragma: no cover


class TooSlow:
    """A model that accepted the request and never answered."""

    model = "llama3.2:3b"
    timeout = 90.0

    async def complete(self, system, messages, *, json_mode: bool = False) -> str:
        import httpx

        raise httpx.ReadTimeout("timed out")

    async def stream(self, system, messages):
        import httpx

        raise httpx.ReadTimeout("timed out")
        yield  # pragma: no cover


def use(model) -> None:
    app.dependency_overrides[get_chat_model] = lambda: model


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_chat_model, None)


@pytest.fixture
async def with_material(signed_in):
    await upload(signed_in, content=BIOLOGY)
    return signed_in


def body(**extra) -> dict:
    return {"topic": "mitochondria and ATP", **extra}


# ---- 1. explain ----------------------------------------------------------------


class TestExplain:
    async def test_returns_a_cited_explanation_and_its_passages(self, with_material):
        use(Scripted("Mitochondria produce ATP [1]."))
        response = await with_material.post("/study/explain", json=body(level="advanced"))

        assert response.status_code == 200
        result = response.json()
        assert result["kind"] == "explain"
        assert result["explanation"]["text"] == "Mitochondria produce ATP [1]."
        assert result["explanation"]["grounded"] is True
        assert result["explanation"]["citations"] == [1]
        assert result["sources"][0]["index"] == 1
        assert result["model"]

    async def test_the_level_reaches_the_model(self, with_material):
        model = Scripted("…")
        use(model)
        await with_material.post("/study/explain", json=body(level="advanced"))
        assert "advanced level" in model.calls[0][1][0]["content"]

    async def test_material_that_does_not_cover_it_is_a_refusal_not_an_error(self, with_material):
        model = Scripted("this must never be used")
        use(model)
        response = await with_material.post("/study/explain", json={"topic": UNRELATED})

        assert response.status_code == 200
        result = response.json()
        assert result["explanation"]["grounded"] is False
        assert result["explanation"]["text"] == "I can't find that in your notes."
        assert result["sources"] == []
        assert model.calls == []  # and the model was never asked

    async def test_it_is_saved_to_the_history(self, with_material):
        use(Scripted("Mitochondria produce ATP [1]."))
        result = (await with_material.post("/study/explain", json=body())).json()

        session = (await with_material.get(f"/study/history/{result['session_id']}")).json()
        assert session["kind"] == "explain"
        assert session["topic"] == "mitochondria and ATP"
        content = session["contents"][0]
        assert content["kind"] == "explanation"
        assert content["text"] == "Mitochondria produce ATP [1]."
        assert content["data"]["citations"] == [1]

    async def test_even_a_refusal_is_saved(self, with_material):
        use(Scripted("unused"))
        result = (await with_material.post("/study/explain", json={"topic": UNRELATED})).json()
        session = (await with_material.get(f"/study/history/{result['session_id']}")).json()
        assert session["contents"][0]["grounded"] is False


# ---- 2. summarise ---------------------------------------------------------------


class TestSummarise:
    async def test_returns_cited_points(self, with_material):
        use(Scripted(SUMMARY_JSON))
        result = (await with_material.post("/study/summarise", json=body(points=4))).json()

        assert result["kind"] == "summarise"
        assert len(result["summary"]["points"]) == 2
        assert result["summary"]["citations"] == [1]

    async def test_the_point_limit_reaches_the_model(self, with_material):
        model = Scripted(SUMMARY_JSON)
        use(model)
        await with_material.post("/study/summarise", json=body(points=3))
        assert "at most 3 short points" in model.calls[0][1][0]["content"]

    async def test_it_is_saved_as_bullets_with_the_structure_beside_them(self, with_material):
        use(Scripted(SUMMARY_JSON))
        result = (await with_material.post("/study/summarise", json=body())).json()

        content = (await with_material.get(f"/study/history/{result['session_id']}")).json()["contents"][0]
        assert content["kind"] == "summary"
        assert content["text"].startswith("- Mitochondria produce ATP [1].")
        assert content["data"]["points"] == result["summary"]["points"]


# ---- 3. quiz ---------------------------------------------------------------------


class TestQuiz:
    async def test_returns_questions_with_the_answer_marked(self, with_material):
        use(Scripted(QUIZ_JSON))
        result = (await with_material.post("/study/quiz", json=body(count=1, difficulty="beginner"))).json()

        question = result["quiz"]["questions"][0]
        assert question["choices"][question["answer_index"]] == "ATP"
        assert question["source_index"] == 1
        assert result["quiz"]["difficulty"] == "beginner"

    async def test_nothing_to_quiz_on_is_422_not_an_empty_quiz(self, with_material):
        use(Scripted(QUIZ_JSON))
        response = await with_material.post("/study/quiz", json={"topic": UNRELATED})
        assert response.status_code == 422
        assert "Nothing in your material" in response.json()["detail"]

    async def test_a_model_that_returns_nothing_usable_is_502(self, with_material):
        use(Scripted("I would rather not."))
        response = await with_material.post("/study/quiz", json=body())
        assert response.status_code == 502
        assert "usable question" in response.json()["detail"]

    async def test_the_whole_quiz_is_saved(self, with_material):
        use(Scripted(QUIZ_JSON))
        result = (await with_material.post("/study/quiz", json=body())).json()

        content = (await with_material.get(f"/study/history/{result['session_id']}")).json()["contents"][0]
        assert content["kind"] == "quiz"
        assert content["data"]["questions"][0]["question"] == "What do mitochondria produce?"


# ---- 4. flashcards ----------------------------------------------------------------


class TestFlashcards:
    async def test_cards_are_saved_scheduled_and_returned(self, with_material):
        use(Scripted(CARDS_JSON))
        response = await with_material.post("/study/flashcards", json=body(count=1))

        assert response.status_code == 201
        result = response.json()
        assert result["cards"][0]["front"] == "What produces ATP?"
        assert result["cards"][0]["state"] == "learning"

        # A real row, in the deck and due now.
        assert [c["id"] for c in (await with_material.get("/cards")).json()] == [result["cards"][0]["id"]]
        assert [c["id"] for c in (await with_material.get("/cards/due")).json()] == [result["cards"][0]["id"]]

    async def test_the_card_points_back_at_the_passage_it_came_from(self, with_material):
        use(Scripted(CARDS_JSON))
        result = (await with_material.post("/study/flashcards", json=body(count=1))).json()
        assert result["cards"][0]["chunk_id"] == result["sources"][0]["chunk_id"]

    async def test_it_never_writes_more_cards_than_asked(self, with_material):
        use(Scripted(json.dumps({"cards": [{"front": f"Q{i}", "back": f"A{i}"} for i in range(9)]})))
        result = (await with_material.post("/study/flashcards", json=body(count=2))).json()
        assert len(result["cards"]) == 2

    async def test_nothing_to_write_about_is_422(self, with_material):
        use(Scripted(CARDS_JSON))
        response = await with_material.post("/study/flashcards", json={"topic": UNRELATED})
        assert response.status_code == 422

    async def test_it_is_saved_to_the_history_with_the_cards(self, with_material):
        use(Scripted(CARDS_JSON))
        result = (await with_material.post("/study/flashcards", json=body(count=1))).json()

        content = (await with_material.get(f"/study/history/{result['session_id']}")).json()["contents"][0]
        assert content["kind"] == "flashcards"
        assert content["data"][0]["id"] == result["cards"][0]["id"]


# ---- 5. revision checklist -----------------------------------------------------------


class TestChecklist:
    async def test_returns_ordered_steps(self, with_material):
        use(Scripted(CHECKLIST_JSON))
        result = (await with_material.post("/study/checklist", json=body(items=5))).json()

        assert result["kind"] == "checklist"
        steps = result["checklist"]["items"]
        assert steps[0]["step"].startswith("Recall what mitochondria produce")
        assert steps[0]["why"]
        assert steps[0]["source_index"] == 1

    async def test_the_step_count_reaches_the_model(self, with_material):
        model = Scripted(CHECKLIST_JSON)
        use(model)
        await with_material.post("/study/checklist", json=body(items=4))
        assert "4 steps" in model.calls[0][1][0]["content"]

    async def test_it_is_saved_as_a_numbered_list_with_the_structure_beside_it(self, with_material):
        use(Scripted(CHECKLIST_JSON))
        result = (await with_material.post("/study/checklist", json=body())).json()

        content = (await with_material.get(f"/study/history/{result['session_id']}")).json()["contents"][0]
        assert content["kind"] == "checklist"
        assert content["text"].startswith("1. Recall what mitochondria produce")
        assert len(content["data"]["items"]) == 2

    async def test_it_can_be_filtered_out_of_the_history(self, with_material):
        use(Scripted(CHECKLIST_JSON))
        await with_material.post("/study/checklist", json=body())
        listed = (await with_material.get("/study/history?kind=checklist")).json()
        assert [s["kind"] for s in listed] == ["checklist"]

    async def test_nothing_to_revise_is_422(self, with_material):
        use(Scripted(CHECKLIST_JSON))
        assert (await with_material.post("/study/checklist", json={"topic": UNRELATED})).status_code == 422

    async def test_a_model_that_returns_no_step_is_502(self, with_material):
        use(Scripted("no json here"))
        response = await with_material.post("/study/checklist", json=body())
        assert response.status_code == 502
        assert "usable step" in response.json()["detail"]


# ---- shared behaviour ----------------------------------------------------------------


ENDPOINTS = ["/study/explain", "/study/summarise", "/study/quiz", "/study/flashcards", "/study/checklist"]


class TestValidation:
    @pytest.mark.parametrize("endpoint", ENDPOINTS)
    @pytest.mark.parametrize("topic", ["", "  ", "ab", "x" * 501])
    async def test_an_empty_or_enormous_topic_is_refused_before_any_work(self, with_material, endpoint, topic):
        use(Scripted("unused"))
        assert (await with_material.post(endpoint, json={"topic": topic})).status_code == 422

    @pytest.mark.parametrize(
        "endpoint, payload",
        [
            ("/study/explain", {"level": "expert"}),
            ("/study/summarise", {"points": 0}),
            ("/study/summarise", {"points": 13}),
            ("/study/quiz", {"count": 0}),
            ("/study/quiz", {"count": 21}),
            ("/study/quiz", {"difficulty": "impossible"}),
            ("/study/flashcards", {"count": 0}),
            ("/study/flashcards", {"count": 21}),
            ("/study/checklist", {"items": 0}),
            ("/study/checklist", {"items": 13}),
        ],
    )
    async def test_out_of_range_options_are_refused(self, with_material, endpoint, payload):
        use(Scripted("unused"))
        assert (await with_material.post(endpoint, json=body(**payload))).status_code == 422


class TestScopeAndAccess:
    async def test_a_document_filter_limits_the_passages_used(self, signed_in):
        biology = (await upload(signed_in, name="bio.md", content=BIOLOGY)).json()
        await upload(signed_in, name="hist.md", content="The Treaty of Westphalia ended the Thirty Years War.")
        use(Scripted("Mitochondria produce ATP [1]."))

        result = (await signed_in.post("/study/explain", json=body(document_ids=[biology["id"]]))).json()
        assert {s["document_id"] for s in result["sources"]} == {biology["id"]}

    @pytest.mark.parametrize("endpoint", ENDPOINTS)
    async def test_every_endpoint_needs_a_signed_in_user(self, client, endpoint):
        client.cookies.clear()
        assert (await client.post(endpoint, json=body())).status_code == 401

    async def test_a_bearer_token_works_as_well_as_the_cookie(self, client):
        await register(client, email="alice@x.com")
        await upload(client, content=BIOLOGY)
        token = (
            await client.post("/auth/token", data={"username": "alice@x.com", "password": "correct-horse-battery"})
        ).json()["access_token"]
        client.cookies.clear()
        use(Scripted("Mitochondria produce ATP [1]."))

        response = await client.post(
            "/study/explain", json=body(), headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    async def test_one_user_cannot_study_anothers_material(self, client):
        await register(client, email="alice@x.com")
        await upload(client, content=BIOLOGY)

        client.cookies.clear()
        await register(client, email="bob@x.com")
        model = Scripted("unused")
        use(model)

        result = (await client.post("/study/explain", json=body())).json()
        assert result["sources"] == []
        assert result["explanation"]["grounded"] is False
        assert model.calls == []
        assert (await client.get("/study/history")).json()[0]["topic"] == "mitochondria and ATP"  # bob's own row


class TestModelFailure:
    @pytest.mark.parametrize("endpoint", ENDPOINTS)
    async def test_an_unreachable_model_is_502_with_a_sentence_for_the_student(self, with_material, endpoint):
        use(Broken())
        response = await with_material.post(endpoint, json=body())
        assert response.status_code == 502
        assert "Ollama" in response.json()["detail"]

    @pytest.mark.parametrize("endpoint", ENDPOINTS)
    async def test_a_model_that_is_too_slow_is_504_and_says_what_to_do(self, with_material, endpoint):
        """Different from unreachable: the model answered the door and then stalled."""
        use(TooSlow())
        response = await with_material.post(endpoint, json=body())

        assert response.status_code == 504
        detail = response.json()["detail"]
        assert "took longer than 90 seconds" in detail
        assert "shorter topic" in detail

    async def test_a_stream_that_times_out_mid_answer_becomes_an_error_event(self, with_material):
        """The response has already started, so a 504 is no longer possible."""
        use(TooSlow())
        events: list[str] = []
        async with with_material.stream("POST", "/chat", json={"question": "what do mitochondria produce"}) as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line.startswith("event: ") or line.startswith("data: "):
                    events.append(line)

        assert "event: error" in events
        assert any("took longer than" in line for line in events)
