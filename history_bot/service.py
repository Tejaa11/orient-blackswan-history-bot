"""Retrieval, grounded generation, and backend-verified citations."""
import json
from time import perf_counter

from .config import Settings
from .errors import BotError, InputError
from .ingest import check_source_hash, index_signature, open_store, sha256_file
from .models import Answer, GroundedDraft, SupportCheck
from .prompts import ANSWER_PROMPT, VERIFY_PROMPT
from .providers import call_provider, chat_model, chat_identity, embedding_identity, provider_error


def validate_question(question: str):
    if not isinstance(question, str) or not question.strip():
        raise InputError("Enter a question about the catalogue.")
    if len(question) > 1500:
        raise InputError("Please keep your question under 1,500 characters.")
    return question.strip()


def verified_citations(draft: GroundedDraft, retrieved: list[dict]) -> list[dict]:
    by_id = {p["chunk_id"]: p for p in retrieved}
    if not draft.evidence or not draft.answer.strip():
        raise BotError("The model returned an answer without supporting evidence. Please retry.")
    citations = []
    for evidence in draft.evidence:
        passage = by_id.get(evidence.chunk_id)
        # Literal substring: no fuzzy matching or invented ellipses are accepted.
        if passage is None or len(evidence.quote.strip()) < 16 or evidence.quote not in passage["text"]:
            raise BotError("The model returned an unverified source quotation. Please retry.")
        citation = {
            "chunk_id": evidence.chunk_id, "quote": evidence.quote,
            "source": passage["source"], "pdf_page": passage["pdf_page"],
            "pdf_page_index": passage["pdf_page_index"],
        }
        if citation not in citations:
            citations.append(citation)
    return citations


class CatalogueBot:
    def __init__(self, settings: Settings):
        self.settings = settings
        try:
            manifest_path = settings.index_dir / "manifest.json"
            if not manifest_path.is_file():
                raise BotError("Index not found. Run: python -m history_bot ingest")
            self.info = json.loads(manifest_path.read_text())
            check_source_hash(settings)
            signature = index_signature(settings, sha256_file(settings.pdf_path), embedding_identity(settings))
            if self.info.get("signature") != signature:
                raise BotError("The PDF or embedding/chunk configuration changed. Run ingestion again before asking.")
            self.store = open_store(settings, self.info["collection"])
            if self.store._collection.count() != self.info["chunk_count"]:
                raise BotError("Index is incomplete or damaged. Stop the app and rebuild the index.")
            self.chat_digest = chat_identity(settings)
            model = chat_model(settings)
            self.answer_chain = ANSWER_PROMPT | model.with_structured_output(GroundedDraft, method="json_schema")
            self.verify_chain = VERIFY_PROMPT | model.with_structured_output(SupportCheck, method="json_schema")
        except BotError:
            raise
        except Exception:
            raise BotError("Could not open the catalogue index or configure the model. Check configuration and rebuild if necessary.") from None

    def retrieve(self, question: str):
        question = validate_question(question)
        try:
            hits = self.store.similarity_search_with_score(question, k=self.settings.retrieval_k)
            return [
                {**doc.metadata, "text": doc.page_content, "distance": float(distance)}
                for doc, distance in hits
            ]
        except BotError:
            raise
        except Exception as exc:
            raise provider_error("Retrieval", getattr(self.settings, 'embedding_provider', 'ollama'), exc) from None

    def ask(self, question: str) -> Answer:
        question = validate_question(question)
        started = perf_counter()
        retrieved = self.retrieve(question)
        if not retrieved:
            # A populated, validated index must return candidates even for unrelated queries.
            raise BotError("The index returned no passages. Check the database before continuing.")
        context = [{"chunk_id": p["chunk_id"], "text": p["text"]} for p in retrieved]
        try:
            draft = call_provider(
                lambda: self.answer_chain.invoke({"question": question, "context": json.dumps(context, ensure_ascii=False)}),
                getattr(self.settings, 'chat_provider', 'ollama'), "The language model request",
            )
            citations = []
            supported = draft.supported
            if supported:
                citations = verified_citations(draft, retrieved)
                verify_input = {
                    "question": question, "answer": draft.answer,
                    "evidence": json.dumps([
                        {**c, "full_passage": next(p['text'] for p in retrieved if p['chunk_id'] == c['chunk_id'])}
                        for c in citations
                    ], ensure_ascii=False),
                }
                check = call_provider(
                    lambda: self.verify_chain.invoke(verify_input),
                    getattr(self.settings, 'chat_provider', 'ollama'), "The language model request",
                )
                supported = check.fully_supported
            return Answer(
                question=question, answer=draft.answer.strip() if supported else "Not found",
                supported=supported, citations=citations if supported else [], retrieved=retrieved,
                elapsed_seconds=round(perf_counter() - started, 3),
            )
        except BotError:
            raise
        except Exception as exc:
            raise provider_error("The language model request", getattr(self.settings, 'chat_provider', 'ollama'), exc) from None
