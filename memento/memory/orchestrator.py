import re
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

# Common English stopwords excluded from term-overlap scoring so that ranking is
# driven by content words rather than function words.
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at", "by",
    "for", "with", "from", "into", "onto", "over", "under", "is", "are", "was",
    "were", "be", "been", "being", "as", "that", "this", "these", "those", "it",
    "its", "they", "them", "their", "we", "us", "our", "you", "your", "i", "he",
    "she", "his", "her", "do", "does", "did", "done", "not", "no", "than",
    "then", "so", "if", "out", "up", "down", "off", "per", "via", "many", "one",
    "more", "most", "some", "any", "all", "each", "such", "without", "within",
    "across", "onto", "using", "use", "uses", "used",
})

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    """Lowercase, split on non-alphanumerics, drop stopwords and 1-char tokens."""
    if not text:
        return []
    return [
        t for t in _TOKEN_RE.findall(text.lower())
        if len(t) > 1 and t not in _STOPWORDS
    ]


def _overlap_score(query_tokens: set[str], memory_text: str) -> float:
    """Deterministic relevance score: fraction of query content tokens present
    in the candidate memory text. Higher means more relevant.

    Uses |query ∩ memory| / |query| so a candidate that contains more of the
    query's content words ranks above one that shares fewer, independent of
    which tier it came from.
    """
    if not query_tokens:
        return 0.0
    mem_tokens = set(_tokenize(memory_text))
    if not mem_tokens:
        return 0.0
    inter = query_tokens & mem_tokens
    return len(inter) / len(query_tokens)

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
        self._vsa_index.load_from_db()
        logger.info("VSA index enabled for O(1) relational queries")

    def disable_vsa_index(self) -> None:
        self._vsa_index = None
        logger.info("VSA index disabled")

    def add(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        tier: str = "semantic",
        importance: float = 0.5,
    ) -> str:
        mem_id = str(uuid.uuid4())

        if tier == "working":
            self.l1.add(mem_id, content, metadata, importance=importance)
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
        vsa_results: List[Dict[str, Any]] = []
        if self._vsa_index and tier in ("episodic", "semantic", "all"):
            vsa_ids = self._vsa_index.query_by_entity(query, top_k=limit)
            if vsa_ids:
                vsa_results = self._fetch_by_ids(vsa_ids, tier)
                if tier != "all":
                    return vsa_results

        if tier == "all":
            l3_results = self.l3.search(query, limit)
            l2_results = self.l2.search(query, limit)
            l1_items = self.l1.get_all()
            l1_formatted = [
                {"id": item["id"], "memory": item["content"], "metadata": item.get("metadata", {}), "memory_tier": "working"}
                for item in l1_items
            ]
            # Whole-string LIKE in the tier searches misses paraphrase queries,
            # so additionally gather token-level candidates directly from the
            # store. This only widens what we have to RANK; final ordering is by
            # global relevance, not retrieval source.
            token_candidates = self._gather_token_candidates(query, limit)

            # Global relevance-ranked fusion: dedup by id, score every candidate
            # by query-term overlap, then sort by score (desc) with a stable
            # tiebreak on original merge order so runs are deterministic.
            query_tokens = set(_tokenize(query))
            merged: List[Dict[str, Any]] = []
            seen: set[str] = set()
            for item in (
                vsa_results + l3_results + l2_results + l1_formatted + token_candidates
            ):
                item_id = item.get("id")
                if item_id in seen:
                    continue
                seen.add(item_id)
                merged.append(item)

            ranked = sorted(
                enumerate(merged),
                key=lambda pair: (-_overlap_score(query_tokens, pair[1].get("memory", "")), pair[0]),
            )
            return [item for _, item in ranked]
        elif tier == "working":
            return self.l1.get_all()
        elif tier == "episodic":
            return self.l2.search(query, limit)
        elif tier == "semantic":
            return self.l3.search(query, limit)
        else:
            raise ValueError(f"Unknown memory tier: {tier}")

    def _gather_token_candidates(
        self,
        query: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Gather candidate memories whose text contains ANY content token of
        the query, using per-token LIKE against the store.

        The tier searches use whole-string LIKE which returns nothing for
        paraphrase queries; this widens the candidate pool so the relevance
        ranker has the gold memory to surface. Ordering is left to the caller's
        global fusion. Failures are swallowed so search never breaks.
        """
        tokens = _tokenize(query)
        if not tokens:
            return []
        # Deduplicate while preserving order; cap to bound the OR clause.
        seen_tokens: List[str] = []
        for t in tokens:
            if t not in seen_tokens:
                seen_tokens.append(t)
        seen_tokens = seen_tokens[:24]

        clause = " OR ".join("text LIKE ?" for _ in seen_tokens)
        params: List[Any] = [f"%{t}%" for t in seen_tokens]
        sql = (
            "SELECT id, text, metadata, memory_tier FROM memories "
            f"WHERE {clause} ORDER BY created_at DESC LIMIT ?"
        )
        params.append(max(limit, 50))

        results: List[Dict[str, Any]] = []
        try:
            rows = self.db.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            logger.debug("token candidate gather failed: %s", exc)
            return results

        import json
        for r in rows:
            row_tier = r[3] if r[3] else "semantic"
            results.append({
                "id": r[0],
                "memory": r[1],
                "metadata": json.loads(r[2]) if r[2] else {},
                "memory_tier": row_tier,
            })
        return results

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
