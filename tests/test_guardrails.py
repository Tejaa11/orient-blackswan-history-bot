"""Deterministic unit tests with synthetic passages and mocked model chains.

These tests never open the real PDF, vector database, or an Ollama connection.
They check the backend's error and citation boundaries, not model quality.
"""

from types import SimpleNamespace

import pytest

from history_bot.models import Evidence, GroundedDraft, SupportCheck
from history_bot.service import BotError, CatalogueBot, InputError, verified_citations


SYNTHETIC_QUOTE = "The catalogue prices were last updated on 1 January 2001."


class MockChain:
    """A recorded local stand-in for a LangChain structured-output runnable."""

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def invoke(self, payload):
        self.calls.append(payload)
        if self.error is not None:
            raise self.error
        return self.result


class MockStore:
    """Return synthetic documents; no embedding or persistence is involved."""

    def __init__(self, passages, error=None):
        self.passages = passages
        self.error = error
        self.calls = []

    def similarity_search_with_score(self, question, k):
        self.calls.append((question, k))
        if self.error is not None:
            raise self.error
        return [
            (
                SimpleNamespace(
                    page_content=passage["text"],
                    metadata={key: value for key, value in passage.items() if key not in {"text", "distance"}},
                ),
                passage["distance"],
            )
            for passage in self.passages
        ]


@pytest.fixture
def passage():
    return {
        "chunk_id": "synthetic-p007-c000",
        "source": "unit-fixture.pdf",
        "pdf_page": 7,
        "pdf_page_index": 6,
        "text": f"Synthetic test catalogue. {SYNTHETIC_QUOTE} Prices may change.",
        "distance": 0.1,
    }


@pytest.fixture
def draft(passage):
    return GroundedDraft(
        supported=True,
        answer="The prices were last updated on 1 January 2001.",
        evidence=[Evidence(chunk_id=passage["chunk_id"], quote=SYNTHETIC_QUOTE)],
    )


@pytest.fixture
def bot(passage, draft):
    # Bypass __init__ deliberately: a unit test must not validate a real index,
    # read the catalogue, inspect a local model, or establish a connection.
    instance = CatalogueBot.__new__(CatalogueBot)
    instance.settings = SimpleNamespace(retrieval_k=3)
    instance.store = MockStore([passage])
    instance.answer_chain = MockChain(result=draft)
    instance.verify_chain = MockChain(result=SupportCheck(fully_supported=True))
    return instance


@pytest.mark.parametrize("question", ["", "   \n\t", None, 42, "x" * 1501])
def test_invalid_question_is_rejected_before_retrieval_or_models(bot, question):
    with pytest.raises(InputError):
        bot.ask(question)
    assert bot.store.calls == []
    assert bot.answer_chain.calls == []
    assert bot.verify_chain.calls == []


def test_valid_answer_uses_exact_quote_and_retrieved_page_metadata(bot, passage):
    answer = bot.ask("  When were catalogue prices last updated?  ")

    assert answer.question == "When were catalogue prices last updated?"
    assert answer.supported is True
    assert answer.answer == "The prices were last updated on 1 January 2001."
    assert answer.citations == [
        {
            "chunk_id": passage["chunk_id"],
            "quote": SYNTHETIC_QUOTE,
            "source": "unit-fixture.pdf",
            "pdf_page": 7,
            "pdf_page_index": 6,
        }
    ]
    assert answer.citations[0]["quote"] in passage["text"]
    assert len(bot.answer_chain.calls) == 1
    assert len(bot.verify_chain.calls) == 1


@pytest.mark.parametrize(
    "chunk_id, quote",
    [
        ("invented-p099-c000", SYNTHETIC_QUOTE),
        ("synthetic-p007-c000", SYNTHETIC_QUOTE.replace("2001", "2002")),
        ("synthetic-p007-c000", SYNTHETIC_QUOTE.lower()),
        ("synthetic-p007-c000", "prices"),
    ],
    ids=["invented-chunk", "changed-fact", "not-literal", "too-short"],
)
def test_invalid_source_quote_is_rejected(passage, chunk_id, quote):
    invalid = GroundedDraft(
        supported=True,
        answer="A purported supported answer.",
        evidence=[Evidence(chunk_id=chunk_id, quote=quote)],
    )
    with pytest.raises(BotError, match="unverified source quotation"):
        verified_citations(invalid, [passage])


def test_supported_answer_without_evidence_is_an_error(passage):
    no_evidence = GroundedDraft(supported=True, answer="Uncited claim.", evidence=[])
    with pytest.raises(BotError, match="without supporting evidence"):
        verified_citations(no_evidence, [passage])


def test_unverified_citation_in_ask_is_an_error_not_an_abstention(bot):
    bot.answer_chain.result = GroundedDraft(
        supported=True,
        answer="An unsupported claim.",
        evidence=[Evidence(chunk_id="invented", quote=SYNTHETIC_QUOTE)],
    )
    with pytest.raises(BotError, match="unverified source quotation"):
        bot.ask("When were catalogue prices last updated?")
    assert bot.verify_chain.calls == []


def test_unsupported_model_draft_returns_exact_not_found_without_citations(bot):
    bot.answer_chain.result = GroundedDraft(
        supported=False, answer="I cannot find that answer in this document.", evidence=[]
    )
    answer = bot.ask("Who won a fictional election?")
    assert answer.answer == "Not found"
    assert answer.supported is False
    assert answer.citations == []
    assert answer.retrieved
    assert bot.verify_chain.calls == []


def test_semantic_verifier_rejection_returns_not_found_and_removes_citations(bot):
    bot.verify_chain.result = SupportCheck(fully_supported=False)
    answer = bot.ask("When were catalogue prices last updated?")
    assert answer.answer == "Not found"
    assert answer.supported is False
    assert answer.citations == []
    assert len(bot.verify_chain.calls) == 1


def test_failed_retrieval_is_an_operational_error_not_not_found(bot):
    bot.store.error = ConnectionError("Synthetic embedding outage")
    with pytest.raises(BotError, match="Retrieval failed"):
        bot.ask("When were catalogue prices last updated?")
    assert bot.answer_chain.calls == []


def test_empty_retrieval_is_an_operational_error_not_not_found(bot):
    bot.store.passages = []
    with pytest.raises(BotError, match="index returned no passages"):
        bot.ask("When were catalogue prices last updated?")
    assert bot.answer_chain.calls == []


@pytest.mark.parametrize("failing_chain", ["answer_chain", "verify_chain"])
def test_model_failure_is_an_operational_error_not_not_found(bot, failing_chain):
    getattr(bot, failing_chain).error = TimeoutError("Synthetic model timeout")
    with pytest.raises(BotError, match="language model request failed"):
        bot.ask("When were catalogue prices last updated?")
