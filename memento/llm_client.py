import os
import asyncio
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None

_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2.0


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


def get_llm_client() -> AsyncOpenAI | None:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    global _client
    if _client is None:
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        _client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    return _client


def get_model_name() -> str:
    return os.environ.get("MEM0_MODEL", "openai/gpt-4o-mini")


def get_embedding_model() -> str:
    return os.environ.get("MEM0_EMBEDDING_MODEL", "text-embedding-3-small")
