"""Turning an upload into text, and text into chunks.

Pure functions. Nothing here touches the database or the network, which is
what makes the chunker testable with a string and the extractor testable with
a handful of bytes.
"""

from __future__ import annotations

import io
import re
from pathlib import PurePosixPath

from pypdf import PdfReader

# Decided by extension, not by the Content-Type the browser sends. Browsers
# disagree about what a .md file is (text/markdown, text/plain, or nothing),
# and the extension is the thing the user can see.
SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".pdf": "application/pdf",
}


class UnsupportedFile(ValueError):
    pass


class UnreadableFile(ValueError):
    pass


def media_type_for(filename: str) -> str:
    suffix = PurePosixPath(filename.lower()).suffix
    try:
        return SUPPORTED_EXTENSIONS[suffix]
    except KeyError:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedFile(f"Unsupported file type {suffix or '(none)'}. Use {supported}.") from None


def extract_text(filename: str, data: bytes) -> str:
    media_type = media_type_for(filename)

    if media_type == "application/pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [page.extract_text() or "" for page in reader.pages]
        except Exception as exc:  # pypdf raises a zoo of its own types
            raise UnreadableFile("Could not read this PDF.") from exc
        return _normalise("\n\n".join(pages))

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        # Latin-1 decodes anything; better a few wrong accents than a refusal.
        text = data.decode("latin-1")
    return _normalise(text)


def _normalise(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)  # trailing whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)  # runs of blank lines
    return text.strip()


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def chunk_text(text: str, *, target: int = 1800, overlap: int = 200) -> list[str]:
    """Split text into chunks of about `target` characters.

    Paragraphs are the unit. They are packed into a chunk until the next one
    would push it past `target`; a paragraph longer than `target` on its own is
    split at sentence boundaries. Each chunk after the first opens with the
    last `overlap` characters of the previous one, so a sentence that straddles
    a boundary is whole in at least one of them.
    """
    if overlap >= target:
        raise ValueError("overlap must be smaller than target")

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    pieces: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= target:
            pieces.append(paragraph)
        else:
            pieces.extend(_split_long(paragraph, target))

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}\n\n{piece}" if current else piece
        if len(candidate) <= target or not current:
            current = candidate
            continue
        chunks.append(current)
        current = _tail(current, overlap) + "\n\n" + piece if overlap else piece

    if current:
        chunks.append(current)
    return chunks


def _split_long(paragraph: str, target: int) -> list[str]:
    sentences = _SENTENCE_END.split(paragraph)
    out: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > target:
            # A single "sentence" longer than the target (a table, a code dump).
            # Hard-cut it; there is no better boundary to find.
            if current:
                out.append(current)
                current = ""
            out.extend(sentence[i : i + target] for i in range(0, len(sentence), target))
            continue
        candidate = f"{current} {sentence}" if current else sentence
        if len(candidate) <= target:
            current = candidate
        else:
            out.append(current)
            current = sentence
    if current:
        out.append(current)
    return out


def _tail(text: str, n: int) -> str:
    """The last `n` characters, snapped forward to a word boundary."""
    if len(text) <= n:
        return text
    cut = text[-n:]
    space = cut.find(" ")
    return cut[space + 1 :] if space != -1 else cut
