"""Real PDF extraction tests on generated fixtures, without models or a database.

Every PDF and hash record is temporary. The provider catalogue is never opened,
and these tests do not make embedding or language-model requests.
"""

import json
from dataclasses import replace

import pymupdf
import pytest

from history_bot import ingest
from history_bot.config import Settings
from history_bot.errors import BotError


REPEATED_BODY = "Repeated body label: this ordinary catalogue section must remain on every page."
REPEATED_FOOTER = "Synthetic catalogue notice: all listed prices may change without prior notice."
UNIQUE_FOOTER = "A different notice appears only on the first page and must remain available."


@pytest.fixture
def synthetic_pdf(tmp_path):
    """Four pages; the repeated bottom-margin notice starts on PDF page two."""
    path = tmp_path / "synthetic-catalogue.pdf"
    with pymupdf.open() as pdf:
        for page_number in range(1, 5):
            page = pdf.new_page(width=700, height=1000)
            page.insert_text((40, 55), "SYNTHETIC HISTORY CATALOGUE", fontsize=12)
            page.insert_text((40, 140), f"Page {page_number}: a distinct book entry for this page.", fontsize=11)
            page.insert_text((40, 190), REPEATED_BODY, fontsize=10)
            # Insertion order deliberately differs from left-to-right row order.
            page.insert_text((390, 270), "Right column was inserted first.", fontsize=10)
            page.insert_text((40, 270), "Left column was inserted second.", fontsize=10)
            footer = UNIQUE_FOOTER if page_number == 1 else REPEATED_FOOTER
            page.insert_text((40, 975), footer, fontsize=9)
        pdf.save(path)
    return path


def test_repeated_footer_is_canonical_but_every_page_body_is_preserved(synthetic_pdf):
    documents = ingest.extract_pages(synthetic_pdf)
    footers = [doc for doc in documents if doc.metadata.get("chunk_type") == "repeated_footer"]
    bodies = [doc for doc in documents if doc.metadata.get("chunk_type") != "repeated_footer"]

    assert len(footers) == 1
    footer = footers[0]
    assert footer.page_content == REPEATED_FOOTER
    # Reference the earliest actual occurrence, not the start of the document.
    assert footer.metadata["pdf_page"] == 2
    assert footer.metadata["pdf_page_index"] == 1
    assert footer.metadata["source"] == synthetic_pdf.name
    assert footer.metadata["repeated_pdf_pages"] == "2,3,4"
    assert sum(REPEATED_FOOTER in doc.page_content for doc in documents) == 1

    assert [doc.metadata["pdf_page"] for doc in bodies] == [1, 2, 3, 4]
    for page_number, body in enumerate(bodies, start=1):
        assert "SYNTHETIC HISTORY CATALOGUE" in body.page_content
        assert f"Page {page_number}: a distinct book entry" in body.page_content
        # Repetition alone must never remove an ordinary body block.
        assert REPEATED_BODY in body.page_content
        assert body.metadata["pdf_page_index"] == page_number - 1
        assert body.page_content.index("Right column was inserted first.") < body.page_content.index(
            "Left column was inserted second."
        )
    assert UNIQUE_FOOTER in bodies[0].page_content


def test_body_and_canonical_footer_get_unique_stable_chunk_ids(synthetic_pdf, tmp_path):
    documents = ingest.extract_pages(synthetic_pdf)
    settings = Settings(
        pdf_path=synthetic_pdf,
        index_dir=tmp_path / "unused-index",
        chunk_size=200,
        chunk_overlap=25,
    )
    digest = ingest.sha256_file(synthetic_pdf)
    chunks = ingest.make_chunks(documents, settings, digest)
    ids = [chunk.metadata["chunk_id"] for chunk in chunks]

    assert len(ids) == len(set(ids))
    assert all(chunk.id == chunk.metadata["chunk_id"] for chunk in chunks)
    assert all(chunk.metadata["source"] == synthetic_pdf.name for chunk in chunks)
    assert all(chunk.metadata["sha256"] == digest for chunk in chunks)
    assert {chunk.metadata["pdf_page"] for chunk in chunks} == {1, 2, 3, 4}

    canonical = [chunk for chunk in chunks if chunk.metadata.get("chunk_type") == "repeated_footer"]
    assert len(canonical) == 1
    assert canonical[0].page_content == REPEATED_FOOTER
    assert canonical[0].metadata["pdf_page"] == 2
    assert canonical[0].metadata["repeated_pdf_pages"] == "2,3,4"
    assert any(
        chunk.metadata["pdf_page"] == 2 and chunk.metadata.get("chunk_type") != "repeated_footer"
        for chunk in chunks
    )

    # Running the pure extraction/chunking stages again produces identical IDs.
    rerun = ingest.make_chunks(ingest.extract_pages(synthetic_pdf), settings, digest)
    assert [chunk.metadata["chunk_id"] for chunk in rerun] == ids


def test_source_hash_record_rejects_changed_pdf(synthetic_pdf, tmp_path, monkeypatch):
    # Keep the source record under a temporary ROOT; never touch submission data.
    monkeypatch.setattr(ingest, "ROOT", tmp_path)
    record = tmp_path / "data" / "catalogue_source.json"
    record.parent.mkdir()
    record.write_text(json.dumps({"sha256": ingest.sha256_file(synthetic_pdf)}))
    settings = Settings(pdf_path=synthetic_pdf, index_dir=tmp_path / "unused-index")

    ingest.check_source_hash(settings)
    with synthetic_pdf.open("ab") as stream:
        stream.write(b"\n% synthetic source changed\n")

    with pytest.raises(BotError, match="hash differs"):
        ingest.check_source_hash(settings)


@pytest.mark.parametrize(
    "field, value",
    [
        ("embedding_model", "different-test-embedding"),
        ("chunk_size", 400),
        ("chunk_overlap", 10),
    ],
)
def test_index_signature_changes_with_embedding_or_chunk_configuration(tmp_path, field, value):
    settings = Settings(pdf_path=tmp_path / "synthetic.pdf", chunk_size=200, chunk_overlap=25)
    original = ingest.index_signature(settings, "a" * 64, "mock-embedding-digest")
    changed = ingest.index_signature(replace(settings, **{field: value}), "a" * 64, "mock-embedding-digest")

    assert changed != original
    assert changed[field] == value


def test_index_signature_changes_when_model_weights_change(tmp_path):
    settings = Settings(pdf_path=tmp_path / "synthetic.pdf")
    before = ingest.index_signature(settings, "a" * 64, "mock-model-version-one")
    after = ingest.index_signature(settings, "a" * 64, "mock-model-version-two")
    assert before != after
    assert before["embedding_model"] == after["embedding_model"]
