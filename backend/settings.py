import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _ollama_base_url(value: str) -> str:
    value = value.rstrip("/")
    return value if value.endswith("/v1") else f"{value}/v1"


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./universal_jobs.db")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    llm_mode: str = os.getenv("LLM_MODE", "local")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    ollama_host: str = _ollama_base_url(os.getenv("OLLAMA_HOST", "http://localhost:11434"))
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    worker_count: int = int(os.getenv("WORKER_COUNT", "5"))
    seed_target_url: str = os.getenv("SEED_TARGET_URL", "")
    scrape_timeout_seconds: int = int(os.getenv("SCRAPE_TIMEOUT_SECONDS", "45"))
    llm_context_chars: int = int(os.getenv("LLM_CONTEXT_CHARS", "18000"))

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        return self.database_url


settings = Settings()
