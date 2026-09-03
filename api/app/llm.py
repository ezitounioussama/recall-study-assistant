"""The chat model behind /chat.

One small interface — stream(system, messages) yields text deltas — with an
Ollama implementation for the product and a scripted one for the tests. The
router never imports Ollama directly, so swapping the model is a settings
change and testing the router needs no network.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Protocol, TypedDict

import httpx

from app.config import settings


class Turn(TypedDict):
    role: str  # "user" | "assistant"
    content: str


class ChatModel(Protocol):
    async def stream(self, system: str, messages: list[Turn]) -> AsyncIterator[str]: ...


# Families that emit a reasoning block before the answer. Ollama can switch it
# off with `think: false`, but rejects the field for models that never think,
# so it is only sent when the model is one of these.
_THINKING_FAMILIES = ("qwen3", "deepseek-r1", "gpt-oss", "magistral")


class OllamaChat:
    def __init__(self, host: str, model: str) -> None:
        self._host = host.rstrip("/")
        self._model = model

    async def stream(self, system: str, messages: list[Turn]) -> AsyncIterator[str]:
        payload: dict = {
            "model": self._model,
            "stream": True,
            "messages": [{"role": "system", "content": system}, *messages],
            # Low temperature: this is "answer from the passages", not creative
            # writing, and a grounded answer should come out the same twice.
            "options": {"temperature": 0.2, "num_ctx": 8192},
        }
        if self._model.split(":")[0] in _THINKING_FAMILIES:
            payload["think"] = False

        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=10)) as http:
            async with http.stream("POST", f"{self._host}/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    event = json.loads(line)
                    if "error" in event:
                        raise RuntimeError(event["error"])
                    delta = event.get("message", {}).get("content", "")
                    if delta:
                        yield delta
                    if event.get("done"):
                        return


class ScriptedChat:
    """Replays a fixed reply one word at a time and records what it was asked.

    For tests: the interesting assertions are about what the router sends the
    model (the passages, the question, the bounded history) and how it relays
    the stream, and neither needs a real model.
    """

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[tuple[str, list[Turn]]] = []

    async def stream(self, system: str, messages: list[Turn]) -> AsyncIterator[str]:
        self.calls.append((system, messages))
        words = self.reply.split(" ")
        for i, word in enumerate(words):
            yield word if i == len(words) - 1 else f"{word} "


def get_chat_model() -> ChatModel:
    cfg = settings()
    return OllamaChat(cfg.ollama_host, cfg.chat_model)
