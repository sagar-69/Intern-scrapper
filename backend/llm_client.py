from typing import Literal
from .settings import settings

def get_llm_client(mode: Literal["local", "cloud"]):
    if mode == "cloud":
        if not settings.gemini_api_key: raise RuntimeError("GEMINI_API_KEY is required for cloud extraction")
        import instructor
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        return instructor.from_genai(genai.GenerativeModel("gemini-2.5-flash-lite"))
    if not settings.ollama_host: raise RuntimeError("OLLAMA_HOST is required for local discovery")
    try:
        import instructor
        from openai import AsyncOpenAI
        return instructor.from_openai(AsyncOpenAI(base_url=settings.ollama_host, api_key="ollama"))
    except ImportError as exc: raise RuntimeError("Install instructor and openai for local LLM mode") from exc
