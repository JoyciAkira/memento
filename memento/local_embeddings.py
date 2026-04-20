import logging
from typing import List

logger = logging.getLogger(__name__)


class LocalEmbeddingBackend:
    _MODEL_NAME = "BAAI/bge-small-en-v1.5"
    _DIMENSION = 384

    def __init__(self):
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return
        from fastembed import TextEmbedding
        logger.info(f"Loading local embedding model: {self._MODEL_NAME}")
        self._model = TextEmbedding(self._MODEL_NAME)
        logger.info("Local embedding model loaded successfully")

    async def embed(self, text: str) -> List[float]:
        self._ensure_model()
        results = list(self._model.embed([text]))
        if results:
            return results[0].tolist()
        return []

    @property
    def dimension(self) -> int:
        return self._DIMENSION


def is_fastembed_available() -> bool:
    try:
        import fastembed  # noqa: F401
        return True
    except ImportError:
        return False
