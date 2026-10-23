"""Streamlit interface for the grounded Orient BlackSwan catalogue assistant.

Run ``python -m history_bot ingest`` before ``streamlit run app.py``.
"""

from __future__ import annotations

import html

import streamlit as st

from history_bot.config import Settings
from history_bot.service import BotError, CatalogueBot, InputError


st.set_page_config(
    page_title="Orient BlackSwan History Bot",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .stApp { background: #f7f4ec; }
      .block-container { max-width: 1120px; padding-top: 2.5rem; padding-bottom: 3rem; }
      h1, h2, h3 { font-family: Georgia, 'Times New Roman', serif !important;
                    font-weight: 500 !important; letter-spacing: -.025em; }
      h1 { font-size: clamp(2.25rem, 5vw, 3.8rem) !important; line-height: 1.08 !important; }
      h2 { font-size: 1.85rem !important; }
      h3 { font-size: 1.3rem !important; }
      p, li, label { line-height: 1.65; }
      .masthead { border-top: 3px solid #244a37; padding-top: 1rem;
                    margin-bottom: 1.1rem; color: #8b5b3d; font-size: .72rem;
                    letter-spacing: .18em; font-weight: 650; }
      .intro { max-width: 710px; font-size: 1.06rem; color: #536257;
                 line-height: 1.75; margin: .3rem 0 1.5rem; }
      .section-label { color: #8b5b3d; font-size: .7rem; letter-spacing: .14em;
                         font-weight: 650; margin: 1.1rem 0 .7rem; }
      .empty-state { padding: 2.3rem 0 1.3rem; border-top: 1px solid #d8d5ca;
                       margin-top: 1.9rem; }
      .empty-state .symbol { color: #8b5b3d; font-size: 1.5rem; }
      .empty-state h3 { margin: .7rem 0 .3rem; }
      .empty-state p { color: #637064; max-width: 590px; font-size: .94rem; }
      .source-line { color: #526357; font-size: .79rem; padding: .25rem 0 .7rem; }
      .citation-label { color: #8b5b3d; font-size: .69rem; letter-spacing: .13em;
                           margin: .8rem 0 .3rem; font-weight: 650; }
      div[data-testid="stForm"] { border-color: #c9cdbf; border-radius: 5px;
                                   background: #fcfaf5; padding: 1.15rem; }
      div[data-testid="stTextInput"] input { background: #fffef9; }
      div[data-testid="stButton"] button { border-radius: 4px; }
      div[data-testid="stFormSubmitButton"] button { border-radius: 4px; }
      div[data-testid="stExpander"] { background: #fcfaf5; border-radius: 4px; }
      div[data-testid="stSidebar"] { border-right: 1px solid #d8d5ca; }
      .footer-note { color: #6a7569; font-size: .74rem; line-height: 1.7;
                       border-top: 1px solid #d8d5ca; margin-top: 2.3rem; padding-top: 1rem; }
      @media (max-width: 640px) {
        .block-container { padding-top: 1.4rem; padding-left: 1rem; padding-right: 1rem; }
        .intro { font-size: .97rem; }
        .masthead { letter-spacing: .12em; font-size: .65rem; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)

for state_key, default in {
    "catalogue_history": [],
    "catalogue_question": "",
    "catalogue_pending": None,
    "catalogue_busy": False,
    "catalogue_error": None,
}.items():
    if state_key not in st.session_state:
        st.session_state[state_key] = default


@st.cache_resource(show_spinner=False)
def ready_bot(configuration_key: str, _settings: Settings) -> CatalogueBot:
    """Reuse an index until settings change; keep private settings out of hashing."""
    return CatalogueBot(_settings)


def queue_question(question: str) -> None:
    question = question.strip()
    st.session_state.catalogue_error = None
    if not question:
        st.session_state.catalogue_error = "Enter a question about the history catalogue."
        return
    st.session_state.catalogue_pending = question
    st.session_state.catalogue_busy = True


def queue_input() -> None:
    queue_question(st.session_state.catalogue_question)


def reset_session() -> None:
    st.session_state.catalogue_history = []
    st.session_state.catalogue_question = ""
    st.session_state.catalogue_pending = None
    st.session_state.catalogue_busy = False
    st.session_state.catalogue_error = None


def show_answer(item: dict, *, latest: bool = False) -> None:
    """Render answer text and only the evidence returned by the backend."""
    if latest:
        st.markdown("## From the catalogue")
    st.markdown("**Your question**")
    st.write(item["question"])
    if item["supported"]:
        st.markdown(item["answer"])
    else:
        st.warning("Not found")
        st.caption("The catalogue does not provide enough evidence to answer this question.")

    citations = item["citations"]
    if citations:
        st.markdown('<div class="citation-label">SOURCE REFERENCES</div>', unsafe_allow_html=True)
        pages = sorted({citation["pdf_page"] for citation in citations})
        page_word = "page" if len(pages) == 1 else "pages"
        source_names = sorted({str(citation["source"]) for citation in citations})
        st.caption(f"{' · '.join(source_names)} · PDF {page_word} {', '.join(map(str, pages))}")
        with st.expander(f"Read the exact supporting passages ({len(citations)})"):
            for index, citation in enumerate(citations, start=1):
                st.markdown(f"**Passage {index} · PDF page {citation['pdf_page']}**")
                st.caption(f"{citation['source']} · {citation['chunk_id']}")
                # st.text preserves exact extracted wording and does not render HTML.
                st.text(citation["quote"])
                if index < len(citations):
                    st.divider()
    st.caption(f"Answered in {item['elapsed_seconds']:.1f}s · Based only on the supplied PDF catalogue")


st.markdown('<div class="masthead">ORIENT BLACKSWAN / HISTORY COLLECTION</div>', unsafe_allow_html=True)
heading, reset = st.columns([5, 1.2], vertical_alignment="top")
with heading:
    st.title("Orient BlackSwan History Bot")
with reset:
    st.button(
        "Reset session",
        on_click=reset_session,
        disabled=st.session_state.catalogue_busy,
        use_container_width=True,
        help="Clear the questions and answers shown in this session.",
    )
st.markdown(
    '<div class="intro">Explore the history catalogue with answers you can trace '
    'to the original PDF pages.</div>',
    unsafe_allow_html=True,
)

bot = None
settings = None
readiness_error = None
try:
    settings = Settings.from_env()
    with st.spinner("Opening the catalogue…"):
        bot = ready_bot(settings.cache_key(), settings)
except BotError as exc:
    readiness_error = str(exc)
except (ValueError, OSError) as exc:
    readiness_error = str(exc)

with st.sidebar:
    st.markdown("### About this catalogue")
    st.write("Ask about titles, authors, prices, editions, or other information present in the supplied history catalogue.")
    st.caption("Questions beyond the PDF receive ‘Not found’. Source references use the PDF's page positions, which may differ from printed page numbers.")
    if settings is not None:
        st.divider()
        st.markdown("**Model configuration**")
        provider_names = {"gemini": "Gemini", "ollama": "Ollama"}
        st.caption(f"Answers: {provider_names[settings.chat_provider]} · {settings.chat_model}")
        st.caption(f"Embeddings: {provider_names[settings.embedding_provider]} · {settings.embedding_model}")
        with st.expander("Provider setup"):
            st.write("Choose providers and models in the project's private .env file. For Gemini, set GEMINI_API_KEY there.")
            st.caption("After adding the key, prepare the catalogue once with python -m history_bot ingest. Rebuild the index if the embedding provider or model changes, then refresh this page after configuration edits.")
    if bot is not None:
        st.divider()
        st.markdown("**Indexed source**")
        st.write(bot.info["source"])
        st.caption(f"{bot.info['page_count']} PDF pages · {bot.info['chunk_count']} searchable passages")
        with st.expander("Index details"):
            st.caption("Source SHA-256")
            st.code(bot.info["sha256"], language=None, wrap_lines=True)
    st.divider()
    st.caption("Reset clears this session's visible questions and answers. The prepared catalogue index remains available.")

if bot is None:
    st.error("The catalogue is not ready yet.")
    if readiness_error:
        st.write(readiness_error)
    st.info("Configure the selected providers in the project's private .env file. For Gemini, add GEMINI_API_KEY. Then check the connection and prepare the catalogue from the project directory:")
    st.code("python -m history_bot doctor\npython -m history_bot ingest", language="bash")
    st.caption("Prepare the index once after adding the key. Rebuild it when the embedding provider or model changes. Refresh this page after setup or configuration edits. See the project README for instructions.")
    st.session_state.catalogue_busy = False
    st.session_state.catalogue_pending = None
    st.stop()

source = html.escape(str(bot.info["source"]))
st.markdown(
    f'<div class="source-line">● &nbsp; Catalogue ready &nbsp; · &nbsp; {source}'
    f' &nbsp; · &nbsp; {bot.info["page_count"]} PDF pages</div>',
    unsafe_allow_html=True,
)

with st.form("catalogue_question_form", clear_on_submit=False):
    st.text_input(
        "Ask the catalogue",
        key="catalogue_question",
        placeholder="e.g. When were the catalogue prices last updated?",
        disabled=st.session_state.catalogue_busy,
    )
    st.form_submit_button(
        "Searching the catalogue…" if st.session_state.catalogue_busy else "Find an answer →",
        type="primary",
        on_click=queue_input,
        disabled=st.session_state.catalogue_busy,
    )
    st.caption("Answers are limited to this PDF. Every supported answer includes source passages.")

st.markdown('<div class="section-label">A FEW PLACES TO BEGIN</div>', unsafe_allow_html=True)
examples = [
    "When were the catalogue prices last updated?",
    "When was Orient BlackSwan incorporated?",
    "Who is the current Minister of Education?",
]
for column, example in zip(st.columns(3), examples):
    with column:
        st.button(
            example,
            on_click=queue_question,
            args=(example,),
            disabled=st.session_state.catalogue_busy,
            use_container_width=True,
        )
st.caption("The last example checks how the bot handles a question beyond its catalogue.")

if st.session_state.catalogue_pending:
    question = st.session_state.catalogue_pending
    try:
        with st.spinner("Finding relevant passages and checking the answer…"):
            result = bot.ask(question)
        st.session_state.catalogue_history.append(
            {
                "question": question,
                "answer": result.answer,
                "supported": result.supported,
                "citations": result.citations,
                "elapsed_seconds": result.elapsed_seconds,
            }
        )
        st.session_state.catalogue_error = None
    except InputError as exc:
        st.session_state.catalogue_error = str(exc)
    except BotError as exc:
        st.session_state.catalogue_error = str(exc)
    finally:
        st.session_state.catalogue_pending = None
        st.session_state.catalogue_busy = False
    st.rerun()

if st.session_state.catalogue_error:
    st.error(st.session_state.catalogue_error)

history = st.session_state.catalogue_history
if history:
    st.divider()
    show_answer(history[-1], latest=True)
    if len(history) > 1:
        st.markdown("### Earlier in this session")
        for number, item in reversed(list(enumerate(history[:-1], start=1))):
            with st.expander(f"{number:02d} · {item['question']}"):
                show_answer(item)
else:
    st.markdown(
        '<div class="empty-state"><div class="symbol">§</div>'
        '<h3>An answer you can trace.</h3>'
        '<p>Start with a question above. Your answer will appear here, along with '
        'the exact catalogue passages that support it.</p></div>',
        unsafe_allow_html=True,
    )

st.markdown(
    '<div class="footer-note">A focused reading companion for the Orient BlackSwan history catalogue. '
    'Prices and publication details reflect the supplied catalogue; check its date before relying on them.</div>',
    unsafe_allow_html=True,
)
