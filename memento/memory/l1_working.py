import time
from typing import List, Dict, Any, Iterable

class L1WorkingMemory:
    """
    Fast, in-memory volatile cache (L1).
    Eviction policy: LRU + importance score. Entries with higher importance survive longer.
    eviction_score = last_accessed + 0.3 * importance (normalized [0,1])
    """
    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self._cache: Dict[str, Dict[str, Any]] = {}

    def add(self, entry_id: str, content: str, metadata: Dict[str, Any] = None, importance: float = 0.5) -> None:
        if entry_id in self._cache:
            # refresh on re-add
            self._cache[entry_id]["content"] = content
            self._cache[entry_id]["metadata"] = metadata or {}
            self._cache[entry_id]["last_accessed"] = time.time()
            self._cache[entry_id]["importance"] = max(0.0, min(1.0, importance))
            return

        self._cache[entry_id] = {
            "id": entry_id,
            "content": content,
            "metadata": metadata or {},
            "timestamp": time.time(),
            "last_accessed": time.time(),
            "access_count": 0,
            "importance": max(0.0, min(1.0, importance)),
        }

        if len(self._cache) > self.max_size:
            self._evict()

    def _evict(self) -> None:
        # lowest (last_accessed + 0.3 * importance) is evicted
        victim = min(
            self._cache,
            key=lambda k: self._cache[k]["last_accessed"] + 0.3 * self._cache[k]["importance"]
        )
        del self._cache[victim]

    def get(self, entry_id: str) -> Dict[str, Any] | None:
        entry = self._cache.get(entry_id)
        if entry is not None:
            entry["last_accessed"] = time.time()
            entry["access_count"] += 1
        return entry

    def get_all(self) -> List[Dict[str, Any]]:
        return list(self._cache.values())

    def remove(self, entry_id: str) -> None:
        self._cache.pop(entry_id, None)

    def clear(self) -> None:
        self._cache.clear()

    def dump(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": item.get("id"),
                "content": item.get("content"),
                "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
                "timestamp": float(item.get("timestamp") or 0.0),
                "importance": float(item.get("importance") or 0.5),
            }
            for item in self.get_all()
        ]

    def restore(self, items: Iterable[Dict[str, Any]]) -> None:
        self._cache.clear()
        seq = list(items or [])
        for raw in seq:
            if not isinstance(raw, dict):
                continue
            entry_id = raw.get("id")
            content = raw.get("content", "")
            metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
            ts = float(raw.get("timestamp") or time.time())
            importance = float(raw.get("importance") or 0.5)
            if not isinstance(entry_id, str) or not entry_id:
                continue
            self._cache[entry_id] = {
                "id": entry_id,
                "content": str(content),
                "metadata": metadata,
                "timestamp": ts,
                "last_accessed": ts,
                "access_count": 0,
                "importance": max(0.0, min(1.0, importance)),
            }

        while len(self._cache) > self.max_size:
            self._evict()

