"""Documents and retrieval.

The properties that matter: a user only ever sees their own material, the
right passage ranks first, and a deleted document takes its chunks with it.
"""

from __future__ import annotations

import pytest

from app.ingest import chunk_text, extract_text
from tests.conftest import register

BIOLOGY = """# Cell biology

Mitochondria are the organelles that produce ATP through oxidative phosphorylation.
They have a double membrane and their own circular DNA.

## Photosynthesis

Chloroplasts capture light energy with chlorophyll and use it to fix carbon dioxide
into glucose. The light-dependent reactions happen in the thylakoid membranes.
"""

HISTORY = """The Treaty of Westphalia in 1648 ended the Thirty Years' War and is often
cited as the origin of the modern system of sovereign states."""

def make_pdf(text: str) -> bytes:
    """A one-page PDF with a Helvetica text layer.

    Built by hand so the test needs no fixture file. pypdf refuses a PDF
    without a correct xref table, so the offsets are computed rather than typed.
    """
    stream = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


TINY_PDF = make_pdf("Osmosis moves water across a membrane")


async def upload(client, name="notes.md", content=BIOLOGY, title=None):
    data = {"title": title} if title else {}
    body = content.encode() if isinstance(content, str) else content
    return await client.post("/documents", files={"file": (name, body)}, data=data)


class TestUpload:
    async def test_markdown_is_chunked_and_listed(self, signed_in):
        response = await upload(signed_in)
        assert response.status_code == 201
        body = response.json()
        assert body["title"] == "notes"
        assert body["media_type"] == "text/markdown"
        assert body["chunk_count"] >= 1

        listed = (await signed_in.get("/documents")).json()
        assert [d["id"] for d in listed] == [body["id"]]

    async def test_explicit_title_wins(self, signed_in):
        body = (await upload(signed_in, title="  Week 3 lecture ")).json()
        assert body["title"] == "Week 3 lecture"

    async def test_pdf_text_layer_is_extracted(self, signed_in):
        response = await upload(signed_in, name="slides.pdf", content=TINY_PDF)
        assert response.status_code == 201
        detail = (await signed_in.get(f"/documents/{response.json()['id']}")).json()
        assert "Osmosis" in detail["chunks"][0]["text"]

    async def test_unsupported_extension_is_415(self, signed_in):
        response = await upload(signed_in, name="deck.pptx", content=b"PK\x03\x04")
        assert response.status_code == 415
        assert ".pdf" in response.json()["detail"]

    async def test_empty_text_is_422(self, signed_in):
        response = await upload(signed_in, name="blank.txt", content="   \n\n  ")
        assert response.status_code == 422

    async def test_oversized_upload_is_413(self, signed_in, monkeypatch):
        from app import config

        monkeypatch.setattr(config.settings(), "max_upload_bytes", 100)
        response = await upload(signed_in, content="x" * 101)
        assert response.status_code == 413

    async def test_requires_sign_in(self, client):
        assert (await upload(client)).status_code == 401
        assert (await client.get("/documents")).status_code == 401


class TestScoping:
    async def test_another_users_document_is_invisible(self, client):
        await register(client, email="alice@x.com")
        alice_doc = (await upload(client)).json()["id"]

        client.cookies.clear()
        await register(client, email="bob@x.com")

        assert (await client.get("/documents")).json() == []
        assert (await client.get(f"/documents/{alice_doc}")).status_code == 404
        assert (await client.delete(f"/documents/{alice_doc}")).status_code == 404

    async def test_search_only_sees_own_chunks(self, client):
        await register(client, email="alice@x.com")
        await upload(client, content=BIOLOGY)

        client.cookies.clear()
        await register(client, email="bob@x.com")
        await upload(client, content=HISTORY)

        hits = (await client.get("/documents/search", params={"q": "mitochondria ATP"})).json()
        assert hits, "bob has one document, so search must return something"
        assert all("Westphalia" in h["text"] for h in hits)


class TestSearch:
    async def test_the_relevant_passage_ranks_first(self, signed_in):
        await upload(signed_in, name="bio.md", content=BIOLOGY)
        await upload(signed_in, name="hist.md", content=HISTORY)

        hits = (await signed_in.get("/documents/search", params={"q": "chlorophyll light energy"})).json()
        assert hits[0]["document_title"] == "bio"
        assert "chlorophyll" in hits[0]["text"]
        assert hits[0]["score"] > hits[-1]["score"]

    async def test_hits_carry_a_citation(self, signed_in):
        doc = (await upload(signed_in)).json()
        hit = (await signed_in.get("/documents/search", params={"q": "mitochondria"})).json()[0]
        assert hit["document_id"] == doc["id"]
        assert hit["chunk_id"]
        assert hit["position"] == 0

    async def test_delete_removes_chunks_from_search(self, signed_in):
        doc = (await upload(signed_in)).json()
        assert (await signed_in.delete(f"/documents/{doc['id']}")).status_code == 204
        assert (await signed_in.get("/documents/search", params={"q": "mitochondria"})).json() == []
        assert (await signed_in.get("/documents")).json() == []


class TestChunking:
    def test_short_text_is_one_chunk(self):
        assert chunk_text("Hello world.") == ["Hello world."]

    def test_paragraphs_pack_until_target(self):
        paragraphs = [f"Paragraph {i}. " + "word " * 40 for i in range(10)]
        chunks = chunk_text("\n\n".join(paragraphs), target=600, overlap=0)
        assert len(chunks) > 1
        assert all(len(c) <= 600 for c in chunks)

    def test_overlap_repeats_the_tail(self):
        text = "\n\n".join(f"Sentence number {i} ends here." for i in range(40))
        chunks = chunk_text(text, target=300, overlap=60)
        for previous, current in zip(chunks, chunks[1:], strict=False):
            tail = previous[-40:].split(" ", 1)[-1]
            assert tail in current

    def test_a_giant_paragraph_splits_on_sentences(self):
        text = " ".join(f"This is sentence {i}." for i in range(200))
        chunks = chunk_text(text, target=400, overlap=0)
        assert len(chunks) > 1
        assert all(c.endswith(".") for c in chunks)

    def test_overlap_must_be_smaller_than_target(self):
        with pytest.raises(ValueError):
            chunk_text("x", target=100, overlap=100)


class TestExtraction:
    def test_crlf_and_blank_runs_are_normalised(self):
        text = extract_text("a.txt", b"one\r\n\r\n\r\n\r\ntwo   \r\n")
        assert text == "one\n\ntwo"

    def test_non_utf8_falls_back_to_latin1(self):
        assert extract_text("a.txt", "caf\xe9".encode("latin-1")) == "café"

    def test_broken_pdf_is_unreadable(self):
        from app.ingest import UnreadableFile

        with pytest.raises(UnreadableFile):
            extract_text("a.pdf", b"%PDF-1.4 garbage")
