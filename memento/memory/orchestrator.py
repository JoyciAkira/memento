import sqlite3
import uuid
import logging
from typing import List, Dict, Any, Optional

from memento.memory.l1_working import L1WorkingMemory
from memento.memory.l2_episodic import L2EpisodicMemory
from memento.memory.l3_semantic import L3SemanticMemory
from memento.memory.vsa_index import VSAIndex
from memento.memory.hdc import HDCEncoder

logger = logging.getLogger(__name__)

class MemoryOrchestrator:
    """
    Coordinates L1, L2, and L3 memory layers with optional VSA-accelerated retrieval.
    - L1: Volatile working memory (in-memory cache)
    - L2: Episodic memory (trajectories, experiences)
    - L3: Semantic memory (facts, rules, crystallized knowledge)
    - VSA Index: O(1) relational query acceleration via Hyperdimensional Computing
    """
    def __init__(self, db: sqlite3.Connection, hdc_encoder: Optional[HDCEncoder] = None):
        self.db = db
        self.l1 = L1WorkingMemory()
        self.l2 = L2EpisodicMemory(db)
        self.l3 = L3SemanticMemory(db)
        self._hdc = hdc_encoder or HDCEncoder()
        self._vsa_index: Optional[VSAIndex] = None

    def enable_vsa_index(self, db_path: str) -> None:
        self._vsa_index = VSAIndex(db_path, hdc=self._hdc)
        logger.info("VSA index enabled for O(1) relational queries")

    def disable_vsa_index(self) -> None:
        self._vsa_index = None
        logger.info("VSA index disabled")

    def add(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        tier: str = "semantic"
    ) -> str:
        mem_id = str(uuid.uuid4())

        if tier == "working":
            self.l1.add(mem_id, content, metadata)
        elif tier == "episodic":
            self.l2.add(mem_id, content, metadata)
            if self._vsa_index:
                self._vsa_index.index_memory(mem_id, content, metadata)
        elif tier == "semantic":
            self.l3.add(mem_id, content, metadata)
            if self._vsa_index:
                self._vsa_index.index_memory(mem_id, content, metadata)
        else:
            raise ValueError(f"Unknown memory tier: {tier}")

        return mem_id

    def search(
        self,
        query: str,
        tier: str = "all",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        if self._vsa_index and tier in ("episodic", "semantic", "all"):
            vsa_ids = self._vsa_index.query_by_entity(query, top_k=limit)
            if vsa_ids:
                return self._fetch_by_ids(vsa_ids, tier)

        if tier == "all":
            l3_results = self.l3.search(query, limit)
            l2_results = self.l2.search(query, limit)
            l1_items = self.l1.get_all()
            l1_formatted = [
                {"id": item["id"], "memory": item["content"], "metadata": item.get("metadata", {}), "memory_tier": "working"}
                for item in l1_items
            ]
            return l3_results + l2_results + l1_formatted
        elif tier == "working":
            return self.l1.get_all()
        elif tier == "episodic":
            return self.l2.search(query, limit)
        elif tier == "semantic":
            return self.l3.search(query, limit)
        else:
            raise ValueError(f"Unknown memory tier: {tier}")

    def search_relation(
        self,
        subject: str,
        obj: str,
        predicate: str = "relates_to"
    ) -> List[Dict[str, Any]]:
        if not self._vsa_index:
            raise RuntimeError("VSA index not enabled. Call enable_vsa_index() first.")
        mem_ids = self._vsa_index.query_relation(subject, obj, predicate)
        return self._fetch_by_ids(mem_ids, tier="all")

    def _fetch_by_ids(
        self,
        mem_ids: List[str],
        tier: str
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        placeholders = ",".join("?" * len(mem_ids)) if mem_ids else "''"
        query = f"SELECT id, text, metadata, memory_tier FROM memories WHERE id IN ({placeholders})"
        rows = self.db.execute(query, mem_ids).fetchall()
        for r in rows:
            row_tier = r[3] if r[3] else "semantic"
            if tier != "all" and row_tier != tier:
                continue
            import json
            results.append({
                "id": r[0],
                "memory": r[1],
                "metadata": json.loads(r[2]) if r[2] else {},
                "memory_tier": row_tier
            })
        return results

    def clear_l1(self) -> None:
        self.l1.clear()

    def get_vsa_stats(self) -> Optional[Dict[str, Any]]:
        if self._vsa_index:
            return self._vsa_index.get_index_stats()
        return None
