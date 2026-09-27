"""Explain it back: grading a free-text answer against the card and its notes.

The rating arithmetic is tested directly because it is deterministic code.
The endpoint is tested with a scripted model, for what it sends, what it
saves, and what it refuses to do.
"""

from __future__ import annotations

import json

import pytest

from app.llm import get_chat_model
from app.main import app
from app.services.ai_service import AiService, grade_from
from tests.conftest import register
from tests.test_documents import BIOLOGY, upload


class Scripted:
    model = "scripted"
    timeout = 30.0

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[tuple[str, list[dict]]] = []

    async def complete(self, system, messages, *, json_mode: bool = False) -> str:
        self.calls.append((system, messages))
        return self.reply

    async def stream(self, system, messages):
        yield self.reply


def use(model) -> None:
    app.dependency_overrides[get_chat_model] = lambda: model


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.pop(get_chat_model, None)


# ---- the arithmetic ------------------------------------------------------------------


class TestRating:
    def test_everything_covered_and_nothing_wrong_is_good(self):
        grade = grade_from(correct=["produces ATP", "by oxidative phosphorylation"], missing=[], incorrect=[])
        assert (grade.verdict, grade.score, grade.suggested_rating) == ("correct", 1.0, 3)

    def test_the_grader_never_suggests_easy(self):
        """Easy means instant recall, and a grader reading text cannot see speed."""
        assert grade_from(correct=["a", "b", "c"], missing=[], incorrect=[]).suggested_rating == 3

    def test_half_or_more_covered_is_hard(self):
        grade = grade_from(correct=["produces ATP"], missing=["by oxidative phosphorylation"], incorrect=[])
        assert (grade.verdict, grade.score, grade.suggested_rating) == ("partial", 0.5, 2)

    def test_less_than_half_is_again(self):
        grade = grade_from(correct=["a"], missing=["b", "c"], incorrect=[])
        assert grade.suggested_rating == 1 and grade.verdict == "incorrect"

    def test_nothing_covered_is_again(self):
        assert grade_from(correct=[], missing=["a", "b"], incorrect=[]).suggested_rating == 1

    def test_something_wrong_caps_a_full_answer_at_hard(self):
        """A confident wrong claim is exactly what spaced repetition must catch."""
        grade = grade_from(correct=["a", "b"], missing=[], incorrect=["says it makes glucose"])
        assert grade.suggested_rating == 2 and grade.verdict == "partial"

    def test_something_wrong_and_little_right_is_again(self):
        grade = grade_from(correct=[], missing=["a"], incorrect=["wrong"])
        assert grade.suggested_rating == 1

    def test_no_key_points_at_all_is_again_not_a_division_by_zero(self):
        grade = grade_from(correct=[], missing=[], incorrect=[])
        assert grade.score == 0.0 and grade.suggested_rating == 1


# ---- the service ------------------------------------------------------------------------


class Judge:
    """Answers the grader's two yes/no questions from fixed lists.

    `stated` and `false` hold substrings of facts: a fact containing one gets
    "yes" to that question. Everything else is "no". Records every question so
    a test can assert which ones word overlap made unnecessary.
    """

    model = "judge"
    timeout = 30.0

    def __init__(self, stated=(), false=()) -> None:
        self.stated, self.false = stated, false
        self.questions: list[tuple[str, str]] = []

    async def complete(self, system, messages, *, json_mode: bool = False) -> str:
        fact = system.split("Fact: ", 1)[1].split("\n", 1)[0]
        kind = "stated" if "say this fact" in system else "false"
        self.questions.append((kind, fact))
        hits = self.stated if kind == "stated" else self.false
        return json.dumps({"answer": "yes" if any(h in fact for h in hits) else "no"})

    async def stream(self, system, messages):
        yield ""


QUESTION = "What do mitochondria produce, and what is special about their DNA?"
REFERENCE = "ATP, through oxidative phosphorylation; they carry their own circular DNA, inherited from the mother."


class TestKeyPoints:
    def test_the_reference_is_split_by_its_own_punctuation(self):
        assert AiService._key_points(REFERENCE) == [
            "ATP",
            "through oxidative phosphorylation",
            "they carry their own circular DNA",
            "inherited from the mother",
        ]

    def test_a_single_clause_is_a_single_point(self):
        assert AiService._key_points("In the thylakoid membranes of the chloroplast.") == [
            "In the thylakoid membranes of the chloroplast"
        ]

    def test_the_same_reference_always_splits_the_same_way(self):
        """Deterministic: the same answer can never earn two different grades from a different split."""
        assert AiService._key_points(REFERENCE) == AiService._key_points(REFERENCE)


class TestService:
    async def test_an_answer_in_the_references_own_words_needs_no_model_call(self):
        judge = Judge()
        grade = await AiService(judge).grade_answer(
            QUESTION, REFERENCE, "ATP through oxidative phosphorylation; they carry their own circular DNA inherited from the mother"
        )
        assert grade.verdict == "correct" and grade.suggested_rating == 3
        assert [k for k, _ in judge.questions] == []  # overlap decided every fact, no false-claim check needed

    async def test_a_paraphrase_is_confirmed_by_the_model(self):
        judge = Judge(stated=("their own circular DNA", "inherited from the mother"))
        grade = await AiService(judge).grade_answer(
            QUESTION, REFERENCE, "ATP via oxidative phosphorylation, plus a circular ring of DNA that is theirs, from their mother"
        )
        assert grade.score == 1.0

    async def test_a_paraphrase_sharing_no_word_at_all_is_missed(self):
        """The known limit of the overlap gate, pinned so a change to it is deliberate."""
        grade = await AiService(Judge(stated=("inherited",))).grade_answer(
            QUESTION, REFERENCE, "ATP via oxidative phosphorylation, circular DNA, passed down maternally"
        )
        assert "inherited from the mother" in grade.missing

    async def test_a_wrong_claim_is_caught_even_when_the_words_overlap(self):
        """"lower solute concentration" shares most words with "higher solute concentration"."""
        judge = Judge(false=("higher solute concentration",))
        grade = await AiService(judge).grade_answer(
            "How does water cross the cell membrane?",
            "By osmosis, toward the higher solute concentration.",
            "by osmosis, toward the lower solute concentration",
        )
        assert grade.incorrect == ["toward the higher solute concentration"]
        assert grade.suggested_rating == 2  # half right, one thing wrong

    async def test_an_answer_of_only_known_words_is_never_called_wrong(self):
        """Incomplete is not incorrect: no new term, no false-claim question."""
        judge = Judge(false=("ATP", "DNA", "mother", "oxidative"))
        grade = await AiService(judge).grade_answer(QUESTION, REFERENCE, "They produce ATP.")
        assert grade.incorrect == []
        assert all(k != "false" for k, _ in judge.questions)
        assert 0 < grade.score < 1

    async def test_repeating_the_question_earns_nothing(self):
        grade = await AiService(Judge()).grade_answer(
            "What is special about mitochondrial DNA?", "It is circular.", "mitochondrial DNA is special"
        )
        assert grade.score == 0.0

    async def test_i_dont_know_is_again(self):
        grade = await AiService(Judge()).grade_answer(QUESTION, REFERENCE, "I don't remember.")
        assert grade.suggested_rating == 1 and grade.correct == []

    async def test_the_judge_is_the_grader_model_not_the_chat_model(self):
        writer, judge = Judge(), Judge(stated=("their own circular DNA",))
        await AiService(writer, grader=judge).grade_answer(QUESTION, REFERENCE, "ATP, and a DNA ring of their own")
        assert writer.questions == [] and judge.questions

    async def test_feedback_names_what_to_go_back_over(self):
        grade = await AiService(Judge()).grade_answer(QUESTION, REFERENCE, "ATP")
        assert grade.feedback.startswith("Good start. You left out:")
        assert "inherited from the mother" in grade.feedback


# ---- the endpoint ------------------------------------------------------------------------


async def a_card(client, *, from_document: bool = True) -> dict:
    if from_document:
        await upload(client, content=BIOLOGY)
        use(Scripted(json.dumps({"cards": [{"front": "What do mitochondria produce?", "back": "ATP, through oxidative phosphorylation."}]})))
        cards = (await client.post("/study/flashcards", json={"topic": "mitochondria", "count": 1})).json()["cards"]
        return cards[0]
    return (await client.post("/cards", json={"front": "Capital of Morocco?", "back": "Rabat."})).json()


class TestEndpoint:
    async def test_a_full_answer_is_graded_good_with_its_reasons(self, signed_in):
        card = await a_card(signed_in)
        use(Judge())

        response = await signed_in.post(f"/cards/{card['id']}/grade", json={"answer": "ATP, through oxidative phosphorylation"})
        assert response.status_code == 200
        body = response.json()
        assert body["grade"]["verdict"] == "correct"
        assert body["grade"]["suggested_rating"] == 3
        assert body["expected"] == "ATP, through oxidative phosphorylation."
        assert "Mitochondria" in body["source_text"]

    async def test_the_facts_come_from_the_cards_back(self, signed_in):
        card = await a_card(signed_in)
        judge = Judge()
        use(judge)
        await signed_in.post(f"/cards/{card['id']}/grade", json={"answer": "ATP, and something about chlorophyll"})
        assert {fact for _, fact in judge.questions} <= {"ATP", "through oxidative phosphorylation"}

    async def test_a_card_with_no_passage_can_still_be_graded(self, signed_in):
        card = await a_card(signed_in, from_document=False)
        use(Judge())
        body = (await signed_in.post(f"/cards/{card['id']}/grade", json={"answer": "Rabat"})).json()
        assert body["source_text"] is None
        assert body["grade"]["verdict"] == "correct"

    async def test_grading_does_not_touch_the_schedule(self, signed_in):
        """The grade is advice. Only pressing a rating changes the card."""
        card = await a_card(signed_in)
        use(Judge())
        await signed_in.post(f"/cards/{card['id']}/grade", json={"answer": "no idea"})

        after = (await signed_in.get(f"/cards/{card['id']}")).json()
        assert after["reps"] == 0 and after["state"] == "learning"
        assert card["id"] in [c["id"] for c in (await signed_in.get("/cards/due")).json()]

    async def test_it_is_saved_to_the_history(self, signed_in):
        card = await a_card(signed_in)
        use(Judge())
        body = (await signed_in.post(f"/cards/{card['id']}/grade", json={"answer": "ATP"})).json()

        session = (await signed_in.get(f"/study/history/{body['session_id']}")).json()
        assert session["kind"] == "grade"
        content = session["contents"][0]
        assert content["text"] == "ATP"
        assert content["data"]["suggested_rating"] == 2  # one of two facts
        assert [s["kind"] for s in (await signed_in.get("/study/history?kind=grade")).json()] == ["grade"]

    @pytest.mark.parametrize("answer", ["", "   ", "x" * 2001])
    async def test_an_empty_or_enormous_answer_is_422(self, signed_in, answer):
        card = await a_card(signed_in, from_document=False)
        assert (await signed_in.post(f"/cards/{card['id']}/grade", json={"answer": answer})).status_code == 422

    async def test_an_unreadable_judgement_counts_as_no(self, signed_in):
        """A reply the grader cannot read is "no", never an invented "yes"."""
        card = await a_card(signed_in, from_document=False)
        use(Scripted("no json at all"))
        body = (await signed_in.post(f"/cards/{card['id']}/grade", json={"answer": "the capital is Casablanca"})).json()
        assert body["grade"]["verdict"] == "incorrect"
        assert body["grade"]["incorrect"] == []

    async def test_an_unreachable_model_is_502(self, signed_in):
        card = await a_card(signed_in, from_document=False)

        class Broken:
            async def complete(self, *a, **k):
                raise ConnectionError("down")

        use(Broken())
        # An answer that needs the model: it names the fact's subject and adds a
        # new term, so the false-claim question has to be asked.
        response = await signed_in.post(f"/cards/{card['id']}/grade", json={"answer": "not Rabat but Casablanca"})
        assert response.status_code == 502

    async def test_someone_elses_card_is_404(self, client):
        await register(client, email="alice@x.com")
        card = (await client.post("/cards", json={"front": "Q", "back": "A"})).json()
        client.cookies.clear()
        await register(client, email="bob@x.com")
        use(Judge())
        assert (await client.post(f"/cards/{card['id']}/grade", json={"answer": "A"})).status_code == 404

    async def test_it_needs_a_signed_in_user(self, client):
        client.cookies.clear()
        assert (await client.post("/cards/anything/grade", json={"answer": "A"})).status_code == 401
