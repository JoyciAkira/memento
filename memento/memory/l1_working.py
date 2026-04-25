import time
from collections import OrderedDict
from typing import List, Dict, Any, Iterable

class L1WorkingMemory:
    """
    Fast, in-memory volatile cache (L1).
    Used for immediate context window (e.g. current task, active file).
    Evicts oldest entries automatically when max_size is reached.
    """
    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()

    def add(self, entry_id: str, content: str, metadata: Dict[str, Any] = None) -> None:
        if entry_id in self._cache:
            del self._cache[entry_id]

        self._cache[entry_id] = {
            "id": entry_id,
            "content": content,
            "metadata": metadata or {},
            "timestamp": time.time()
        }

        if len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

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
            if not isinstance(entry_id, str) or not entry_id:
                continue
            self._cache[entry_id] = {
                "id": entry_id,
                "content": str(content),
                "metadata": metadata,
                "timestamp": ts,
            }

        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)
