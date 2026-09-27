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

from app.llm import ChatModel, Turn, get_chat_model, get_grader_model
from app.schemas import (
    ChecklistItem,
    Grade,
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

KEY_CHECK_SYSTEM = """You check quiz questions against a passage. Read the passage, then the question and its numbered choices. Pick the one choice the passage shows to be correct. If no choice is correct, or more than one is, answer 0.
Reply with JSON only: {"answer": <number>}"""

STATED_SYSTEM = """Question: {question}
Fact: {point}

Does the student's answer say this fact? Different wording counts. Answer "yes" or "no".
Respond with JSON only: {{"answer": "yes"}}"""

CONFLICT_SYSTEM = """Question: {question}
Correct answer: {expected}
Fact being checked: {point}

Does the student's answer claim something that is false according to the correct answer — for example the opposite of the fact, or a different thing in its place? An answer that is only incomplete, or leaves the fact out, is NOT false. Answer "yes" or "no".
Respond with JSON only: {{"answer": "no"}}"""

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

    def __init__(self, model: ChatModel, grader: ChatModel | None = None) -> None:
        self._model = model
        # Judging answers needs a stronger model than writing them; see
        # `grader_model` in config.py for the measurement.
        self._grader = grader or model

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

    async def check_answer_keys(self, quiz: QuizOut, sources: Sequence[Source]) -> QuizOut:
        """Keep only the questions a second, independent reading agrees with.

        The model that writes a quiz also marks its answer, and `llama3.2:3b`
        marks it wrong often enough to matter: on the demo notes it wrote
        "A process has a lower creation cost" as correct next to an
        explanation saying the opposite. Each question is answered again by
        the grader model from the passage alone, without seeing the key, and a
        question where the two disagree is dropped. A missing question costs
        the student nothing; a wrong key marks them wrong for being right.
        """
        by_index = {s.index: s for s in sources}
        everything = "\n\n".join(s.text for s in sources)

        async def agrees(q: QuizQuestion) -> bool:
            source = by_index.get(q.source_index) if q.source_index else None
            numbered = "\n".join(f"{i + 1}. {choice}" for i, choice in enumerate(q.choices))
            raw = await self._ask(
                KEY_CHECK_SYSTEM,
                f"Passage:\n{source.text if source else everything}\n\nQuestion: {q.question}\n{numbered}",
                json_mode=True,
                model=self._grader,
            )
            try:
                return int(_load_json(raw).get("answer", 0)) == q.answer_index + 1
            except (TypeError, ValueError):
                return False

        # Two choices that say the same thing ("an order of magnitude", "one
        # order of magnitude") make any key wrong for someone. The checker
        # model misses these, so they are caught in code first.
        distinct = [q for q in quiz.questions if _distinct_choices(q.choices)]
        verdicts = await asyncio.gather(*(agrees(q) for q in distinct))
        return quiz.model_copy(update={"questions": [q for q, ok in zip(distinct, verdicts) if ok]})

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

    # ---- 6. grade a free-text answer -------------------------------------------

    async def grade_answer(self, question: str, expected: str, answer: str, *, passage: str = "") -> Grade | None:
        """Compare what the student wrote with the card's reference answer.

        Two narrow steps rather than one broad one. Asked in a single prompt to
        list what an answer got right, missed and got wrong, llama3.2:3b pulled
        key points from the passage instead of the reference, filed correct
        facts under "incorrect", and gave a wrong answer the same grade as a
        right one. So the reference is first split into its facts, and then
        each fact is checked on its own — one three-way decision per call,
        which a small model makes reliably. The splitting is done in code.

        `passage` is accepted for callers that have it, but the facts come from
        the reference answer: that is what the card asks the student to recall.

        Returns None when the reference is empty, so the caller falls back to
        the student rating themselves.
        """
        points = self._key_points(expected)
        if not points:
            return None

        # The facts are independent, so they are checked at once. Ollama runs
        # parallel requests when it has the memory; when it does not, this
        # costs nothing over checking them in turn. Measured: 23 s sequential
        # for a five-fact card.
        verdicts = await asyncio.gather(
            *(self._check_point(question, point, answer, expected=expected) for point in points)
        )

        correct: list[str] = []
        missing: list[str] = []
        incorrect: list[str] = []
        for point, verdict in zip(points, verdicts, strict=True):
            if verdict == "stated":
                correct.append(point)
            elif verdict == "contradicted":
                incorrect.append(point)
            else:
                missing.append(point)

        # Contradicted facts are key points too: they count against coverage.
        return grade_from(
            correct=correct,
            missing=missing + incorrect,
            incorrect=incorrect,
            feedback=_feedback(correct, missing, incorrect),
        )

    @staticmethod
    def _key_points(expected: str) -> list[str]:
        """The reference answer's facts, split by its own punctuation.

        Deterministic on purpose. Asked to split the reference, the model gave
        different facts on different calls and sometimes invented one
        ("Chloroplasts are organelles"), so the same answer could earn two
        different grades. A card's back is one or two sentences; its clauses
        are its facts.
        """
        pieces = [p.strip(" .,;:") for p in re.split(r";|,|\.\s+|\.$|\n", expected)]
        # "…, and pointers to the open-file table" is a fact; its "and" is not.
        pieces = [re.sub(r"^(and|or|but|also)\s+", "", p, flags=re.IGNORECASE) for p in pieces]
        return [p for p in pieces if _terms(p)][:6] or [expected.strip()]

    async def _check_point(self, question: str, point: str, answer: str, *, expected: str = "") -> str:
        """stated, contradicted or not_stated.

        Word overlap decides the clearest case — every content word present —
        and the model is consulted for the rest: a paraphrase, or a claim that
        might be false.
        Measured on llama3.2:3b, a model-only check both credited facts the
        answer never mentioned and failed a fact written as a single word, so
        neither signal alone was trustworthy.

        Terms that already appear in the question are ignored — repeating the
        question back is not knowing the answer.
        """
        asked = _terms(question)
        wanted = (_terms(point) - asked) or _terms(point)
        given = _terms(answer)
        coverage = len(wanted & given) / len(wanted)

        user = [{"role": "user", "content": f"Student's answer: {answer}"}]

        # A wrong claim always brings a term that neither the reference nor the
        # question contains — "glucose", "father", "lower". Only then is the
        # model asked whether the answer is false, and it is asked whether or
        # not the overlap looked good: "towards lower solute concentration"
        # shares most of its words with "toward the higher solute
        # concentration" and is still wrong. An answer made only of known words
        # can be incomplete, but it cannot contradict anything.
        novel = given - _terms(expected or point) - asked
        if novel and (given & _terms(point)) and await self._yes(
            CONFLICT_SYSTEM.format(question=question, expected=expected or point, point=point), user
        ):
            return "contradicted"

        # Overlap settles it only when every content word of the fact is there.
        # At a 0.6 threshold "it lets the thread keep running" passed for "it
        # preempts the running thread": the object words matched, the verb that
        # carried the meaning did not.
        if coverage == 1.0:
            return "stated"
        if coverage > 0 and await self._yes(STATED_SYSTEM.format(question=question, point=point), user):
            return "stated"
        return "not_stated"

    async def _yes(self, system: str, messages: list[Turn]) -> bool:
        raw = await self._ask(system, messages[0]["content"], json_mode=True, model=self._grader)
        return str(_load_json(raw).get("answer", "")).strip().lower().startswith("y")

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

    async def _ask(self, system: str, user: str, *, json_mode: bool = False, model: ChatModel | None = None) -> str:
        """One model call, with both failure modes named.

        `asyncio.wait_for` is the outer bound. The HTTP client has its own
        read timeout, but a provider that dribbles one byte a minute keeps
        resetting it — the request would never finish and never fail. This
        caps the whole call regardless of how the bytes arrive.
        """
        chosen = model or self._model
        limit = getattr(chosen, "timeout", 0.0) or None
        try:
            reply = await asyncio.wait_for(
                chosen.complete(system, [{"role": "user", "content": user}], json_mode=json_mode),
                timeout=limit,
            )
        except (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException) as exc:
            raise self._timeout(chosen) from exc
        except (httpx.HTTPError, RuntimeError, OSError) as exc:
            raise AiUnavailable() from exc
        return reply.strip()

    def _timeout(self, which: ChatModel | None = None) -> AiTimeout:
        which = which or self._model
        seconds = getattr(which, "timeout", 0.0)
        model = getattr(which, "model", "the model")
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


_SAME_WORD = {"a": "one", "an": "one", "1": "one", "the": ""}


def _distinct_choices(choices: Sequence[str]) -> bool:
    """False when two choices read the same once articles and case are ignored."""
    seen = set()
    for choice in choices:
        words = re.findall(r"[a-z0-9]+", choice.lower())
        key = " ".join(w for w in (_SAME_WORD.get(w, w) for w in words) if w)
        if key in seen:
            return False
        seen.add(key)
    return True


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


def grade_from(*, correct: list[str], missing: list[str], incorrect: list[str], feedback: str = "") -> Grade:
    """Turn the three lists into a score, a verdict and a suggested rating.

    Kept out of the model on purpose. A small model asked for "a rating from
    1 to 4" is inconsistent from one call to the next; asked which points were
    covered, it is far more reliable, and the arithmetic from there is ours.

    - Anything wrong caps the rating at Hard, and at Again when less than half
      was covered: a confident wrong answer is the case spaced repetition most
      needs to catch.
    - All key points and nothing wrong is Good. Never Easy — "easy" in FSRS
      means instant recall, and a grader reading text cannot see how long the
      student took.
    """
    total = len(correct) + len(missing)
    score = len(correct) / total if total else 0.0

    if incorrect:
        rating = 1 if score < 0.5 else 2
    elif total and not missing:
        rating = 3
    elif score >= 0.5:
        rating = 2
    else:
        rating = 1

    # The verdict describes the answer, the rating schedules the card, and
    # they are not the same scale: "They produce ATP" covers one fact in four,
    # which is Again for scheduling but plainly a partial answer, not a wrong
    # one.
    if rating == 3:
        verdict = "correct"
    elif not correct or (incorrect and score < 0.5):
        verdict = "incorrect"
    else:
        verdict = "partial"
    return Grade(
        verdict=verdict,
        score=round(score, 2),
        correct=correct,
        missing=missing,
        incorrect=incorrect,
        feedback=feedback,
        suggested_rating=rating,
    )


_STOPWORDS = frozenset(
    "the a an of and or to in on by is are was were it its their they them that this these those with from "
    "for as at be been has have had own do does did what which who how why when where not no yes can will "
    "would should could about into than then there here also only just very more most some any each "
    # Prepositions carry no fact: "via oxidative phosphorylation" says what
    # "through oxidative phosphorylation" says.
    "through via within inside onto upon across".split()
)


def _terms(text: str) -> set[str]:
    """Content words, cut to five letters so "produce" meets "produced" and "producing"."""
    return {w[:5] for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in _STOPWORDS}


def _feedback(correct: list[str], missing: list[str], incorrect: list[str]) -> str:
    """One sentence for the student, built from the lists rather than written by the model."""
    if incorrect:
        return "Check this against your notes: " + "; ".join(incorrect) + "."
    if not missing:
        return "You covered every point."
    if not correct:
        return "Go back over: " + "; ".join(missing) + "."
    return "Good start. You left out: " + "; ".join(missing) + "."


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip()[:300] for v in value if str(v).strip()][:8]


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


def get_ai_service(
    model: ChatModel = Depends(get_chat_model),
    grader: ChatModel | None = Depends(get_grader_model),
) -> AiService:
    """FastAPI dependency. Overriding `get_chat_model` in a test swaps the model."""
    return AiService(model, grader)
