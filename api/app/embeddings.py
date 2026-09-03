"""Text to vectors.

Two implementations behind one small interface. The Ollama one is the product;
the hash one is for tests, where a 300 MB model download is not an acceptable
prerequisite for `pytest`.
"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

import httpx
import numpy as np

from app.config import settings


class Embedder(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[np.ndarray]: ...

    async def embed_query(self, text: str) -> np.ndarray: ...


class OllamaEmbedder:
    """nomic-embed-text through Ollama's /api/embed.

    nomic is trained with task prefixes, and the published guidance is that
    retrieval quality drops without them: documents are embedded as
    `search_document: ...` and queries as `search_query: ...`. They are added
    here so callers never have to remember.
    """

    def __init__(self, host: str, model: str) -> None:
        self._host = host.rstrip("/")
        self._model = model

    async def _embed(self, inputs: list[str]) -> list[np.ndarray]:
        async with httpx.AsyncClient(timeout=120) as http:
            response = await http.post(
                f"{self._host}/api/embed", json={"model": self._model, "input": inputs}
            )
        response.raise_for_status()
        vectors = response.json()["embeddings"]
        return [_unit(np.asarray(v, dtype=np.float32)) for v in vectors]

    async def embed_documents(self, texts: list[str]) -> list[np.ndarray]:
        out: list[np.ndarray] = []
        # Batches keep a large upload from becoming one enormous request.
        for start in range(0, len(texts), 16):
            batch = [f"search_document: {t}" for t in texts[start : start + 16]]
            out.extend(await self._embed(batch))
        return out

    async def embed_query(self, text: str) -> np.ndarray:
        return (await self._embed([f"search_query: {text}"]))[0]


class HashEmbedder:
    """A deterministic bag-of-words embedder with no model behind it.

    Each word is hashed to one of `dimensions` buckets and the vector is the
    normalised bucket count. Two texts that share words score high; two that
    do not score near zero. That is enough to test that retrieval ranks,
    scopes, and cites correctly. It knows nothing about meaning, which is why
    it is not the default.
    """

    # Large enough that two unrelated short texts almost never share a bucket.
    dimensions = 4096

    async def embed_documents(self, texts: list[str]) -> list[np.ndarray]:
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> np.ndarray:
        return self._vector(text)

    def _vector(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dimensions, dtype=np.float32)
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            digest = hashlib.blake2b(word.encode(), digest_size=4).digest()
            vec[int.from_bytes(digest, "little") % self.dimensions] += 1.0
        return _unit(vec)


def _unit(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm else vec


def get_embedder() -> Embedder:
    cfg = settings()
    if cfg.embedding_provider == "hash":
        return HashEmbedder()
    return OllamaEmbedder(cfg.ollama_host, cfg.embedding_model)


def pack(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def unpack(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)
