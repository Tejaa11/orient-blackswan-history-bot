"""Streamlit interaction tests using an explicitly mocked backend.

AppTest exercises the UI callbacks, output, and reset. These are not real-model
integration tests: no PDF, vector index, embedding, or LLM is used.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from history_bot import config, service
from history_bot.models import Answer
from history_bot.service import BotError


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
MOCK_QUOTE = "The prices in this synthetic UI fixture were updated in January 2001."
SUPPORTED_QUESTION = "When were the catalogue prices last updated?"
UNSUPPORTED_QUESTION = "Who is the current Minister of Education?"


@pytest.fixture
def mock_backend(monkeypatch):
    """Replace every app entry into backend setup with an in-memory stand-in."""
    st.cache_resource.clear()
    state = SimpleNamespace(asked=[], readiness_error=None, ask_error=None)
    settings = SimpleNamespace(
        chat_model="mock-chat", embedding_model="mock-embed",
        chat_provider="gemini", embedding_provider="gemini",
        cache_key=lambda: "mock-configuration",
    )
    monkeypatch.setattr(config.Settings, "from_env", classmethod(lambda cls: settings))

    class MockCatalogueBot:
        def __init__(self, supplied_settings):
            assert supplied_settings is settings
            if state.readiness_error is not None:
                raise state.readiness_error
            self.settings = settings
            self.info = {
                "source": "unit-fixture.pdf",
                "page_count": 12,
                "chunk_count": 3,
                "sha256": "0" * 64,
            }

        def ask(self, question):
            state.asked.append(question)
            if state.ask_error is not None:
                raise state.ask_error
            if question == UNSUPPORTED_QUESTION:
                return Answer(question=question, answer="Not found", supported=False)
            return Answer(
                question=question,
                answer="The prices were updated in January 2001.",
                supported=True,
                citations=[
                    {
                        "source": "unit-fixture.pdf",
                        "pdf_page": 7,
                        "chunk_id": "mock-p007-c000",
                        "quote": MOCK_QUOTE,
                    }
                ],
                elapsed_seconds=0.1,
            )

    monkeypatch.setattr(service, "CatalogueBot", MockCatalogueBot)
    yield state
    st.cache_resource.clear()


def button(app, label):
    return next(control for control in app.button if control.label == label)


def load_app():
    app = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    assert not app.exception
    return app


def test_missing_index_explains_preparation_and_does_not_offer_active_form(mock_backend):
    mock_backend.readiness_error = BotError("Index not found. Run: python -m history_bot ingest")
    app = load_app()

    assert app.error[0].value == "The catalogue is not ready yet."
    assert any("python -m history_bot ingest" in code.value for code in app.code)
    assert any("Answers: Gemini · mock-chat" in caption.value for caption in app.caption)
    assert not app.text_input
    assert mock_backend.asked == []


def test_ready_state_has_question_form_and_no_initial_model_call(mock_backend):
    app = load_app()
    assert app.title[0].value == "Orient BlackSwan History Bot"
    assert app.text_input[0].label == "Ask the catalogue"
    assert app.text_input[0].disabled is False
    assert button(app, "Find an answer →").disabled is False
    assert not app.error
    assert mock_backend.asked == []


def test_empty_submission_shows_validation_without_calling_backend(mock_backend):
    app = load_app()
    button(app, "Find an answer →").click().run()
    assert not app.exception
    assert any("Enter a question" in error.value for error in app.error)
    assert mock_backend.asked == []
    assert app.session_state["catalogue_busy"] is False


def test_example_calls_backend_and_displays_source_and_exact_passage(mock_backend):
    app = load_app()
    button(app, SUPPORTED_QUESTION).click().run()
    assert not app.exception
    assert mock_backend.asked == [SUPPORTED_QUESTION]
    assert any("January 2001" in markdown.value for markdown in app.markdown)
    assert any("unit-fixture.pdf" in caption.value and "7" in caption.value for caption in app.caption)
    assert any("supporting passages" in expander.label for expander in app.expander)
    assert any(text.value == MOCK_QUOTE for text in app.text)
    assert app.session_state["catalogue_busy"] is False


def test_out_of_catalogue_example_calls_backend_and_shows_exact_not_found(mock_backend):
    app = load_app()
    button(app, UNSUPPORTED_QUESTION).click().run()
    assert not app.exception
    assert mock_backend.asked == [UNSUPPORTED_QUESTION]
    assert any(warning.value == "Not found" for warning in app.warning)
    assert not any("supporting passages" in expander.label for expander in app.expander)


def test_typed_question_works_and_reset_clears_visible_session(mock_backend):
    app = load_app()
    # A form batches input until submission, just as it does in the browser.
    app.text_input[0].input("What is in this catalogue?")
    button(app, "Find an answer →").click().run()
    assert not app.exception
    assert mock_backend.asked == ["What is in this catalogue?"]
    assert len(app.session_state["catalogue_history"]) == 1

    button(app, "Reset session").click().run()
    assert not app.exception
    assert app.session_state["catalogue_history"] == []
    assert app.text_input[0].value == ""
    assert app.session_state["catalogue_pending"] is None
    assert app.session_state["catalogue_error"] is None
    assert not any("supporting passages" in expander.label for expander in app.expander)


def test_model_error_is_shown_as_error_without_a_fake_not_found_answer(mock_backend):
    mock_backend.ask_error = BotError("Synthetic model failure. Please retry.")
    app = load_app()
    button(app, SUPPORTED_QUESTION).click().run()
    assert not app.exception
    assert any(error.value == "Synthetic model failure. Please retry." for error in app.error)
    assert not app.warning
    assert app.session_state["catalogue_history"] == []
    assert app.session_state["catalogue_busy"] is False
