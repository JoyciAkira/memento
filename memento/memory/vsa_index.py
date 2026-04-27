import sqlite3
import json
import logging
import re
from typing import Dict, List, Any, Optional, Set
from memento.memory.hdc import HDCEncoder

logger = logging.getLogger(__name__)

class VSAIndex:
    """
    Maintains a VSA index over stored memories for O(1) relational queries.
    Indexes memories by extracting entities and binding them into hypervectors.
    Persists hypervectors to SQLite so they survive process restarts.
    """
    def __init__(self, db_path: str, hdc: Optional[HDCEncoder] = None):
        self.db_path = db_path
        self.hdc = hdc or HDCEncoder()
        self._entity_cache: Dict[str, List[str]] = {}
        self._vector_cache: Dict[str, int] = {}

    def extract_entities(self, text: str) -> List[str]:
        words = re.findall(r"[A-Za-z0-9_][A-Za-z0-9_+.#/-]{2,}", (text or "").lower())
        seen: Set[str] = set()
        entities: List[str] = []
        for w in words:
            normalized = w.strip(".,:;()[]{}\"'")
            if len(normalized) < 3 or normalized in seen:
                continue
            seen.add(normalized)
            entities.append(normalized)
            if len(entities) >= 32:
                break
        return entities

    def index_memory(self, memory_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        entities = self.extract_entities(text)
        self._entity_cache[memory_id] = entities

        for entity in entities:
            self.hdc.concept(entity)

        hv = self.hdc.encode_text(text, entities)
        relation_vectors = self._relation_vectors(text, entities, metadata or {})
        if relation_vectors:
            hv = self.hdc.bundle([hv, *relation_vectors])
        self._vector_cache[memory_id] = hv

        self._persist_memory(memory_id, text, entities, hv, metadata or {})

    def unindex_memory(self, memory_id: str) -> None:
        self._entity_cache.pop(memory_id, None)
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("DELETE FROM _vsa_entities WHERE memory_id = ?", (memory_id,))
            conn.execute("DELETE FROM _vsa_vectors WHERE memory_id = ?", (memory_id,))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _ensure_tables(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS _vsa_entities (
                memory_id TEXT PRIMARY KEY,
                text TEXT,
                entities TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS _vsa_vectors (
                memory_id TEXT PRIMARY KEY,
                hypervector BLOB NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vsa_entities_text ON _vsa_entities(memory_id)")

    def _persist_memory(
        self,
        memory_id: str,
        text: str,
        entities: List[str],
        hv: int,
        metadata: Dict[str, Any],
    ) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            self._ensure_tables(conn)
            conn.execute(
                "INSERT OR REPLACE INTO _vsa_entities (memory_id, text, entities) VALUES (?, ?, ?)",
                (memory_id, text, json.dumps(entities))
            )
            conn.execute(
                "INSERT OR REPLACE INTO _vsa_vectors (memory_id, hypervector, metadata, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                (memory_id, sqlite3.Binary(self.hdc.to_bytes(hv)), json.dumps(metadata)),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to persist VSA entity: {e}")

    def load_from_db(self) -> None:
        """Load VSA entities from SQLite on startup."""
        try:
            conn = sqlite3.connect(self.db_path)
            self._ensure_tables(conn)
            rows = conn.execute(
                "SELECT e.memory_id, e.text, e.entities, v.hypervector "
                "FROM _vsa_entities e LEFT JOIN _vsa_vectors v ON e.memory_id = v.memory_id"
            ).fetchall()
            conn.close()

            for memory_id, text, entities_json, hv_blob in rows:
                entities = json.loads(entities_json)
                self._entity_cache[memory_id] = entities
                for entity in entities:
                    self.hdc.concept(entity)
                if hv_blob:
                    self._vector_cache[memory_id] = self.hdc.from_bytes(hv_blob)
                else:
                    self._vector_cache[memory_id] = self.hdc.encode_text(text or "", entities)

            logger.info(f"Loaded {len(self._entity_cache)} VSA entries from DB")
        except Exception as e:
            logger.warning(f"Failed to load VSA from DB: {e}")

    def query_by_entity(self, entity: str, top_k: int = 10) -> List[str]:
        return [mid for mid, _ in self.query(entity, top_k=top_k)]

    def query(self, query: str, top_k: int = 10) -> List[tuple[str, float]]:
        try:
            if not self._vector_cache:
                self.load_from_db()
            entities = self.extract_entities(query)
            qv = self.hdc.encode_text(query, entities)
            scored = [
                (mem_id, self._score(qv, hv, entities, self._entity_cache.get(mem_id, [])))
                for mem_id, hv in self._vector_cache.items()
            ]
            scored.sort(key=lambda x: x[1], reverse=True)
            return scored[:top_k]
        except Exception as e:
            logger.warning(f"VSA query failed: {e}")
            return []

    def query_relation(self, subject: str, obj: str, predicate: str = "relates_to") -> List[str]:
        try:
            _rel_hv = self.hdc.encode_relation(subject, predicate, obj)
            candidates = set()
            for mem_id, entities in self._entity_cache.items():
                for e in entities:
                    if e in (subject.lower(), obj.lower()) or subject.lower() in e or obj.lower() in e:
                        candidates.add(mem_id)
            return list(candidates)
        except Exception as e:
            logger.warning(f"VSA relation query failed: {e}")
            return []

    def _score(
        self,
        query_hv: int,
        memory_hv: int,
        query_entities: List[str],
        memory_entities: List[str],
    ) -> float:
        hv_score = self.hdc.similarity(query_hv, memory_hv)
        if not query_entities or not memory_entities:
            return hv_score
        q = set(query_entities)
        m = set(memory_entities)
        overlap = len(q & m) / max(1, len(q | m))
        return 0.7 * hv_score + 0.3 * overlap

    def _relation_vectors(
        self,
        text: str,
        entities: List[str],
        metadata: Dict[str, Any],
    ) -> List[int]:
        vectors: List[int] = []
        tier = str(metadata.get("memory_tier") or metadata.get("type") or "").strip()
        if tier:
            vectors.append(self.hdc.encode_relation("__memory__", "has_type", tier))
        for key in ("workspace_name", "module", "room"):
            value = metadata.get(key)
            if value:
                vectors.append(self.hdc.encode_relation(str(key), "equals", str(value)))
        for i in range(max(0, len(entities) - 1)):
            vectors.append(self.hdc.encode_relation(entities[i], "near", entities[i + 1]))
        return vectors[:32]

    def get_index_stats(self) -> Dict[str, Any]:
        return {
            "indexed_memories": len(self._entity_cache),
            "total_entities": sum(len(e) for e in self._entity_cache.values()),
            "unique_concepts": len(self.hdc._concept_vectors),
            "stored_vectors": len(self._vector_cache),
        }
