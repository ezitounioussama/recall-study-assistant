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

    async def complete(self, system: str, messages: list[Turn], *, json_mode: bool = False) -> str: ...


# Families that emit a reasoning block before the answer. Ollama can switch it
# off with `think: false`, but rejects the field for models that never think,
# so it is only sent when the model is one of these.
_THINKING_FAMILIES = ("qwen3", "deepseek-r1", "gpt-oss", "magistral")


class OllamaChat:
    """Ollama's /api/chat, and anything that speaks it.

    `api_key` is optional because a local Ollama has no auth. It is sent as a
    bearer token when present, which is what an OpenAI-compatible gateway
    (LiteLLM, a hosted endpoint) in front of it expects. The key arrives from
    settings, which read it from the environment — it is never a literal here,
    and it is never echoed back in a response or an error.
    """

    def __init__(self, host: str, model: str, *, api_key: str = "", timeout: float = 300.0) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = httpx.Timeout(timeout, connect=10)

    def _payload(self, system: str, messages: list[Turn], *, stream: bool) -> dict:
        payload: dict = {
            "model": self._model,
            "stream": stream,
            "messages": [{"role": "system", "content": system}, *messages],
            "options": {
                # Low temperature: this is "answer from the passages", not
                # creative writing, and a grounded answer should come out the
                # same twice.
                "temperature": 0.2,
                "num_ctx": 8192,
                # A cap on the reply. Without it a small model in JSON mode can
                # fail to close its object and generate until the read timeout —
                # a quiz request did exactly that. Study content is short; 2048
                # tokens is far more than any of these prompts should need.
                "num_predict": 2048,
            },
        }
        if self._model.split(":")[0] in _THINKING_FAMILIES:
            payload["think"] = False
        return payload

    async def complete(self, system: str, messages: list[Turn], *, json_mode: bool = False) -> str:
        payload = self._payload(system, messages, stream=False)
        if json_mode:
            # Ollama constrains decoding to valid JSON. Small models still
            # sometimes pick a different shape, so callers parse defensively.
            payload["format"] = "json"
        async with httpx.AsyncClient(timeout=self._timeout, headers=self._headers) as http:
            response = await http.post(f"{self._host}/api/chat", json=payload)
        response.raise_for_status()
        body = response.json()
        if "error" in body:
            raise RuntimeError(body["error"])
        return body["message"]["content"]

    async def stream(self, system: str, messages: list[Turn]) -> AsyncIterator[str]:
        payload = self._payload(system, messages, stream=True)

        async with httpx.AsyncClient(timeout=self._timeout, headers=self._headers) as http:
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

    async def complete(self, system: str, messages: list[Turn], *, json_mode: bool = False) -> str:
        self.calls.append((system, messages))
        return self.reply

    async def stream(self, system: str, messages: list[Turn]) -> AsyncIterator[str]:
        self.calls.append((system, messages))
        words = self.reply.split(" ")
        for i, word in enumerate(words):
            yield word if i == len(words) - 1 else f"{word} "


def get_chat_model() -> ChatModel:
    cfg = settings()
    return OllamaChat(
        cfg.ollama_host,
        cfg.chat_model,
        api_key=cfg.llm_api_key,
        timeout=cfg.llm_timeout_seconds,
    )
