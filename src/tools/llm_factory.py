"""
src/tools/llm_factory.py
────────────────────────
Provider-agnostic LangChain chat model factory.
Switch between OpenAI and Google Gemini via LLM_PROVIDER env var.
"""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from src.config import settings


def get_llm(temperature: float = 0.3) -> BaseChatModel:
    provider = settings.llm_provider.lower()

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.llm_model,
            temperature=temperature,
            api_key=settings.openai_api_key,
        )
    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=settings.llm_model,
            temperature=temperature,
            google_api_key=settings.google_api_key,
        )
    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER: '{provider}'. Use 'openai' or 'google'."
        )
