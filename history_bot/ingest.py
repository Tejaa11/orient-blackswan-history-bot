"""Explicit, repeat-safe ingestion. Questions never parse or embed the PDF again."""
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import pymupdf
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import CATALOGUE_URL, ROOT, Settings
from .errors import BotError
from .providers import CatalogueEmbeddings, embedding_identity, provider_error

EXTRACTION_VERSION = "pymupdf-native-blocks-canonical-footers-v2"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(".tmp")
    staging.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    staging.replace(path)


def download_catalogue(settings: Settings):
    """The exact assignment URL, verified against the recorded snapshot if present."""
    target = settings.pdf_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        check_source_hash(settings)
        return {"status": "already_present", "sha256": sha256_file(target)}
    staging = target.with_suffix(".pdf.part")
    try:
        request = Request(CATALOGUE_URL, headers={"User-Agent": "HistoryCatalogueMidterm/1.0"})
        with urlopen(request, timeout=600) as response, staging.open("wb") as output:
            while part := response.read(1024 * 1024):
                output.write(part)
        with pymupdf.open(staging, filetype="pdf") as pdf:
            if not pdf.page_count:
                raise ValueError("Empty PDF")
        record_path = ROOT / "data/catalogue_source.json"
        digest = sha256_file(staging)
        if record_path.exists() and digest != json.loads(record_path.read_text())["sha256"]:
            raise BotError("The publisher's PDF differs from the recorded submission snapshot. Inspect the edition before replacing it.")
        staging.replace(target)
        return {"status": "downloaded", "sha256": digest, "url": CATALOGUE_URL}
    except BotError:
        raise
    except Exception as exc:
        raise BotError(f"Catalogue download failed: {exc}") from exc
    finally:
        staging.unlink(missing_ok=True)


def check_source_hash(settings: Settings):
    if not settings.pdf_path.is_file():
        raise BotError("Catalogue PDF is missing. Run: python -m history_bot download")
    record_path = ROOT / "data/catalogue_source.json"
    if record_path.exists():
        expected = json.loads(record_path.read_text())["sha256"]
        if sha256_file(settings.pdf_path) != expected:
            raise BotError("Catalogue hash differs from the recorded 2024–25 snapshot. Check the PDF; no edition substitution is automatic.")


def extract_pages(path: Path) -> list[Document]:
    """Keep native block order, not row sorting that interleaves adjacent columns.

    Block order was inspected on front matter and the catalogue's book listings.
    Do not remove short blocks: these include price notices, headings, and footers.
    Whitespace is normalized per block; quotation validation uses this same text.
    """
    pages = []
    records = []
    with pymupdf.open(path) as pdf:
        for i, page in enumerate(pdf):
            blocks = page.get_text("blocks", sort=False)
            text_blocks = [(" ".join(b[4].split()), b[1] >= .94 * page.rect.height)
                           for b in blocks if b[6] == 0 and b[4].strip()]
            records.append((i, page.get_label() or str(i + 1), text_blocks))
    # Exact repeated margin text flooded vector search in the baseline. Canonicalize
    # footers generically by position and repetition, never by assessment keywords.
    counts = Counter(text for _, _, blocks in records for text, footer in blocks if footer and len(text) >= 40)
    repeated = {text for text, count in counts.items() if count >= 3}
    locations = {text: [i + 1 for i, _, blocks in records if any(t == text and footer for t, footer in blocks)] for text in repeated}
    for i, label, blocks in records:
        metadata = {"source": path.name, "pdf_page_index": i, "pdf_page": i + 1, "pdf_page_label": label}
        text = "\n\n".join(t for t, footer in blocks if not (footer and t in repeated))
        if text:
            pages.append(Document(page_content=text, metadata=metadata))
        for footer in sorted(repeated):
            if locations[footer][0] == i + 1:
                pages.append(Document(page_content=footer, metadata={
                    **metadata, "chunk_type": "repeated_footer",
                    "repeated_pdf_pages": ",".join(map(str, locations[footer])),
                }))
    if not pages:
        raise BotError("PDF has no extractable text. This pipeline does not perform OCR.")
    return pages


def make_chunks(pages: list[Document], settings: Settings, digest: str):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", ". ", "\n", " ", ""], add_start_index=True,
    )
    chunks = []
    page_counters = defaultdict(int)
    for page in pages:
        for chunk in splitter.split_documents([page]):
            i = page_counters[page.metadata["pdf_page"]]
            page_counters[page.metadata["pdf_page"]] += 1
            chunk_id = f"{digest[:12]}-p{page.metadata['pdf_page']:03d}-c{i:03d}"
            chunk.metadata.update({"chunk_id": chunk_id, "chunk_index": i, "sha256": digest})
            chunk.id = chunk_id
            chunks.append(chunk)
    return chunks


def index_signature(settings: Settings, digest: str, embedding_digest: str):
    return {
        "source": settings.pdf_path.name, "sha256": digest,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model, "embedding_digest": embedding_digest,
        "embedding_dimensions": settings.embedding_dimensions if settings.embedding_provider == "gemini" else "model-default",
        "embedding_prefixes": "google-retrieval-v1" if settings.embedding_provider == "gemini" else ("nomic-search-v1" if settings.embedding_model.startswith("nomic-embed-text") else "none"),
        "chunk_size": settings.chunk_size, "chunk_overlap": settings.chunk_overlap,
        "extraction_version": EXTRACTION_VERSION,
    }


def open_store(settings: Settings, collection: str):
    try:
        return Chroma(
            collection_name=collection, persist_directory=str(settings.index_dir / "chroma"),
            embedding_function=CatalogueEmbeddings(settings),
            collection_metadata={"hnsw:space": "cosine"},
        )
    except BotError:
        raise
    except Exception:
        raise BotError("Could not initialize Chroma or the embedding provider. Check configuration, dependencies, and index permissions.") from None


def ingest(settings: Settings, rebuild=False):
    check_source_hash(settings)
    digest = sha256_file(settings.pdf_path)
    signature = index_signature(settings, digest, embedding_identity(settings))
    collection = "history_" + hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()[:24]
    manifest_path = settings.index_dir / "manifest.json"
    old = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    store = open_store(settings, collection)
    if old and old.get("signature") == signature and not rebuild:
        if store._collection.count() != old["chunk_count"]:
            raise BotError("Index is incomplete. Stop the app, then run: python -m history_bot ingest --rebuild")
        return {**old, "status": "unchanged; reused existing index"}
    if rebuild:
        store.delete_collection()
        store = open_store(settings, collection)
    pages = extract_pages(settings.pdf_path)
    chunks = make_chunks(pages, settings, digest)
    # The fingerprint identifies the exact source/model/config. Reuse successful
    # batches after interruptions instead of paying to embed those chunks again.
    existing_ids = set(store.get(include=[])["ids"])
    missing = [chunk for chunk in chunks if chunk.metadata["chunk_id"] not in existing_ids]
    for start in range(0, len(missing), 32):
        batch = missing[start:start + 32]
        try:
            store.add_documents(batch, ids=[d.metadata["chunk_id"] for d in batch])
        except BotError:
            raise
        except Exception as exc:
            raise provider_error("Catalogue indexing", settings.embedding_provider, exc) from None
    if store._collection.count() != len(chunks):
        raise BotError("Ingested chunk count does not match extraction. Rebuild the index.")
    with pymupdf.open(settings.pdf_path) as pdf:
        total_pages = pdf.page_count
        text_pages = sum(bool(page.get_text().strip()) for page in pdf)
    info = {
        **signature, "signature": signature, "collection": collection,
        "page_count": total_pages, "text_page_count": text_pages, "chunk_count": len(chunks),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    extracted = ROOT / "data/extracted"
    extracted.mkdir(parents=True, exist_ok=True)
    (extracted / "pages.jsonl").write_text("".join(
        json.dumps({**p.metadata, "text": p.page_content}, ensure_ascii=False) + "\n" for p in pages
    ))
    (extracted / "chunks.jsonl").write_text("".join(
        json.dumps({**p.metadata, "text": p.page_content}, ensure_ascii=False) + "\n" for p in chunks
    ))
    write_json(manifest_path, info)  # Mark ready only after every batch succeeds.
    return {**info, "status": "indexed"}
