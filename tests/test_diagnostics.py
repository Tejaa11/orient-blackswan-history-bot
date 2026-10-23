"""Offline doctor tests using temporary paths and synthetic credentials only."""

import json
import socket
import sys
from dataclasses import replace
from unittest.mock import Mock

import pytest
from pydantic import SecretStr

from history_bot import __main__ as cli
from history_bot import ingest, providers
from history_bot.config import Settings
from history_bot.diagnostics import diagnose


DUMMY_KEY = "dummy-doctor-key-never-a-real-credential"


@pytest.fixture(autouse=True)
def prevent_network_and_provider_use(monkeypatch):
    """Configuration diagnostics must not construct providers or open a store."""
    blocked = []
    for module, attribute in [
        (socket, "create_connection"),
        (providers, "Client"),
        (providers, "CatalogueEmbeddings"),
        (providers, "chat_model"),
        (providers, "embedding_identity"),
        (providers, "chat_identity"),
        (ingest, "open_store"),
    ]:
        guard = Mock(side_effect=AssertionError("Offline diagnostics used a provider or network"))
        monkeypatch.setattr(module, attribute, guard)
        blocked.append(guard)
    yield
    for guard in blocked:
        guard.assert_not_called()


@pytest.fixture
def settings(tmp_path):
    source = tmp_path / "synthetic.pdf"
    # Doctor checks local file presence only. It must not parse or hash this file.
    source.write_text("Synthetic local source placeholder, not a real PDF.")
    return Settings(
        pdf_path=source,
        index_dir=tmp_path / "index",
        chat_provider="gemini",
        embedding_provider="gemini",
        chat_model="synthetic-gemini-chat",
        embedding_model="synthetic-gemini-embedding",
        gemini_api_key=SecretStr(DUMMY_KEY),
    )


def write_manifest(settings, **overrides):
    signature = {
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        **overrides,
    }
    settings.index_dir.mkdir(parents=True, exist_ok=True)
    (settings.index_dir / "manifest.json").write_text(json.dumps({"signature": signature}))


def assert_offline_private(report):
    serialized = json.dumps(report)
    assert DUMMY_KEY not in serialized
    assert report["provider_connectivity"] == "not_checked"
    assert report["credential_validity"] == "not_checked"


def test_missing_private_key_and_source_have_actionable_offline_setup_issues(settings):
    settings.pdf_path.unlink()
    report = diagnose(replace(settings, gemini_api_key=None))

    assert report["status"] == "configuration_required"
    assert report["api_key_present"] is False
    assert any("GEMINI_API_KEY" in issue for issue in report["issues"])
    assert any("python -m history_bot download" in issue for issue in report["issues"])
    assert "ingestion" in report["index"]
    assert_offline_private(report)


@pytest.mark.parametrize("chat_provider, embedding_provider", [
    ("gemini", "ollama"), ("ollama", "gemini"),
])
def test_mixed_provider_configuration_requires_gemini_key_for_either_role(settings, chat_provider, embedding_provider):
    report = diagnose(replace(
        settings,
        chat_provider=chat_provider,
        embedding_provider=embedding_provider,
        gemini_api_key=SecretStr("  "),
    ))
    assert report["status"] == "configuration_required"
    assert report["api_key_present"] is False
    assert any("GEMINI_API_KEY" in issue for issue in report["issues"])
    assert_offline_private(report)


def test_ollama_configuration_needs_no_api_key_or_live_local_service(settings):
    report = diagnose(replace(settings, chat_provider="ollama", embedding_provider="ollama", gemini_api_key=None))
    assert report["status"] == "local_configuration_checked"
    assert report["api_key_present"] is False
    assert report["embedding_dimensions"] == "model-default"
    assert report["issues"] == []
    assert_offline_private(report)


def test_existing_key_and_matching_manifest_do_not_claim_authentication_or_database_validity(settings):
    write_manifest(settings)
    report = diagnose(settings)

    assert report["status"] == "local_configuration_checked"
    assert report["api_key_present"] is True
    assert report["embedding_dimensions"] == 768
    assert report["issues"] == []
    assert report["index"] == "configuration matches; database not checked"
    assert not (settings.index_dir / "chroma").exists()
    assert_offline_private(report)


@pytest.mark.parametrize("field, value", [
    ("embedding_provider", "ollama"),
    ("embedding_model", "another-embedding"),
    ("embedding_dimensions", 256),
    ("chunk_size", 1000),
    ("chunk_overlap", 100),
])
def test_changed_embedding_or_chunk_configuration_requests_ingestion(settings, field, value):
    write_manifest(settings, **{field: value})
    report = diagnose(settings)
    assert report["index"] == "configuration changed; run ingestion"
    assert_offline_private(report)


def test_chat_model_change_does_not_invalidate_embedding_configuration(settings):
    write_manifest(settings)
    report = diagnose(replace(settings, chat_model="another-synthetic-chat"))
    assert report["index"] == "configuration matches; database not checked"
    assert report["chat_model"] == "another-synthetic-chat"
    assert_offline_private(report)


@pytest.mark.parametrize("text", [
    "not valid JSON",
    "{}",
    '{"signature": null}',
    '{"signature": []}',
    "[]",
    "null",
], ids=["invalid-json", "missing-signature", "null-signature", "list-signature", "list-manifest", "null-manifest"])
def test_invalid_manifest_is_classified_without_a_traceback_or_database_access(settings, text):
    settings.index_dir.mkdir(parents=True)
    (settings.index_dir / "manifest.json").write_text(text)
    report = diagnose(settings)
    assert report["index"] == "invalid manifest; inspect/rebuild index"
    assert_offline_private(report)


def test_doctor_cli_outputs_offline_metadata_without_credential_contents(monkeypatch, capsys, settings):
    write_manifest(settings)
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: settings))
    monkeypatch.setattr(sys, "argv", ["history_bot", "doctor"])
    assert cli.main() == 0
    output = capsys.readouterr()
    assert output.err == ""
    report = json.loads(output.out)
    assert report["status"] == "local_configuration_checked"
    assert report["api_key_present"] is True
    assert_offline_private(report)
