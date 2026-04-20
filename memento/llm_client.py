import os
import asyncio
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None
_client_base_url: str | None = None

_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2.0

_LOCAL_HOST_INDICATORS = ("localhost", "127.0.0.1", "0.0.0.0", "::1")


async def _retry_async(coro):
    for attempt in range(_MAX_RETRIES):
        try:
            return await coro
        except Exception as e:
            if attempt < _MAX_RETRIES - 1 and _is_retryable(e):
                wait = _RETRY_BACKOFF_BASE ** (attempt + 1)
                logger.warning(f"Retrying LLM call (attempt {attempt + 1}/{_MAX_RETRIES}): {e}")
                await asyncio.sleep(wait)
            else:
                raise


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in ("rate_limit", "429", "timeout", "503", "502", "connection"))


def _is_local_base_url(base_url: str) -> bool:
    """Check if the base URL points to a local endpoint (LM Studio, Ollama, etc.)."""
    return any(indicator in base_url for indicator in _LOCAL_HOST_INDICATORS)


def get_llm_client() -> AsyncOpenAI | None:
    global _client, _client_base_url

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()

    is_local = _is_local_base_url(base_url)

    # Local LLM endpoints (LM Studio, Ollama) don't require authentication.
    if not api_key and not is_local:
        logger.debug("No OPENAI_API_KEY set and base_url is not local. LLM features disabled.")
        return None

    effective_key = api_key if api_key else "local-no-key"

    if _client is not None and _client_base_url == base_url:
        return _client

    _client = AsyncOpenAI(api_key=effective_key, base_url=base_url)
    _client_base_url = base_url
    logger.info(f"LLM client initialized: base_url={base_url}, local={is_local}")
    return _client


def get_model_name() -> str:
    return os.environ.get("MEM0_MODEL", "openai/gpt-4o-mini")


def get_embedding_model() -> str:
    return os.environ.get("MEM0_EMBEDDING_MODEL", "text-embedding-3-small")
