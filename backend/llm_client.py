from typing import Literal

from settings import settings


def get_llm_client(mode: Literal["local", "cloud"] = "local"):
    if mode == "cloud":
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for cloud extraction")
        import google.generativeai as genai
        import instructor

        genai.configure(api_key=settings.gemini_api_key)
        return instructor.from_gemini(
            client=genai.GenerativeModel("gemini-2.5-flash-lite"),
            mode=instructor.Mode.GEMINI_JSON,
        )

    if not settings.ollama_host:
        raise RuntimeError("OLLAMA_HOST is required for local extraction")

    try:
        import instructor
        from openai import OpenAI

        return instructor.from_openai(
            OpenAI(base_url=settings.ollama_host, api_key="ollama"),
            mode=instructor.Mode.JSON,
        )
    except ImportError as exc:
        raise RuntimeError("Install instructor and openai for local LLM mode") from exc
