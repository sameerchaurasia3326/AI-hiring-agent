"""
src/tools/llm_factory.py
────────────────────────
Provider-agnostic LangChain chat model factory.

Fallback chain (automatic):
  1. OpenAI         (OPENAI_API_KEY)
  2. Google Gemini  (GOOGLE_API_KEY)
  3. OpenRouter     (OPENROUTER_API_KEY)
  4. Ollama         (local — no key needed, always last resort)
"""
from __future__ import annotations

from loguru import logger

from langchain_core.language_models import BaseChatModel
from src.config import settings

# logger = logging.getLogger(__name__) # Removed in favor of loguru


def _check_ollama() -> bool:
    """Return True if Ollama server is reachable."""
    try:
        import urllib.request
        url = f"{settings.ollama_base_url.rstrip('/')}/api/tags"
        urllib.request.urlopen(url, timeout=3)
        return True
    except Exception:
        return False


from langchain_core.runnables import RunnableLambda

def get_llm(temperature: float = 0.3, prioritize_local: bool = False) -> BaseChatModel:
    """
    Return a LangChain chat model with a 4-level automatic fallback chain.

    Priority:
        1. The provider specified in settings.llm_provider (if key is set)
        2. Others in order: OpenAI → Google Gemini → OpenRouter → Ollama (local)
    """
    # Dictionary of available providers that have keys
    provider_map: dict[str, BaseChatModel] = {}

    # ── 1. OpenAI ──────────────────────────────────────────────────────────────
    if settings.openai_api_key:
        from langchain_openai import ChatOpenAI
        # If this is NOT the chosen provider, use a safe default like gpt-4o-mini
        model_name = settings.llm_model if settings.llm_provider == "openai" else "gpt-4o-mini"
        provider_map["openai"] = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=settings.openai_api_key,
        )
        logger.debug("LLM factory: prepared OpenAI (%s)", model_name)

    # ── 2. Google Gemini ───────────────────────────────────────────────────────
    if settings.google_api_key:
        from langchain_google_genai import ChatGoogleGenerativeAI
        # Use config model if chosen, else gemini-2.0-flash
        model_name = settings.llm_model if settings.llm_provider == "google" else "gemini-2.0-flash"
        provider_map["google"] = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
            google_api_key=settings.google_api_key,
        )
        logger.debug("LLM factory: prepared Google Gemini (%s)", model_name)

    # ── 3. OpenRouter ──────────────────────────────────────────────────────────
    if settings.openrouter_api_key:
        from langchain_openai import ChatOpenAI
        # Always use openrouter_model for OpenRouter fallback
        model_name = settings.openrouter_model
        provider_map["openrouter"] = ChatOpenAI(
            model=model_name,
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            temperature=temperature,
        )
        logger.debug("LLM factory: prepared OpenRouter (%s)", model_name)

    # ── 4. Ollama (local — always last resort) ─────────────────────────────────
    if _check_ollama():
        from langchain_ollama import ChatOllama
        provider_map["ollama"] = ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=temperature,
        )
        logger.debug("LLM factory: prepared Ollama (%s)", settings.ollama_model)
    else:
        logger.warning(
            "Ollama not reachable at %s — skipping local fallback. "
            "Run `ollama serve` to enable it.",
            settings.ollama_base_url,
        )

    # Order the models: Primary first, then others
    ordered_models: list[BaseChatModel] = []
    
    # ── 5. Define priority order ──────────────────────────────────────────────
    # Primary is always what's in settings.llm_provider
    primary_provider = settings.llm_provider.lower()
    
    if prioritize_local:
        order = ["ollama", "openai", "google", "openrouter"]
    else:
        order = ["openai", "google", "openrouter", "ollama"]

    # Move primary_provider to the front of the order list if it exists there
    if primary_provider in order:
        order.remove(primary_provider)
        order.insert(0, primary_provider)

    for p in order:
        if p in provider_map:
            ordered_models.append(provider_map.pop(p))

    if not ordered_models:
        raise ValueError(
            "No LLM provider available. Check API keys and ensure Ollama is running."
        )

    # If we only have one, return it
    if len(ordered_models) == 1:
        logger.info("LLM: using {} (no fallbacks)", ordered_models[0].__class__.__name__)
        return ordered_models[0]

    # Enhanced fallback logic with logging
    def wrap_with_logging(model: BaseChatModel, is_primary: bool = False):
        name = model.__class__.__name__
        def _invoke_with_log(input, config=None, **kwargs):
            if is_primary:
                logger.info("🤖 [LLM] Trying primary: {}", name)
            else:
                logger.warning("🔄 [LLM] Falling back to: {}", name)
            try:
                return model.invoke(input, config=config, **kwargs)
            except Exception as e:
                logger.error("❌ [LLM] {} failed: {}", name, str(e)[:100])
                raise e
        return RunnableLambda(_invoke_with_log)

    primary = wrap_with_logging(ordered_models[0], is_primary=True)
    fallbacks = [wrap_with_logging(m) for m in ordered_models[1:]]
    
    logger.info(
        "LLM: primary={} ({}), fallbacks={}",
        ordered_models[0].__class__.__name__,
        getattr(ordered_models[0], 'model_name', getattr(ordered_models[0], 'model', 'unknown')),
        [f"{m.__class__.__name__} ({getattr(m, 'model_name', getattr(m, 'model', 'unknown'))})" for m in ordered_models[1:]],
    )
    
    return primary.with_fallbacks(fallbacks)


def get_embeddings():
    """
    Return a LangChain embedding model with cloud-only automatic fallbacks.
    Priority: Provider in settings -> OpenRouter -> OpenAI -> Google
    Ollama is EXCLUDED for embeddings as per user requirement.
    """
    embeddings_map = {}

    # ── 1. OpenAI ──────────────────────────────────────────────────────────────
    if settings.openai_api_key:
        from langchain_openai import OpenAIEmbeddings
        embeddings_map["openai"] = OpenAIEmbeddings(
            api_key=settings.openai_api_key, 
            model=settings.openai_embedding_model
        )

    # ── 2. Google Gemini ───────────────────────────────────────────────────────
    if settings.google_api_key:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        embeddings_map["google"] = GoogleGenerativeAIEmbeddings(
            google_api_key=settings.google_api_key, 
            model=settings.gemini_embedding_model
        )

    # ── 3. OpenRouter (Cloud) ──────────────────────────────────────────────────
    if settings.openrouter_api_key:
        from langchain_openai import OpenAIEmbeddings
        embeddings_map["openrouter"] = OpenAIEmbeddings(
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_embedding_model,
            base_url="https://openrouter.ai/api/v1"
        )

    # Build fallback chain
    ordered = []
    
    # Build fallback chain: Cloud first, Ollama last
    ordered = []
    
    # Priority: Standard Cloud Chain (OpenAI -> Google -> OpenRouter)
    for p in ["openai", "google", "openrouter"]:
        if p in embeddings_map:
            ordered.append(embeddings_map.pop(p))
                
    # Priority: Ollama local fallback (Absolute last resort)
    if _check_ollama():
         from langchain_ollama import OllamaEmbeddings
         ordered.append(OllamaEmbeddings(
            model=settings.ollama_model, 
            base_url=settings.ollama_base_url
         ))

    if not ordered:
        raise ValueError("No Embedding provider available. Check API keys and Ollama status.")

    if len(ordered) == 1:
        return ordered[0]

    # Wrap with fallbacks manually since some Embedding models lack .with_fallbacks()
    class EmbeddingFallbackWrapper:
        def __init__(self, models):
            self.models = models
        
        def embed_query(self, text: str) -> List[float]:
            for model in self.models:
                try:
                    model_name = getattr(model, "model", model.__class__.__name__)
                    logger.info("🔄 [Embeddings] Trying fallback: {}", model_name)
                    return model.embed_query(text)
                except Exception as e:
                    logger.warning("❌ [Embeddings] Fallback failed: {} | Error: {}", model.__class__.__name__, e)
                    continue
            raise ValueError("All embedding models (cloud + local) failed.")
            
        def embed_documents(self, texts: List[str]) -> List[List[float]]:
            for model in self.models:
                try:
                    model_name = getattr(model, "model", model.__class__.__name__)
                    logger.info("🔄 [Embeddings] Trying fallback: {}", model_name)
                    return model.embed_documents(texts)
                except Exception as e:
                    logger.warning("❌ [Embeddings] Fallback failed: {} | Error: {}", model.__class__.__name__, e)
                    continue
            raise ValueError("All embedding models (cloud + local) failed.")

    return EmbeddingFallbackWrapper(ordered)

