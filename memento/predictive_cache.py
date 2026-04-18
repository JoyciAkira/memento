"""Predictive cache — pre-warms related memories based on text context."""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PredictiveCache:
    """In-memory cache that pre-warms related memories for proactive context injection."""

    MAX_CACHE_SIZE = 100
    CACHE_TTL_SECONDS = 300  # 5 minutes
    MAX_RESULTS_PER_KEY = 5

    def __init__(self, db_path: str, provider=None):
        self.db_path = db_path
        self.provider = provider
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._hits = 0
        self._misses = 0

    async def warm_for_context(self, text: str, limit: int = 5) -> Dict[str, Any]:
        """Search for related memories given text context and cache them."""
        key = self._make_key(text)
        if key in self._cache:
            entry = self._cache[key]
            if time.time() - entry["timestamp"] < self.CACHE_TTL_SECONDS:
                self._hits += 1
                return entry
            del self._cache[key]

        self._misses += 1

        if not self.provider:
            return {"key": key, "results": [], "cached_at": None}

        try:
            results = await self.provider.search(text, limit=limit)
            entry = {
                "key": key,
                "results": [
                    {
                        "id": r.get("id"),
                        "memory": r.get("memory", ""),
                        "score": r.get("score", 0),
                    }
                    for r in results
                ],
                "cached_at": datetime.now().isoformat(),
                "timestamp": time.time(),
            }
            self._cache[key] = entry
            # Evict oldest if over limit
            while len(self._cache) > self.MAX_CACHE_SIZE:
                oldest_key = min(
                    self._cache, key=lambda k: self._cache[k]["timestamp"]
                )
                del self._cache[oldest_key]
            return entry
        except Exception as e:
            logger.error(f"Predictive cache warm error: {e}")
            return {"key": key, "results": [], "cached_at": None, "error": str(e)}

    def get_cached_context(self, text: str) -> Optional[Dict[str, Any]]:
        """Retrieve pre-warmed context for text. Returns None if not cached."""
        key = self._make_key(text)
        entry = self._cache.get(key)
        if not entry:
            return None
        if time.time() - entry["timestamp"] >= self.CACHE_TTL_SECONDS:
            del self._cache[key]
            return None
        self._hits += 1
        return entry

    def invalidate(self, file_path: str = None, key: str = None) -> int:
        """Invalidate cache entries. Returns count of evicted entries."""
        if key:
            self._cache.pop(key, None)
            return 1
        if file_path:
            prefix = self._make_key(file_path)
            keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_remove:
                del self._cache[k]
            return len(keys_to_remove)
        count = len(self._cache)
        self._cache.clear()
        return count

    def cache_stats(self) -> Dict[str, Any]:
        active = sum(
            1
            for e in self._cache.values()
            if time.time() - e["timestamp"] < self.CACHE_TTL_SECONDS
        )
        total = self._hits + self._misses
        return {
            "total_entries": len(self._cache),
            "active_entries": active,
            "stale_entries": len(self._cache) - active,
            "max_size": self.MAX_CACHE_SIZE,
            "ttl_seconds": self.CACHE_TTL_SECONDS,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / max(total, 1), 3) if total > 0 else 0,
        }

    @staticmethod
    def _make_key(text: str) -> str:
        return text[:200].strip()
