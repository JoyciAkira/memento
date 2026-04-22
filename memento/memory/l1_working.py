import time
from collections import OrderedDict
from typing import List, Dict, Any

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
