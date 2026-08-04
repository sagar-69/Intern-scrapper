import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "postgresql://radar:radar@localhost:5432/internship_radar")
    llm_mode: str = os.getenv("LLM_MODE", "hybrid")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434/v1")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    worker_count: int = int(os.getenv("WORKER_COUNT", "5"))
    seed_target_url: str = os.getenv("SEED_TARGET_URL", "")

settings = Settings()

