# Phase 3 — LLM API integration

*Lab phase 3 of 7 · Oussama Ezitouni*

Every prompt in the product now lives in one file,
[`api/app/services/ai_service.py`](../api/app/services/ai_service.py), behind four
methods that return Pydantic models. The routers do HTTP; the service does AI.

## The service

| # | Method | Returns | Used by |
|---|---|---|---|
| 1 | `explain(topic, sources, level=…)` | `Explanation {topic, text, grounded, citations}` | `/chat` today, `POST /study/explain` in phase 5 |
| 2 | `summarise(sources, points=…)` | `Summary {title, points[], grounded, citations}` | `/chat`, `POST /study/summarise` |
| 3 | `generate_quiz(sources, count=…, difficulty=…)` | `QuizOut {topic, difficulty, questions[]}` | `POST /study/quiz` |
| 4 | `generate_flashcards(passage, count=…)` | `list[FlashcardDraft {front, back}]` | `POST /cards/generate` |
| — | `stream_answer(question, sources, history)` | text deltas | `POST /chat` (server-sent events) |

The output models are in [`api/app/schemas.py`](../api/app/schemas.py), so they are
part of the OpenAPI schema and a route can return one unchanged.

Three rules hold for all four:

- **Grounded.** Each method is handed the passages retrieved from the student's
  own material and told to answer only from them. The service fetches nothing:
  a caller that retrieved no passage does not call the model at all —
  `explain` and `summarise` return the refusal without a request.
- **Defensive parsing.** JSON mode where the provider supports it, and a parser
  that drops what it cannot read rather than inventing a value or raising.
- **No secrets.** The service never sees a key. It knows only that a model sits
  behind the `ChatModel` interface.

## Separation

```
routers/chat.py    ──┐
routers/cards.py   ──┤──► services/ai_service.py ──► llm.py (ChatModel) ──► Ollama
routers/study.py ──┘        prompts, parsing,          the transport,
  (phase 5)                 structured output          the key, the timeout
```

Before this phase the prompt for chat lived in the chat router and the prompt
for flashcards in the cards router, each with its own JSON parser. Both routers
lost about forty lines; `routers/chat.py` no longer imports a model at all.

`llm.py` keeps the transport: one `ChatModel` protocol with `complete()` and
`stream()`, an `OllamaChat` implementation, and a `ScriptedChat` used by the
tests. Swapping provider is a settings change, and testing the prompts needs no
network.

## The key

Recall's default provider is a local Ollama, which has no authentication. The
adapter still supports a key, because an OpenAI-compatible gateway or a hosted
endpoint in front of the same API needs one:

```python
# app/config.py — read from the environment, empty by default
llm_api_key: str = ""

# app/llm.py — sent only when set, never logged, never returned
self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
```

`.env.example` ships the name with no value and `.env` is gitignored, so the
real value exists only on the machine that runs the service. A test asserts the
default is empty (no key can be hardcoded without failing it) and that the
header is present exactly when a key is configured.

## Two things the model got wrong, and what was done about them

**A quiz request never came back.** Asked for JSON, `llama3.2:3b` failed to
close its object and generated until the 300-second read timeout. Ollama's
`num_predict` defaults to unlimited; the adapter now caps a reply at 2048
tokens, which is far more than any of these prompts needs.

**The answer key was wrong.** The first quiz prompt asked the model for
`answer_index`, the position of the correct choice. `llama3.2:3b` got it wrong
on three questions out of three — it wrote four good options and then pointed
at the wrong one. It repeats the winning line verbatim reliably, so the prompt
now asks for `"answer"` as text and the service derives the index by matching
it against the choices (case, spacing and a trailing full stop ignored; a
unique prefix accepted; anything looser refused). A question whose answer
cannot be located is dropped: a wrong key is worse than a missing question,
because it marks a student wrong for being right. A model that numbers instead
of naming is still understood, through `answer_index` as a fallback.

Stripping "A. " prefixes from choices in code was considered and rejected — one
of the model's own correct answers was *"A unit of execution"*.

## Live evidence

`llama3.2:3b` on CPU, three passages from the operating-systems notes:

| Method | Time | Result |
|---|---|---|
| `explain("what a thread is")` | 8 s | grounded, cites `[2]`: "A thread is a unit of execution inside a process… All threads of a process share the same address space" |
| `summarise(points=4)` | 15 s | 4 points, cites `[1] [2] [3]`, title "Key concepts in operating systems" |
| `generate_quiz(count=3)` | 31 s | 3/3 kept, every key correct: "An address space", "Open files", "It is preempted" |
| `generate_flashcards(count=3)` | 16 s | 3 cards, e.g. *"What is the response time bound of Round Robin scheduling?"* |
| `explain(…, [])` — no passages | 0 s | `"I can't find that in your notes."`, `grounded=False`, no model call |

`qwen3:8b` answers the same quiz correctly in 132 s. The default stays
`llama3.2:3b`; `CHAT_MODEL` in `api/.env` switches it.

## Tests

`api/tests/test_ai_service.py` — 39 tests, no network and no model:

- the prompt carries the numbered passages, the refusal sentence, the requested level, count and difficulty;
- explain: grounded answer with citations, invented citations dropped, no passages means no model call, a refusing model is marked ungrounded;
- summarise: the JSON shape, fewer points rather than padding, never more than asked, prose kept when the model ignores JSON mode;
- quiz: structured questions, the index derived from the answer text, matching that survives case and punctuation, the `answer_index` fallback, and six kinds of untrustworthy item dropped;
- flashcards: the asked-for shape, a bare list wrapped in prose, half cards and garbage dropped;
- failure: every method raises one `AiUnavailable` carrying a sentence for the student;
- the key: empty by default, sent as a bearer token when set, absent when not.

Whole suite: **134 tests**, run in CI on every push.

```bash
cd api && .venv/bin/python -m pytest -q
```

## Why async

Every model call is `async` and the answer path streams. A study answer takes
seconds to a minute on a CPU; a synchronous call would hold a worker thread for
that whole time and the second student would wait for the first. With `async`,
the event loop serves other requests while the model writes, and `/chat` sends
each token onward as it arrives, so the reader sees progress instead of a
spinner. Phase 6 adds the timeout handling around it — the setting
(`LLM_TIMEOUT_SECONDS`) and the friendly error (`AiUnavailable`) are already in
place.
