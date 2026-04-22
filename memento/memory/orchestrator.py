import sqlite3
import uuid
from typing import List, Dict, Any, Optional

from memento.memory.l1_working import L1WorkingMemory
from memento.memory.l2_episodic import L2EpisodicMemory
from memento.memory.l3_semantic import L3SemanticMemory

class MemoryOrchestrator:
    """
    Coordinates L1, L2, and L3 memory layers.
    - L1: Volatile working memory (in-memory cache)
    - L2: Episodic memory (trajectories, experiences)
    - L3: Semantic memory (facts, rules, crystallized knowledge)
    """
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self.l1 = L1WorkingMemory()
        self.l2 = L2EpisodicMemory(db)
        self.l3 = L3SemanticMemory(db)

    def add(self, content: str, metadata: Optional[Dict[str, Any]] = None, tier: str = "semantic") -> str:
        mem_id = str(uuid.uuid4())

        if tier == "working":
            self.l1.add(mem_id, content, metadata)
        elif tier == "episodic":
            self.l2.add(mem_id, content, metadata)
        elif tier == "semantic":
            self.l3.add(mem_id, content, metadata)
        else:
            raise ValueError(f"Unknown memory tier: {tier}")

        return mem_id

    def search(self, query: str, tier: str = "all", limit: int = 100) -> List[Dict[str, Any]]:
        if tier == "all":
            l3_results = self.l3.search(query, limit)
            l2_results = self.l2.search(query, limit)
            l1_results = self.l1.get_all()
            return l3_results + l2_results + l1_results
        elif tier == "working":
            return self.l1.get_all()
        elif tier == "episodic":
            return self.l2.search(query, limit)
        elif tier == "semantic":
            return self.l3.search(query, limit)
        else:
            raise ValueError(f"Unknown memory tier: {tier}")

    def clear_l1(self) -> None:
        self.l1.clear()
