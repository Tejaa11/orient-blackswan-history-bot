"""Short Google quota retries with synthetic errors and a mocked clock only."""

import json
import traceback
from unittest.mock import Mock

import pytest

from history_bot import providers
from history_bot.errors import BotError


DUMMY_KEY = "dummy-retry-test-key-never-a-real-credential"


@pytest.fixture(autouse=True)
def fake_sleep(monkeypatch):
    sleep = Mock()
    monkeypatch.setattr(providers.time, "sleep", sleep)
    return sleep


def quota_error(*, code=429, quota="EmbedContentRequestsPerMinute", delay="47s", retry_info=True):
    details = [{
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
        "violations": [{"quotaId": quota, "description": f"Synthetic private request key={DUMMY_KEY}"}],
    }]
    if retry_info:
        details.append({"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay})
    error = RuntimeError(f"Synthetic SDK error containing key={DUMMY_KEY}")
    error.code = code
    error.response_json = {"error": {"code": code, "details": details}}
    return error


def assert_private(error, captured):
    assert isinstance(error, BotError)
    assert "Not found" not in str(error)
    assert DUMMY_KEY not in str(error)
    assert DUMMY_KEY not in "".join(traceback.format_exception(error))
    assert DUMMY_KEY not in captured.out + captured.err
    assert "response_json" not in captured.out + captured.err


@pytest.mark.parametrize("quota, delay, expected_wait", [
    ("EmbedContentRequestsPerMinute", "47s", 48),
    ("EmbedContentRequestsPerSecond", "60s", 60),
])
def test_explicit_short_window_google_limit_waits_then_returns_success(fake_sleep, capsys, quota, delay, expected_wait):
    result = object()
    operation = Mock(side_effect=[quota_error(quota=quota, delay=delay), result])
    assert providers.call_provider(operation, "gemini", "Document embedding") is result
    assert operation.call_count == 2
    fake_sleep.assert_called_once_with(expected_wait)
    captured = capsys.readouterr()
    assert "Google rate limit" in captured.err
    assert DUMMY_KEY not in captured.out + captured.err
    assert "quotaId" not in captured.out + captured.err


def test_repeated_short_window_limit_stops_after_four_attempts_without_exposing_payload(fake_sleep, capsys):
    operation = Mock(side_effect=quota_error())
    with pytest.raises(BotError) as failure:
        providers.call_provider(operation, "gemini", "Document embedding")
    assert operation.call_count == 4
    assert fake_sleep.call_count == 3
    assert all(call.args == (48,) for call in fake_sleep.call_args_list)
    assert failure.value.provider_code == 429
    assert "quota" in str(failure.value).lower()
    assert_private(failure.value, capsys.readouterr())


def test_daily_quota_is_not_retried_even_with_google_retry_guidance(fake_sleep, capsys):
    operation = Mock(side_effect=quota_error(quota="EmbedContentRequestsPerDay"))
    with pytest.raises(BotError) as failure:
        providers.call_provider(operation, "gemini", "Document embedding")
    assert operation.call_count == 1
    fake_sleep.assert_not_called()
    assert failure.value.provider_code == 429
    assert_private(failure.value, capsys.readouterr())


@pytest.mark.parametrize("delay", ["61s", "0s", "47", "soon", None])
def test_unusable_or_excessive_retry_delay_is_not_retried(fake_sleep, capsys, delay):
    operation = Mock(side_effect=quota_error(delay=delay))
    with pytest.raises(BotError) as failure:
        providers.call_provider(operation, "gemini", "Query embedding")
    assert operation.call_count == 1
    fake_sleep.assert_not_called()
    assert_private(failure.value, capsys.readouterr())


def test_short_window_quota_without_retry_info_is_not_retried(fake_sleep, capsys):
    operation = Mock(side_effect=quota_error(retry_info=False))
    with pytest.raises(BotError) as failure:
        providers.call_provider(operation, "gemini", "Query embedding")
    assert operation.call_count == 1
    fake_sleep.assert_not_called()
    assert_private(failure.value, capsys.readouterr())


def test_authentication_failure_is_not_retried_with_misleading_retry_metadata(fake_sleep, capsys):
    operation = Mock(side_effect=quota_error(code=401))
    with pytest.raises(BotError) as failure:
        providers.call_provider(operation, "gemini", "The language model request")
    assert operation.call_count == 1
    fake_sleep.assert_not_called()
    assert failure.value.provider_code == 401
    assert "credential" in str(failure.value).lower()
    assert_private(failure.value, capsys.readouterr())


def test_ollama_failure_never_uses_google_retry_metadata(fake_sleep, capsys):
    operation = Mock(side_effect=quota_error())
    with pytest.raises(BotError) as failure:
        providers.call_provider(operation, "ollama", "Query embedding")
    assert operation.call_count == 1
    fake_sleep.assert_not_called()
    assert "Ollama" in str(failure.value)
    assert_private(failure.value, capsys.readouterr())


@pytest.mark.parametrize("response", [{"error": None}, {"error": {"details": None}}])
def test_unexpected_google_error_payload_is_safely_reported_without_retry(fake_sleep, capsys, response):
    error = quota_error()
    error.response_json = response
    operation = Mock(side_effect=error)
    with pytest.raises(BotError) as failure:
        providers.call_provider(operation, "gemini", "Query embedding")
    assert operation.call_count == 1
    fake_sleep.assert_not_called()
    assert failure.value.provider_code == 429
    assert_private(failure.value, capsys.readouterr())
    assert DUMMY_KEY not in json.dumps(response)
