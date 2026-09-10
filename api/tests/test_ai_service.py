"""The AI service: the prompts, the parsers, and what happens when a model misbehaves.

No network and no model. A scripted `ChatModel` returns whatever a test needs,
which is the point of the interface: the prompts and the parsing are ours to
test, the model's fluency is not.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.llm import OllamaChat, ScriptedChat
from app.schemas import Source
from app.services.ai_service import REFUSAL, AiService, AiUnavailable, render_passages


def source(index: int, text: str, *, title: str = "Operating systems", position: int = 0) -> Source:
    return Source(
        index=index,
        chunk_id=f"chunk-{index}",
        document_id="doc-1",
        document_title=title,
        position=position,
        text=text,
        score=0.8,
    )


PASSAGES = [
    source(1, "A process is a program in execution: its code, its stack, its heap and its open files."),
    source(2, "A thread is a unit of execution inside a process. Threads share the address space.", position=1),
]


class QueuedChat:
    """Returns each queued reply in turn, and records what it was asked."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, list[dict]]] = []

    async def complete(self, system, messages, *, json_mode: bool = False) -> str:
        self.calls.append((system, messages))
        self.json_mode = json_mode
        return self.replies.pop(0) if self.replies else ""

    async def stream(self, system, messages):
        self.calls.append((system, messages))
        for word in (self.replies.pop(0) if self.replies else "").split(" "):
            yield word + " "


class BrokenChat:
    """Every call fails, the way an unreachable Ollama does."""

    async def complete(self, system, messages, *, json_mode: bool = False) -> str:
        raise httpx.ConnectError("connection refused")

    async def stream(self, system, messages):
        raise OSError("connection refused")
        yield  # pragma: no cover - makes this an async generator


# ---- the prompt --------------------------------------------------------------


class TestPrompt:
    def test_passages_are_numbered_as_the_client_shows_them(self):
        rendered = render_passages(PASSAGES)
        assert rendered.startswith('[1] From "Operating systems", part 1:')
        assert '[2] From "Operating systems", part 2:' in rendered
        assert "unit of execution" in rendered

    async def test_the_system_prompt_carries_the_passages_and_the_refusal(self):
        model = QueuedChat("A process is a program in execution [1].")
        await AiService(model).explain("processes", PASSAGES)
        system, messages = model.calls[0]
        assert "program in execution" in system
        assert REFUSAL in system
        assert "processes" in messages[0]["content"]

    async def test_the_asked_for_level_reaches_the_model(self):
        model = QueuedChat("…")
        await AiService(model).explain("threads", PASSAGES, level="advanced")
        assert "advanced level" in model.calls[0][1][0]["content"]


# ---- 1. explain ---------------------------------------------------------------


class TestExplain:
    async def test_returns_a_grounded_explanation_with_its_citations(self):
        model = QueuedChat("A process is a program in execution [1]. A thread lives inside one [2].")
        result = await AiService(model).explain("processes and threads", PASSAGES)

        assert result.topic == "processes and threads"
        assert result.grounded is True
        assert result.citations == [1, 2]
        assert "program in execution" in result.text

    async def test_invented_citations_are_dropped(self):
        model = QueuedChat("A process is a program in execution [1], and also [7].")
        result = await AiService(model).explain("processes", PASSAGES)
        assert result.citations == [1]

    async def test_no_passages_means_no_model_call(self):
        model = QueuedChat("this must never be used")
        result = await AiService(model).explain("the Treaty of Westphalia", [])

        assert result.text == REFUSAL
        assert result.grounded is False
        assert model.calls == []

    async def test_a_model_that_refuses_is_marked_ungrounded(self):
        model = QueuedChat(REFUSAL)
        result = await AiService(model).explain("quantum tunnelling", PASSAGES)
        assert result.grounded is False


# ---- 2. summarise -------------------------------------------------------------


class TestSummarise:
    async def test_parses_the_json_shape_it_asked_for(self):
        reply = json.dumps(
            {"title": "Processes and threads", "points": ["A process owns an address space [1].", "A thread shares it [2]."]}
        )
        result = await AiService(QueuedChat(reply)).summarise(PASSAGES)

        assert result.title == "Processes and threads"
        assert len(result.points) == 2
        assert result.citations == [1, 2]
        assert result.grounded is True

    async def test_gives_fewer_points_than_asked_rather_than_padding(self):
        reply = json.dumps({"title": "t", "points": ["Only this one [1]."]})
        result = await AiService(QueuedChat(reply)).summarise(PASSAGES, points=5)
        assert result.points == ["Only this one [1]."]

    async def test_never_returns_more_points_than_asked(self):
        reply = json.dumps({"points": [f"Point {i} [1]." for i in range(10)]})
        result = await AiService(QueuedChat(reply)).summarise(PASSAGES, points=3)
        assert len(result.points) == 3

    async def test_prose_from_a_model_that_ignored_json_mode_is_still_used(self):
        reply = "- A process owns an address space [1].\n- A thread is a unit of execution inside it [2]."
        result = await AiService(QueuedChat(reply)).summarise(PASSAGES)
        assert len(result.points) == 2
        assert result.points[0].startswith("A process")

    async def test_no_passages_means_no_model_call(self):
        model = QueuedChat("unused")
        result = await AiService(model).summarise([])
        assert result.points == [] and result.grounded is False and model.calls == []


# ---- 3. quiz ------------------------------------------------------------------

GOOD_QUESTION = {
    "question": "What does a process own that a thread does not?",
    "choices": ["An address space", "A program counter", "A stack", "A register set"],
    "answer": "An address space",
    "explanation": "A process owns the address space; threads share it [1].",
    "source_index": 1,
}


class TestQuiz:
    async def test_returns_structured_questions(self):
        result = await AiService(QueuedChat(json.dumps({"questions": [GOOD_QUESTION]}))).generate_quiz(
            PASSAGES, count=1, difficulty="beginner", topic="Processes"
        )

        assert result.topic == "Processes"
        assert result.difficulty == "beginner"
        question = result.questions[0]
        assert question.choices[question.answer_index] == "An address space"
        assert question.source_index == 1

    @pytest.mark.parametrize(
        "bad",
        [
            {**GOOD_QUESTION, "answer": "something it never offered"},  # answer is not among the choices
            {**GOOD_QUESTION, "answer": ""},                            # no answer at all
            {**GOOD_QUESTION, "answer": "", "answer_index": 9},         # index outside its own choices
            {**GOOD_QUESTION, "answer": "", "answer_index": "first"},   # index not a number
            {**GOOD_QUESTION, "choices": ["Only one"]},                 # not a choice at all
            {**GOOD_QUESTION, "question": "   "},                       # no question
            "a bare string instead of an object",
        ],
    )
    async def test_untrustworthy_questions_are_dropped_not_repaired(self, bad):
        reply = json.dumps({"questions": [bad, GOOD_QUESTION]})
        result = await AiService(QueuedChat(reply)).generate_quiz(PASSAGES, count=5)
        assert len(result.questions) == 1
        assert result.questions[0].question == GOOD_QUESTION["question"]

    async def test_the_index_is_derived_from_the_answer_text_not_trusted_from_the_model(self):
        """A 3B model names the right choice reliably and numbers it badly, so the text wins."""
        item = {**GOOD_QUESTION, "choices": ["A stack", "An address space", "A register set", "A PID"],
                "answer": "An address space", "answer_index": 0}
        result = await AiService(QueuedChat(json.dumps({"questions": [item]}))).generate_quiz(PASSAGES)
        question = result.questions[0]
        assert question.answer_index == 1
        assert question.choices[question.answer_index] == "An address space"

    @pytest.mark.parametrize("written", ["an address space", "  An Address Space.  ", "An address space (the mapping)"])
    async def test_the_match_survives_case_space_and_a_trailing_stop(self, written):
        item = {**GOOD_QUESTION, "answer": written}
        result = await AiService(QueuedChat(json.dumps({"questions": [item]}))).generate_quiz(PASSAGES)
        assert result.questions[0].answer_index == 0

    async def test_a_model_that_numbered_instead_of_naming_is_still_understood(self):
        item = {k: v for k, v in GOOD_QUESTION.items() if k != "answer"} | {"answer_index": 2}
        result = await AiService(QueuedChat(json.dumps({"questions": [item]}))).generate_quiz(PASSAGES)
        assert result.questions[0].answer_index == 2

    async def test_a_source_index_that_does_not_exist_becomes_none(self):
        reply = json.dumps({"questions": [{**GOOD_QUESTION, "source_index": 9}]})
        result = await AiService(QueuedChat(reply)).generate_quiz(PASSAGES)
        assert result.questions[0].source_index is None

    async def test_the_count_and_difficulty_reach_the_model_and_bound_the_result(self):
        model = QueuedChat(json.dumps({"questions": [GOOD_QUESTION] * 6}))
        result = await AiService(model).generate_quiz(PASSAGES, count=2, difficulty="advanced")

        task = model.calls[0][1][0]["content"]
        assert "2 multiple-choice questions" in task and "advanced level" in task
        assert len(result.questions) == 2

    async def test_unusable_output_is_an_empty_quiz_not_an_exception(self):
        result = await AiService(QueuedChat("I would rather not.")).generate_quiz(PASSAGES)
        assert result.questions == []


# ---- 4. flashcards ------------------------------------------------------------

CARDS_JSON = json.dumps(
    {
        "cards": [
            {"front": "What is a process?", "back": "A program in execution."},
            {"front": "What do threads share?", "back": "The address space of their process."},
        ]
    }
)


class TestFlashcards:
    async def test_parses_the_asked_for_shape(self):
        cards = await AiService(QueuedChat(CARDS_JSON)).generate_flashcards("…", count=2)
        assert [c.front for c in cards] == ["What is a process?", "What do threads share?"]

    async def test_accepts_a_bare_list_wrapped_in_prose(self):
        reply = 'Here you go:\n[{"front": "Q", "back": "A"}]\nHope that helps!'
        cards = await AiService(QueuedChat(reply)).generate_flashcards("…")
        assert [(c.front, c.back) for c in cards] == [("Q", "A")]

    async def test_drops_half_cards_and_garbage(self):
        reply = '{"cards": [{"front": "Q"}, {"back": "A"}, "nope", {"front": "Q2", "back": "A2"}]}'
        cards = await AiService(QueuedChat(reply)).generate_flashcards("…")
        assert [(c.front, c.back) for c in cards] == [("Q2", "A2")]

    async def test_nothing_usable_is_an_empty_list(self):
        assert await AiService(QueuedChat("no json here")).generate_flashcards("…") == []
        assert await AiService(QueuedChat('{"cards": "not a list"}')).generate_flashcards("…") == []

    async def test_the_passage_is_what_the_model_is_given(self):
        model = QueuedChat(CARDS_JSON)
        await AiService(model).generate_flashcards("Mitochondria produce ATP.", count=3)
        system, messages = model.calls[0]
        assert "exactly 3 flashcards" in system
        assert messages[0]["content"] == "Mitochondria produce ATP."


# ---- failure ------------------------------------------------------------------


class TestModelFailure:
    async def test_every_method_raises_one_friendly_error(self):
        service = AiService(BrokenChat())
        for call in (
            service.explain("x", PASSAGES),
            service.summarise(PASSAGES),
            service.generate_quiz(PASSAGES),
            service.generate_flashcards("x"),
        ):
            with pytest.raises(AiUnavailable) as raised:
                await call
            assert "Ollama" in raised.value.detail

    async def test_a_broken_stream_raises_the_same_error(self):
        with pytest.raises(AiUnavailable):
            async for _ in AiService(BrokenChat()).stream_answer("x", PASSAGES):
                pass


# ---- the streaming variant ------------------------------------------------------


class TestStreamAnswer:
    async def test_relays_deltas_and_bounds_the_history(self):
        model = ScriptedChat("A process is a program in execution [1].")
        history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i}"} for i in range(20)]

        deltas = [d async for d in AiService(model).stream_answer("what is a process?", PASSAGES, history)]

        assert "".join(deltas) == "A process is a program in execution [1]."
        _, messages = model.calls[0]
        assert len(messages) == 7  # HISTORY_TURNS + the question
        assert messages[-1] == {"role": "user", "content": "what is a process?"}


# ---- the key ---------------------------------------------------------------------


class TestApiKey:
    def test_the_default_is_empty_so_no_key_is_ever_hardcoded(self):
        assert Settings(session_secret="x" * 48).llm_api_key == ""

    def test_a_configured_key_is_sent_as_a_bearer_token(self, monkeypatch):
        seen: dict = {}

        class Recorder(httpx.AsyncClient):
            def __init__(self, *args, **kwargs):
                seen.update(kwargs)
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", Recorder)
        client = OllamaChat("http://x", "m", api_key="secret-from-the-environment")
        assert client._headers == {"Authorization": "Bearer secret-from-the-environment"}

    def test_no_key_means_no_authorization_header(self):
        assert OllamaChat("http://x", "m")._headers == {}
