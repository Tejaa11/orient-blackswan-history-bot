"""Explicit Gemini/Ollama providers; no silent provider fallback."""
import re
import sys
import time
from langchain_core.embeddings import Embeddings
from langchain_ollama import ChatOllama, OllamaEmbeddings
from ollama import Client

from .config import Settings
from .errors import BotError


def require_gemini_key(settings: Settings):
    key = settings.gemini_api_key
    if key is None or not key.get_secret_value().strip():
        raise BotError("Gemini API key is missing. Add GEMINI_API_KEY to the local .env file, then reload the app. Do not put the key in source code.")
    return key


def provider_error(stage: str, provider: str, cause: Exception | None = None) -> BotError:
    # Never expose raw provider exceptions: they may contain request URLs or secrets.
    code = None
    retry_delay = None
    seen = set()
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        value = getattr(cause, "code", None) or getattr(cause, "status_code", None)
        if isinstance(value, int) and 400 <= value <= 599:
            code = value
            response = getattr(cause, "details", None) or getattr(cause, "response_json", None)
            if code == 429 and isinstance(response, dict):
                error_obj = response.get("error")
                error_dict = error_obj if isinstance(error_obj, dict) else response
                raw_details = error_dict.get("details", []) if isinstance(error_dict, dict) else []
                details = raw_details if isinstance(raw_details, list) else []
                quota_ids = [
                    v.get("quotaId", "")
                    for d in details
                    if isinstance(d, dict)
                    for v in (d.get("violations") or [])
                    if isinstance(v, dict)
                ]
                if any("PerMinute" in q or "PerSecond" in q for q in quota_ids):
                    for detail in details:
                        if isinstance(detail, dict):
                            delay = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)s", str(detail.get("retryDelay", "")))
                            if delay and 0 < float(delay[1]) <= 60:
                                retry_delay = min(60, float(delay[1]) + 1)
            break
        cause = cause.__cause__ or cause.__context__
    if provider == "gemini":
        detail = {
            400: "Google rejected the request; check the key, model name, and request settings.",
            401: "Google rejected the API credential.",
            403: "Google denied access; check API key permissions and project/model access.",
            404: "Google could not find the configured model; check model availability for this project.",
            429: "Google quota or rate limit was reached; wait and check the project's API limits before retrying.",
        }.get(code, "Check the Gemini API key, model access, quota/rate limits, and network connection, then retry.")
        error = BotError(f"{stage} failed. {detail}")
        error.provider_code = code
        error.retry_after_seconds = retry_delay
        return error
    return BotError(f"{stage} failed. Check that Ollama and the configured local model are available, then retry.")


def call_provider(operation, provider: str, stage: str):
    """Honor explicit short-window Google retry guidance, at most three retries.

    Daily/exhausted quota, authentication, and unknown errors are never looped.
    Ingestion saves each successful batch, so interruption can resume safely.
    """
    for attempt in range(4):
        try:
            return operation()
        except BotError:
            raise
        except Exception as exc:
            error = provider_error(stage, provider, exc)
            delay = getattr(error, "retry_after_seconds", None)
            if provider == "gemini" and delay is not None and attempt < 3:
                print(f"Google rate limit: waiting {delay:.0f}s before retrying {stage.lower()}.", file=sys.stderr, flush=True)
                time.sleep(delay)
                continue
            raise error from None


def model_digest(settings: Settings, name: str) -> str:
    try:
        for model in Client(host=settings.base_url, timeout=10).list().models:
            if model.model == name or model.model == f"{name}:latest":
                return model.digest
    except Exception as exc:
        raise BotError("Cannot reach Ollama. Start Ollama and check OLLAMA_BASE_URL.") from exc
    raise BotError(f"Local model '{name}' is missing. Run: ollama pull {name}")


def embedding_identity(settings: Settings) -> str:
    if settings.embedding_provider == "gemini":
        require_gemini_key(settings)
        # Hosted APIs do not expose a weight digest. Record model/config, not a fake hash.
        return f"gemini-api:{settings.embedding_model}:dimensions={settings.embedding_dimensions}:retrieval-v1"
    return model_digest(settings, settings.embedding_model)


def chat_identity(settings: Settings) -> str:
    if settings.chat_provider == "gemini":
        require_gemini_key(settings)
        return f"gemini-api:{settings.chat_model}"
    return model_digest(settings, settings.chat_model)


class CatalogueEmbeddings(Embeddings):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.google = settings.embedding_provider == "gemini"
        self.nomic = not self.google and settings.embedding_model.startswith("nomic-embed-text")
        if self.google:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            self.provider = GoogleGenerativeAIEmbeddings(
                model=settings.embedding_model, api_key=require_gemini_key(settings), vertexai=False,
                output_dimensionality=settings.embedding_dimensions,
            )
        else:
            self.provider = OllamaEmbeddings(
                model=settings.embedding_model, base_url=settings.base_url,
                client_kwargs={"timeout": settings.model_timeout},
            )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        def operation():
            if self.google:
                return self.provider.embed_documents(texts, task_type="RETRIEVAL_DOCUMENT")
            return self.provider.embed_documents([
                f"search_document: {text}" if self.nomic else text for text in texts
            ])
        return call_provider(operation, self.settings.embedding_provider, "Document embedding")

    def embed_query(self, text: str) -> list[float]:
        def operation():
            if self.google:
                return self.provider.embed_query(text, task_type="RETRIEVAL_QUERY")
            return self.provider.embed_query(f"search_query: {text}" if self.nomic else text)
        return call_provider(operation, self.settings.embedding_provider, "Query embedding")


def chat_model(settings: Settings):
    if settings.chat_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=settings.chat_model, api_key=require_gemini_key(settings), vertexai=False,
            max_tokens=2048, max_retries=1, timeout=settings.model_timeout,
        )
    return ChatOllama(
        model=settings.chat_model, base_url=settings.base_url, temperature=0,
        reasoning=False, num_ctx=8192, num_predict=1100, seed=42,
        client_kwargs={"timeout": settings.model_timeout},
    )
