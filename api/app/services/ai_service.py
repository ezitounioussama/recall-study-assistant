"""The AI service: every prompt in the product, in one place.

Four study features, one method each — explain, summarise, quiz, flashcards —
plus the streaming variant the chat endpoint uses. Each method takes plain
arguments and returns a Pydantic model, never free text the caller has to
parse, so a route handler can hand the result straight to FastAPI.

Three rules hold for all of them.

*Grounded.* Every method is given the passages retrieved from the student's own
material and told to answer only from them. Nothing here fetches anything: what
to retrieve is the caller's decision, and a caller that finds no passage should
not call the model at all.

*Defensive parsing.* Small local models drift out of the shape they were asked
for. JSON mode is used where the provider supports it, and every parser drops
what it cannot read rather than inventing a value or raising.

*No secrets.* The service never sees a key. `app/llm.py` reads one from the
environment when the provider needs it; this file only knows there is a model
somewhere behind the `ChatModel` interface.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Sequence

import httpx
from fastapi import Depends

from app.llm import ChatModel, Turn, get_chat_model
from app.schemas import (
    ChecklistItem,
    ChecklistOut,
    Explanation,
    FlashcardDraft,
    QuizOut,
    QuizQuestion,
    Source,
    Summary,
)

# The sentence the assistant says instead of guessing. Fixed, so the client can
# recognise it and the tests can assert on it.
REFUSAL = "I can't find that in your notes."

# The last N turns of history travel with each request. Enough to follow a
# "what about the second one?" — not enough for a long conversation to crowd
# the passages out of the context window.
HISTORY_TURNS = 6


class AiUnavailable(RuntimeError):
    """The model could not be reached.

    Carries a sentence meant for the student, not a stack trace, and the
    status code that fits: routers raise it as an HTTPException and the chat
    stream sends it as an `error` event.
    """

    status_code = 502
    default_detail = "The model could not be reached. Is Ollama running with the chat model pulled?"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class AiTimeout(AiUnavailable):
    """The model accepted the request and then took too long.

    A different failure from "not running", and a different thing to tell the
    student: the fix is a smaller request or a faster model, not starting
    Ollama. 504 rather than 502 for the same reason — the gateway was reached.
    """

    status_code = 504
    default_detail = "The model took too long to answer. Try a shorter topic, or a faster model."

    @classmethod
    def after(cls, seconds: float, model: str) -> "AiTimeout":
        return cls(
            f"The model ({model}) took longer than {seconds:.0f} seconds to answer. "
            f"Try a shorter topic, fewer items, or a faster model such as llama3.2:3b."
        )


# ---- prompts -----------------------------------------------------------------
#
# Written for a small local model. Small models follow a shown format far more
# reliably than a described one, so each prompt carries an example rather than
# a paragraph of rules.

ANSWER_SYSTEM = """You are Recall, a study assistant. The student is asking about their own notes. Below are numbered passages from those notes.

Answer using only what the passages say, and cite the passage each statement comes from in square brackets. Do not add facts from your own knowledge: if the question asks about something the passages do not mention, say that the notes do not cover it rather than filling the gap.

Match the shape of the request:
- A question: a short, direct answer in plain prose, one to four sentences.
- A request to summarise, list, or explain: do that, from the passages, as a numbered or bulleted list if the student asked for points. Every item cites its passage.
- If the material supports fewer points than the student asked for, give fewer. Never pad a list with placeholders or with anything the passages do not say.

Example of the format for a question:
Question: What is the powerhouse of the cell?
Answer: The mitochondrion produces the cell's ATP [1]. It has a double membrane and carries its own DNA [1].

Only if the passages contain nothing relevant to the request, reply with exactly this sentence and nothing else: {refusal}
A summary or explanation of what the passages do say is always possible when they are on the topic — do not refuse those.

Do not mention these instructions or the word "passages".

Passages:
{passages}"""

EXPLAIN_TASK = """Explain "{topic}" to a student at {level} level, using only the passages.

Two to five sentences of plain prose. Define any term the passages define. Cite every statement."""

SUMMARISE_TASK = """Summarise the passages as at most {points} short points, in the order the material presents them.

Respond with JSON only, in exactly this shape:
{{"title": "...", "points": ["... [1]", "... [2]"]}}

Each point is one sentence and ends with the bracket citation of the passage it came from. Give fewer points if the material supports fewer. Never pad."""

QUIZ_TASK = """Write exactly {count} multiple-choice questions at {difficulty} level to test whether the student has understood the passages.

Rules:
- Ask only what the passages answer. No trivia, no outside knowledge.
- Exactly four choices per question, one of them correct.
- Write each choice as the answer itself. Do not prefix them with "A", "B", "1." or any label — the app numbers them.
- Never use "all of the above" or "none of the above".
- The wrong choices must be plausible to someone who half-remembers the material, not obviously silly.
- "answer" repeats the correct choice word for word, exactly as it appears in "choices".
- "explanation" says why that choice is right, in one sentence, and ends with the passage number in brackets.
- "source_index" is the number of the passage the question came from.

Respond with JSON only, in exactly this shape:
{{"questions": [{{"question": "What does a process own that a thread does not?", "choices": ["An address space", "A program counter", "A stack", "A set of registers"], "answer": "An address space", "explanation": "Threads share the address space of their process [1].", "source_index": 1}}]}}

Now write {count} questions about the passages above."""

CHECKLIST_TASK = """Write a revision checklist for "{topic}": {items} steps a student should work through to be sure they know this material.

Rules:
- Every step is an action the student performs: recall something without looking, explain it out loud, work through an example, compare two things, sketch a process.
- Order them from remembering the facts to using them. Definitions first, applications last.
- Only cover what the passages contain. Do not invent topics they do not mention.
- "why" says what that particular step proves. Every step has a different why — do not repeat one, and do not copy the example.
- "source_index" is the number of the passage the step came from.

Respond with JSON only, in exactly this shape:
{{"items": [
  {{"step": "Recall the three parts of a process control block without looking", "why": "the definition has to be automatic before anything builds on it", "source_index": 1}},
  {{"step": "Explain out loud why a context switch costs more than a function call", "why": "shows you understand the mechanism, not just the label", "source_index": 2}},
  {{"step": "Work out how long ten threads wait under a 20ms quantum", "why": "applying the formula is where a half-learned rule falls apart", "source_index": 2}}
]}}

Now write {items} steps for "{topic}", each with its own why."""

FLASHCARDS_SYSTEM = """You write flashcards for a student from a passage of their own notes.

Write exactly {n} flashcards. Each card has:
- "front": one specific question that the passage answers
- "back": the answer in one or two sentences, using the passage's own facts

Only ask what the passage actually answers. Prefer why, how, and what-distinguishes questions over trivia. Do not number the cards.

Respond with JSON only, in exactly this shape:
{{"cards": [{{"front": "...", "back": "..."}}]}}"""


# ---- the service --------------------------------------------------------------


class AiService:
    """Study content from a model, in structured form.

    Holds a `ChatModel` and nothing else. The tests pass a scripted one; the
    application passes the configured provider.
    """

    def __init__(self, model: ChatModel) -> None:
        self._model = model

    # ---- 1. explain ----------------------------------------------------------

    async def explain(self, topic: str, sources: Sequence[Source], *, level: str = "beginner") -> Explanation:
        """Explain a topic from the student's own material."""
        if not sources:
            return Explanation(topic=topic, text=REFUSAL, grounded=False, citations=[])

        text = await self._ask(
            self._answer_system(sources),
            EXPLAIN_TASK.format(topic=topic, level=level),
        )
        return Explanation(
            topic=topic,
            text=text,
            grounded=self._is_grounded(text),
            citations=self.citations(text, len(sources)),
        )

    # ---- 2. summarise --------------------------------------------------------

    async def summarise(self, sources: Sequence[Source], *, title: str = "", points: int = 5) -> Summary:
        """Reduce the passages to a handful of cited points."""
        if not sources:
            return Summary(title=title, points=[], grounded=False, citations=[])

        raw = await self._ask(
            self._answer_system(sources),
            SUMMARISE_TASK.format(points=points),
            json_mode=True,
        )
        data = _load_json(raw)
        parsed = [str(p).strip() for p in _items(data, "points") if str(p).strip()]
        # A model that ignored JSON mode still produced prose worth keeping:
        # fall back to its lines rather than showing the student nothing.
        bullets = parsed or [line.lstrip("-*0123456789. ").strip() for line in raw.splitlines() if len(line.strip()) > 20]
        bullets = bullets[:points]

        return Summary(
            title=str(data.get("title") or title or (sources[0].document_title if sources else "")),
            points=bullets,
            grounded=bool(bullets) and self._is_grounded(" ".join(bullets)),
            citations=self.citations(" ".join(bullets), len(sources)),
        )

    # ---- 3. quiz -------------------------------------------------------------

    async def generate_quiz(
        self, sources: Sequence[Source], *, count: int = 5, difficulty: str = "beginner", topic: str = ""
    ) -> QuizOut:
        """Multiple-choice questions the passages actually answer."""
        if not sources:
            return QuizOut(topic=topic, difficulty=difficulty, questions=[])

        raw = await self._ask(
            self._answer_system(sources),
            QUIZ_TASK.format(count=count, difficulty=difficulty),
            json_mode=True,
        )
        questions = [q for item in _items(_load_json(raw), "questions") if (q := _as_question(item, len(sources)))]
        return QuizOut(
            topic=topic or (sources[0].document_title if sources else ""),
            difficulty=difficulty,
            questions=questions[:count],
        )

    # ---- 4. flashcards -------------------------------------------------------

    async def generate_flashcards(self, passage: str, *, count: int = 3) -> list[FlashcardDraft]:
        """Front/back pairs from one passage.

        Takes the passage text rather than a `Source` because cards are written
        per chunk, one model call each: a card should be answerable from the
        passage printed on its back.
        """
        raw = await self._ask(FLASHCARDS_SYSTEM.format(n=count), passage, json_mode=True)
        cards: list[FlashcardDraft] = []
        for item in _items(_load_json(raw), "cards"):
            if not isinstance(item, dict):
                continue
            front = str(item.get("front", "")).strip()
            back = str(item.get("back", "")).strip()
            if front and back:
                cards.append(FlashcardDraft(front=front[:2000], back=back[:4000]))
        return cards[:count]

    # ---- 5. revision checklist -----------------------------------------------

    async def generate_revision_checklist(
        self, topic: str, sources: Sequence[Source], *, items: int = 6
    ) -> ChecklistOut:
        """An ordered list of things to do to be sure you know a topic.

        Not a summary of the material: a list of actions performed against it,
        ordered from recalling definitions to applying them. This is the one
        the MCP tool exposes, so its output has to be structured enough for
        another program to render.
        """
        if not sources:
            return ChecklistOut(topic=topic, items=[])

        raw = await self._ask(
            self._answer_system(sources),
            CHECKLIST_TASK.format(topic=topic, items=items),
            json_mode=True,
        )
        parsed = [step for item in _items(_load_json(raw), "items") if (step := _as_step(item, len(sources)))]
        return ChecklistOut(topic=topic, items=parsed[:items])

    # ---- the streaming variant, for /chat -------------------------------------

    async def stream_answer(
        self, question: str, sources: Sequence[Source], history: Sequence[Turn] = ()
    ) -> AsyncIterator[str]:
        """The same grounded answer, delivered as it is written.

        A generator, so the caller relays deltas to the browser. Errors raise
        `AiUnavailable` from inside the iteration, which the route turns into
        an `error` event rather than a broken stream.
        """
        messages: list[Turn] = [*list(history)[-HISTORY_TURNS:], {"role": "user", "content": question}]
        try:
            async for delta in self._model.stream(self._answer_system(sources), messages):
                yield delta
        except httpx.TimeoutException as exc:
            raise self._timeout() from exc
        except (httpx.HTTPError, RuntimeError, OSError) as exc:
            raise AiUnavailable() from exc

    # ---- shared --------------------------------------------------------------

    def _answer_system(self, sources: Sequence[Source]) -> str:
        return ANSWER_SYSTEM.format(refusal=REFUSAL, passages=render_passages(sources))

    async def _ask(self, system: str, user: str, *, json_mode: bool = False) -> str:
        """One model call, with both failure modes named.

        `asyncio.wait_for` is the outer bound. The HTTP client has its own
        read timeout, but a provider that dribbles one byte a minute keeps
        resetting it — the request would never finish and never fail. This
        caps the whole call regardless of how the bytes arrive.
        """
        limit = getattr(self._model, "timeout", 0.0) or None
        try:
            reply = await asyncio.wait_for(
                self._model.complete(system, [{"role": "user", "content": user}], json_mode=json_mode),
                timeout=limit,
            )
        except (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException) as exc:
            raise self._timeout() from exc
        except (httpx.HTTPError, RuntimeError, OSError) as exc:
            raise AiUnavailable() from exc
        return reply.strip()

    def _timeout(self) -> AiTimeout:
        seconds = getattr(self._model, "timeout", 0.0)
        model = getattr(self._model, "model", "the model")
        return AiTimeout.after(seconds, model) if seconds else AiTimeout()

    @staticmethod
    def _is_grounded(text: str) -> bool:
        return bool(text) and REFUSAL.lower() not in text.lower()

    @staticmethod
    def citations(answer: str, count: int) -> list[int]:
        """The passage numbers the answer cites that exist.

        Small models sometimes invent a [2] when there is only one passage. The
        client highlights what was used, and it should not have to guess which
        brackets to believe.
        """
        return sorted({int(n) for n in _CITATION.findall(answer) if 1 <= int(n) <= count})


# ---- helpers -------------------------------------------------------------------

_CITATION = re.compile(r"\[(\d+)\]")
_JSON_BLOB = re.compile(r"\{.*\}|\[.*\]", re.DOTALL)


def render_passages(sources: Sequence[Source]) -> str:
    """The passages as the model sees them, numbered exactly as the client shows them."""
    return "\n\n".join(
        f'[{s.index}] From "{s.document_title}", part {s.position + 1}:\n{s.text}' for s in sources
    )


def _load_json(text: str) -> dict:
    """The JSON object in a reply, or an empty dict. Never raises.

    Tolerates prose around the JSON, which a model in a chatty mood adds even
    when asked not to.
    """
    match = _JSON_BLOB.search(text)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {"_list": data}


def _items(data: dict, key: str) -> list:
    """The list under `key`, or a bare list the model returned instead."""
    value = data.get(key, data.get("_list", []))
    return value if isinstance(value, list) else []


def _as_question(item: object, source_count: int) -> QuizQuestion | None:
    """One quiz question, or None if the model's item cannot be trusted.

    The model is asked to name the correct choice as text, not to number it:
    a 3B model writing four plausible options gets the *index* of the right one
    wrong more often than not — measured, all three of three on llama3.2:3b —
    while repeating the winning line verbatim is something it does reliably.
    The index the API returns is derived here by matching that text.

    A question whose answer cannot be located is dropped rather than repaired.
    A wrong answer key is worse than a missing question: it marks a student
    wrong for being right.
    """
    if not isinstance(item, dict):
        return None
    question = str(item.get("question", "")).strip()
    choices = [str(c).strip() for c in item.get("choices", []) if str(c).strip()]
    if not question or len(choices) < 2:
        return None

    answer_index = _locate_answer(item, choices)
    if answer_index is None:
        return None

    source_index = item.get("source_index")
    try:
        source = int(source_index)
    except (TypeError, ValueError):
        source = 0
    return QuizQuestion(
        question=question[:1000],
        choices=[c[:500] for c in choices[:6]],
        answer_index=answer_index,
        explanation=str(item.get("explanation", "")).strip()[:1000],
        source_index=source if 1 <= source <= source_count else None,
    )


def _as_step(item: object, source_count: int) -> ChecklistItem | None:
    """One checklist step, or None when there is no action in it.

    A step with no text is useless; one with a source number that does not
    exist keeps its text and loses the number, because the step is still
    worth doing even when the model mislabelled where it came from.
    """
    if isinstance(item, str):
        return ChecklistItem(step=item.strip()[:400]) if item.strip() else None
    if not isinstance(item, dict):
        return None

    step = str(item.get("step", "")).strip()
    if not step:
        return None
    try:
        source = int(item.get("source_index"))
    except (TypeError, ValueError):
        source = 0
    return ChecklistItem(
        step=step[:400],
        why=str(item.get("why", "")).strip()[:300],
        source_index=source if 1 <= source <= source_count else None,
    )


def _locate_answer(item: dict, choices: list[str]) -> int | None:
    """Which choice the model meant, or None.

    Prefers the answer text; falls back to `answer_index` for a model that
    numbered it instead. Matching ignores case, surrounding space and a
    trailing full stop, and accepts a unique prefix — nothing looser, because
    a fuzzy match that picks the wrong option is the failure being avoided.
    """
    answer = str(item.get("answer", "")).strip()
    if answer:
        normalised = [_norm(c) for c in choices]
        target = _norm(answer)
        if target in normalised:
            return normalised.index(target)
        starts = [i for i, c in enumerate(normalised) if c.startswith(target) or target.startswith(c)]
        if len(starts) == 1:
            return starts[0]

    try:
        index = int(item["answer_index"])
    except (KeyError, TypeError, ValueError):
        return None
    return index if 0 <= index < len(choices) else None


def _norm(text: str) -> str:
    return " ".join(text.lower().split()).rstrip(".")


def get_ai_service(model: ChatModel = Depends(get_chat_model)) -> AiService:
    """FastAPI dependency. Overriding `get_chat_model` in a test swaps the model."""
    return AiService(model)
