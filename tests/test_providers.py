"""Provider/configuration boundaries using mocked SDKs; no network or real index.

Dummy credentials below exist only to verify that failures and cache metadata do
not expose their contents. These tests do not establish Gemini model quality.
"""

import os
import traceback
from dataclasses import replace
from unittest.mock import Mock

import langchain_google_genai
import pytest
from langchain_core.documents import Document
from pydantic import SecretStr

from history_bot import config, ingest, providers
from history_bot.config import Settings
from history_bot.errors import BotError
from history_bot.service import CatalogueBot


DUMMY_KEY = "dummy-provider-test-key-never-a-real-credential"


@pytest.fixture(autouse=True)
def prohibit_provider_connections(monkeypatch):
    """Unexpected real-provider construction must fail before opening a client."""
    for module, attribute in [
        (providers, "Client"),
        (providers, "OllamaEmbeddings"),
        (providers, "ChatOllama"),
        (langchain_google_genai, "GoogleGenerativeAIEmbeddings"),
        (langchain_google_genai, "ChatGoogleGenerativeAI"),
    ]:
        monkeypatch.setattr(module, attribute, Mock(side_effect=AssertionError("Unexpected provider connection")))


@pytest.fixture
def gemini_settings(tmp_path):
    return Settings(
        pdf_path=tmp_path / "synthetic.pdf",
        index_dir=tmp_path / "index",
        chat_provider="gemini",
        embedding_provider="gemini",
        chat_model=config.GEMINI_CHAT_MODEL,
        embedding_model=config.GEMINI_EMBEDDING_MODEL,
        gemini_api_key=SecretStr(DUMMY_KEY),
        embedding_dimensions=768,
        model_timeout=23,
    )


@pytest.mark.parametrize("operation", [
    providers.require_gemini_key,
    providers.embedding_identity,
    providers.chat_identity,
    providers.CatalogueEmbeddings,
    providers.chat_model,
])
@pytest.mark.parametrize("key", [None, SecretStr("   ")], ids=["missing", "blank"])
def test_missing_gemini_key_is_an_operational_error_without_sdk_calls(gemini_settings, operation, key):
    with pytest.raises(BotError, match="Gemini API key is missing"):
        operation(replace(gemini_settings, gemini_api_key=key))
    providers.Client.assert_not_called()
    langchain_google_genai.GoogleGenerativeAIEmbeddings.assert_not_called()
    langchain_google_genai.ChatGoogleGenerativeAI.assert_not_called()


def test_gemini_identities_describe_hosted_configuration_without_local_model_lookup(gemini_settings):
    assert providers.embedding_identity(gemini_settings) == (
        f"gemini-api:{gemini_settings.embedding_model}:dimensions=768:retrieval-v1"
    )
    assert providers.chat_identity(gemini_settings) == f"gemini-api:{gemini_settings.chat_model}"
    providers.Client.assert_not_called()


def test_gemini_embedding_factory_and_retrieval_tasks(monkeypatch, gemini_settings):
    backend = Mock()
    backend.embed_documents.return_value = [[0.2, 0.8], [0.4, 0.6]]
    backend.embed_query.return_value = [0.3, 0.7]
    factory = Mock(return_value=backend)
    monkeypatch.setattr(langchain_google_genai, "GoogleGenerativeAIEmbeddings", factory)

    embeddings = providers.CatalogueEmbeddings(gemini_settings)
    assert embeddings.embed_documents(["A title", "Another title"]) == [[0.2, 0.8], [0.4, 0.6]]
    assert embeddings.embed_query("Who wrote the title?") == [0.3, 0.7]
    factory.assert_called_once_with(
        model=gemini_settings.embedding_model,
        api_key=gemini_settings.gemini_api_key,
        vertexai=False,
        output_dimensionality=768,
    )
    backend.embed_documents.assert_called_once_with(
        ["A title", "Another title"], task_type="RETRIEVAL_DOCUMENT"
    )
    backend.embed_query.assert_called_once_with("Who wrote the title?", task_type="RETRIEVAL_QUERY")
    providers.Client.assert_not_called()
    providers.OllamaEmbeddings.assert_not_called()


def test_gemini_chat_factory_has_explicit_auth_backend_and_bounded_requests(monkeypatch, gemini_settings):
    backend = object()
    factory = Mock(return_value=backend)
    monkeypatch.setattr(langchain_google_genai, "ChatGoogleGenerativeAI", factory)

    assert providers.chat_model(gemini_settings) is backend
    factory.assert_called_once_with(
        model=gemini_settings.chat_model,
        api_key=gemini_settings.gemini_api_key,
        vertexai=False,
        max_tokens=2048,
        max_retries=1,
        timeout=23,
    )
    providers.Client.assert_not_called()
    providers.ChatOllama.assert_not_called()


def test_ollama_embeddings_retain_nomic_document_and_query_prefixes(monkeypatch):
    backend = Mock()
    factory = Mock(return_value=backend)
    monkeypatch.setattr(providers, "OllamaEmbeddings", factory)
    settings = Settings(model_timeout=17)
    embeddings = providers.CatalogueEmbeddings(settings)

    embeddings.embed_documents(["A title"])
    embeddings.embed_query("Who wrote it?")
    factory.assert_called_once_with(
        model=settings.embedding_model,
        base_url=settings.base_url,
        client_kwargs={"timeout": 17},
    )
    backend.embed_documents.assert_called_once_with(["search_document: A title"])
    backend.embed_query.assert_called_once_with("search_query: Who wrote it?")
    langchain_google_genai.GoogleGenerativeAIEmbeddings.assert_not_called()


def assert_sanitized_error(exc):
    assert isinstance(exc, BotError)
    assert "Not found" not in str(exc)
    assert DUMMY_KEY not in str(exc)
    assert DUMMY_KEY not in "".join(traceback.format_exception(exc))


@pytest.mark.parametrize("operation", ["embed_documents", "embed_query"])
def test_gemini_embedding_failures_are_sanitized_operational_errors(monkeypatch, gemini_settings, operation):
    backend = Mock()
    getattr(backend, operation).side_effect = RuntimeError(f"Request URL contained key={DUMMY_KEY}")
    monkeypatch.setattr(langchain_google_genai, "GoogleGenerativeAIEmbeddings", Mock(return_value=backend))
    embeddings = providers.CatalogueEmbeddings(gemini_settings)

    with pytest.raises(BotError) as error:
        getattr(embeddings, operation)(["Synthetic passage"] if operation == "embed_documents" else "Question?")
    assert_sanitized_error(error.value)


@pytest.mark.parametrize("stage", ["retrieve", "ask"])
def test_gemini_bot_request_failure_stays_error_and_hides_raw_exception(gemini_settings, stage):
    bot = CatalogueBot.__new__(CatalogueBot)
    bot.settings = gemini_settings
    bot.store = Mock()
    bot.answer_chain = Mock()
    raw_error = RuntimeError(f"Request failed with key={DUMMY_KEY}")
    if stage == "retrieve":
        bot.store.similarity_search_with_score.side_effect = raw_error
    else:
        bot.retrieve = Mock(return_value=[{"chunk_id": "synthetic-1", "text": "A synthetic catalogue passage."}])
        bot.answer_chain.invoke.side_effect = raw_error

    with pytest.raises(BotError) as error:
        getattr(bot, stage)("Who wrote this book?")
    assert_sanitized_error(error.value)


def test_ingestion_provider_failure_does_not_publish_ready_manifest(monkeypatch, gemini_settings):
    monkeypatch.setattr(ingest, "check_source_hash", Mock())
    monkeypatch.setattr(ingest, "sha256_file", Mock(return_value="a" * 64))
    monkeypatch.setattr(ingest, "extract_pages", Mock(return_value=[Document(
        page_content="A synthetic passage.", metadata={"pdf_page": 1}
    )]))
    store = Mock()
    store.get.return_value = {"ids": []}
    store.add_documents.side_effect = RuntimeError(f"Request failed with key={DUMMY_KEY}")
    monkeypatch.setattr(ingest, "open_store", Mock(return_value=store))

    with pytest.raises(BotError) as error:
        ingest.ingest(gemini_settings)
    assert_sanitized_error(error.value)
    assert not (gemini_settings.index_dir / "manifest.json").exists()


def test_interrupted_ingestion_resumes_only_missing_chunks_and_stays_unready_on_failure(monkeypatch, gemini_settings):
    completed = Document(page_content="Previously embedded passage.", metadata={"chunk_id": "synthetic-completed"})
    pending = Document(page_content="Passage still needing an embedding.", metadata={"chunk_id": "synthetic-pending"})
    monkeypatch.setattr(ingest, "check_source_hash", Mock())
    monkeypatch.setattr(ingest, "sha256_file", Mock(return_value="a" * 64))
    monkeypatch.setattr(ingest, "extract_pages", Mock(return_value=[]))
    monkeypatch.setattr(ingest, "make_chunks", Mock(return_value=[completed, pending]))
    store = Mock()
    store.get.return_value = {"ids": [completed.metadata["chunk_id"]]}
    store.add_documents.side_effect = RuntimeError(f"Transient provider failure containing key={DUMMY_KEY}")
    monkeypatch.setattr(ingest, "open_store", Mock(return_value=store))

    with pytest.raises(BotError) as error:
        ingest.ingest(gemini_settings)
    assert_sanitized_error(error.value)
    store.get.assert_called_once_with(include=[])
    store.add_documents.assert_called_once_with([pending], ids=[pending.metadata["chunk_id"]])
    store.delete_collection.assert_not_called()
    store._collection.count.assert_not_called()
    assert not (gemini_settings.index_dir / "manifest.json").exists()


@pytest.mark.parametrize("code, attribute, expected_detail", [
    (401, "code", "credential"),
    (429, "status_code", "quota"),
])
@pytest.mark.parametrize("wrapped", [False, True], ids=["direct", "wrapped"])
def test_provider_status_classification_preserves_actionable_code_without_raw_error(
    monkeypatch, gemini_settings, code, attribute, expected_detail, wrapped
):
    original = RuntimeError(f"Remote request URL contained key={DUMMY_KEY}")
    setattr(original, attribute, code)
    failure = original
    if wrapped:
        failure = RuntimeError(f"SDK wrapper also included key={DUMMY_KEY}")
        failure.__cause__ = original
    backend = Mock()
    backend.embed_query.side_effect = failure
    monkeypatch.setattr(langchain_google_genai, "GoogleGenerativeAIEmbeddings", Mock(return_value=backend))

    with pytest.raises(BotError) as error:
        providers.CatalogueEmbeddings(gemini_settings).embed_query("Synthetic question?")
    assert_sanitized_error(error.value)
    assert error.value.provider_code == code
    assert expected_detail in str(error.value).lower()


def test_provider_error_walk_handles_exception_context_cycles_without_leaking_messages():
    first = RuntimeError(f"SDK message with key={DUMMY_KEY}")
    second = RuntimeError("Cyclic SDK wrapper")
    first.__context__ = second
    second.__context__ = first
    error = providers.provider_error("Query embedding", "gemini", first)
    assert_sanitized_error(error)
    assert error.provider_code is None


def test_embedding_client_setup_failure_is_sanitized_before_store_opens(monkeypatch, gemini_settings):
    monkeypatch.setattr(
        langchain_google_genai,
        "GoogleGenerativeAIEmbeddings",
        Mock(side_effect=RuntimeError(f"Client setup contained key={DUMMY_KEY}")),
    )
    chroma = Mock()
    monkeypatch.setattr(ingest, "Chroma", chroma)

    with pytest.raises(BotError) as error:
        ingest.open_store(gemini_settings, "synthetic-test-collection")
    assert_sanitized_error(error.value)
    chroma.assert_not_called()


def test_embedding_provider_and_dimensions_isolate_index_signatures(gemini_settings):
    digest = "a" * 64
    # Hold the identity argument constant so provider/dimension fields themselves
    # must distinguish the signatures, even if two models share a name.
    signature = ingest.index_signature(gemini_settings, digest, "synthetic-identity")
    ollama = ingest.index_signature(
        replace(gemini_settings, embedding_provider="ollama"), digest, "synthetic-identity"
    )
    reduced = ingest.index_signature(
        replace(gemini_settings, embedding_dimensions=256), digest, "synthetic-identity"
    )
    assert signature != ollama
    assert signature != reduced
    assert signature["embedding_provider"] == "gemini"
    assert signature["embedding_dimensions"] == 768
    assert signature["embedding_prefixes"] == "google-retrieval-v1"


def test_changing_chat_provider_or_key_does_not_change_embedding_signature(gemini_settings):
    digest = "a" * 64
    signature = ingest.index_signature(gemini_settings, digest, providers.embedding_identity(gemini_settings))
    other = replace(
        gemini_settings,
        chat_provider="ollama",
        chat_model="synthetic-local-chat",
        gemini_api_key=SecretStr("different-dummy-credential"),
    )
    assert signature == ingest.index_signature(other, digest, providers.embedding_identity(other))


@pytest.fixture
def isolated_environment(monkeypatch, tmp_path):
    # Only these names belong to this application's configuration. Keep unrelated
    # process environment in place so the test itself does not need a live shell.
    for name in [
        "CHAT_PROVIDER", "EMBEDDING_PROVIDER", "CHAT_MODEL", "EMBEDDING_MODEL",
        "GEMINI_API_KEY", "GOOGLE_API_KEY", "EMBEDDING_DIMENSIONS", "OLLAMA_BASE_URL",
        "CATALOGUE_PATH", "INDEX_DIR", "CHUNK_SIZE", "CHUNK_OVERLAP", "RETRIEVAL_K", "MODEL_TIMEOUT",
    ]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "ROOT", tmp_path)
    return tmp_path / ".env"


def test_env_configuration_is_fresh_private_and_does_not_mutate_process(isolated_environment):
    isolated_environment.write_text(
        f"CHAT_PROVIDER=gemini\nEMBEDDING_PROVIDER=gemini\nGEMINI_API_KEY={DUMMY_KEY}\n"
        "INDEX_DIR=data/gemini-index\n"
    )
    original_environment = dict(os.environ)
    first = Settings.from_env()
    assert first.chat_model == config.GEMINI_CHAT_MODEL
    assert first.embedding_model == config.GEMINI_EMBEDDING_MODEL
    assert first.index_dir == isolated_environment.parent / "data/gemini-index"
    assert first.gemini_api_key.get_secret_value() == DUMMY_KEY
    assert DUMMY_KEY not in repr(first)
    assert DUMMY_KEY not in first.cache_key()

    isolated_environment.write_text(
        "CHAT_PROVIDER=gemini\nEMBEDDING_PROVIDER=gemini\nGEMINI_API_KEY=second-dummy-key\n"
    )
    second = Settings.from_env()
    assert second.gemini_api_key.get_secret_value() == "second-dummy-key"
    assert first.cache_key() != second.cache_key()
    assert os.environ == original_environment


def test_process_environment_overrides_matching_dotenv_variable(monkeypatch, isolated_environment):
    isolated_environment.write_text("CHAT_PROVIDER=ollama\nGEMINI_API_KEY=file-dummy-key\n")
    monkeypatch.setenv("CHAT_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", DUMMY_KEY)
    settings = Settings.from_env()
    assert settings.chat_provider == "gemini"
    assert settings.gemini_api_key.get_secret_value() == DUMMY_KEY


def test_google_key_alias_works_and_gemini_key_has_priority(monkeypatch, isolated_environment):
    monkeypatch.setenv("GOOGLE_API_KEY", "google-dummy-key")
    assert Settings.from_env().gemini_api_key.get_secret_value() == "google-dummy-key"
    monkeypatch.setenv("GEMINI_API_KEY", DUMMY_KEY)
    assert Settings.from_env().gemini_api_key.get_secret_value() == DUMMY_KEY


def test_cache_token_changes_for_public_configuration_and_private_key(gemini_settings):
    token = gemini_settings.cache_key()
    assert len(token) == 64
    assert all(c in "0123456789abcdef" for c in token)
    assert token != replace(gemini_settings, chat_model="another-chat-model").cache_key()
    assert token != replace(gemini_settings, gemini_api_key=SecretStr("another-dummy-key")).cache_key()
    assert token == replace(gemini_settings).cache_key()
