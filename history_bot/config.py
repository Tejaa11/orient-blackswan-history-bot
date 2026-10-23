"""Configuration is explicit, local, and independent of the current directory."""
import os
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values
from pydantic import SecretStr

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE_URL = "https://www.orientblackswan.com/pdfs/downloads/History_2024-25.pdf"
GEMINI_CHAT_MODEL = "gemini-3.5-flash-lite"
GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"


@dataclass(frozen=True)
class Settings:
    pdf_path: Path = ROOT / "data/source/History_2024-25.pdf"
    index_dir: Path = ROOT / "data/index"
    base_url: str = "http://localhost:11434"
    chat_model: str = "qwen3:8b"
    embedding_model: str = "nomic-embed-text:v1.5"
    chat_provider: str = "ollama"
    embedding_provider: str = "ollama"
    embedding_dimensions: int = 768
    gemini_api_key: SecretStr | None = field(default=None, repr=False, compare=False)
    chunk_size: int = 1200
    chunk_overlap: int = 180
    retrieval_k: int = 6
    model_timeout: float = 180

    def __post_init__(self):
        if self.chat_provider not in {"gemini", "ollama"} or self.embedding_provider not in {"gemini", "ollama"}:
            raise ValueError("CHAT_PROVIDER and EMBEDDING_PROVIDER must be gemini or ollama.")
        if not self.chat_model.strip() or not self.embedding_model.strip():
            raise ValueError("CHAT_MODEL and EMBEDDING_MODEL cannot be empty.")
        if not 128 <= self.embedding_dimensions <= 3072:
            raise ValueError("EMBEDDING_DIMENSIONS must be between 128 and 3072.")
        if not 0 <= self.chunk_overlap < self.chunk_size or self.chunk_size < 200:
            raise ValueError("Use CHUNK_SIZE >= 200 and 0 <= CHUNK_OVERLAP < CHUNK_SIZE.")
        if not 1 <= self.retrieval_k <= 12 or self.model_timeout <= 0:
            raise ValueError("Use RETRIEVAL_K from 1 to 12 and a positive MODEL_TIMEOUT.")

    @classmethod
    def from_env(cls):
        # Re-read edits without copying credentials into global process state.
        env = {**dotenv_values(ROOT / ".env"), **os.environ}
        chat_provider = (env.get("CHAT_PROVIDER") or "ollama").strip().lower()
        embedding_provider = (env.get("EMBEDDING_PROVIDER") or "ollama").strip().lower()
        key = (env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY") or "").strip()

        def path(name, default):
            p = Path(env.get(name) or default).expanduser()
            return p if p.is_absolute() else ROOT / p

        return cls(
            pdf_path=path("CATALOGUE_PATH", "data/source/History_2024-25.pdf"),
            index_dir=path("INDEX_DIR", "data/index"),
            base_url=env.get("OLLAMA_BASE_URL") or "http://localhost:11434",
            chat_provider=chat_provider, embedding_provider=embedding_provider,
            chat_model=env.get("CHAT_MODEL") or (GEMINI_CHAT_MODEL if chat_provider == "gemini" else "qwen3:8b"),
            embedding_model=env.get("EMBEDDING_MODEL") or (GEMINI_EMBEDDING_MODEL if embedding_provider == "gemini" else "nomic-embed-text:v1.5"),
            embedding_dimensions=int(env.get("EMBEDDING_DIMENSIONS") or "768"),
            gemini_api_key=SecretStr(key) if key else None,
            chunk_size=int(env.get("CHUNK_SIZE") or "1200"),
            chunk_overlap=int(env.get("CHUNK_OVERLAP") or "180"),
            retrieval_k=int(env.get("RETRIEVAL_K") or "6"),
            model_timeout=float(env.get("MODEL_TIMEOUT") or "180"),
        )

    def cache_key(self) -> str:
        """A non-display cache token: invalidate resources after private key/config edits."""
        key = self.gemini_api_key.get_secret_value() if self.gemini_api_key else ""
        return hashlib.sha256((repr(self) + "\0" + key).encode()).hexdigest()

