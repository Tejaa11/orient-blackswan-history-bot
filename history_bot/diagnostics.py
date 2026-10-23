"""Offline configuration diagnostics. Never display credentials or call a provider."""
import json

from .config import Settings


def diagnose(settings: Settings):
    issues = []
    needs_key = "gemini" in {settings.chat_provider, settings.embedding_provider}
    key_present = bool(settings.gemini_api_key and settings.gemini_api_key.get_secret_value().strip())
    if needs_key and not key_present:
        issues.append("Set GEMINI_API_KEY privately in .env or the environment.")
    if not settings.pdf_path.is_file():
        issues.append("Download the catalogue: python -m history_bot download")
    index_status = "missing; run ingestion"
    manifest = settings.index_dir / "manifest.json"
    if manifest.is_file():
        try:
            signature = json.loads(manifest.read_text())["signature"]
            if not isinstance(signature, dict):
                raise ValueError("Invalid signature shape")
            matches = (
                signature.get("embedding_provider") == settings.embedding_provider
                and signature.get("embedding_model") == settings.embedding_model
                and signature.get("chunk_size") == settings.chunk_size
                and signature.get("chunk_overlap") == settings.chunk_overlap
            )
            if settings.embedding_provider == "gemini":
                matches = matches and signature.get("embedding_dimensions") == settings.embedding_dimensions
            index_status = "configuration matches; database not checked" if matches else "configuration changed; run ingestion"
        except (OSError, ValueError, KeyError, TypeError):
            index_status = "invalid manifest; inspect/rebuild index"
    return {
        "status": "configuration_required" if issues else "local_configuration_checked",
        "chat_provider": settings.chat_provider, "chat_model": settings.chat_model,
        "embedding_provider": settings.embedding_provider, "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions if settings.embedding_provider == "gemini" else "model-default",
        "api_key_present": key_present, "provider_connectivity": "not_checked",
        "credential_validity": "not_checked", "index": index_status, "issues": issues,
    }
