import sqlite3
import json
import logging
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

    def extract_entities(self, text: str) -> List[str]:
        words = text.lower().split()
        entities = [w for w in words if len(w) >= 3][:10]
        return entities

    def index_memory(self, memory_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        entities = self.extract_entities(text)
        self._entity_cache[memory_id] = entities

        for entity in entities:
            self.hdc.concept(entity)

        self._persist_memory(memory_id, text, entities)

    def unindex_memory(self, memory_id: str) -> None:
        self._entity_cache.pop(memory_id, None)
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("DELETE FROM _vsa_entities WHERE memory_id = ?", (memory_id,))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _persist_memory(self, memory_id: str, text: str, entities: List[str]) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _vsa_entities (
                    memory_id TEXT PRIMARY KEY,
                    text TEXT,
                    entities TEXT
                )
            """)
            conn.execute(
                "INSERT OR REPLACE INTO _vsa_entities (memory_id, text, entities) VALUES (?, ?, ?)",
                (memory_id, text, json.dumps(entities))
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to persist VSA entity: {e}")

    def load_from_db(self) -> None:
        """Load VSA entities from SQLite on startup."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _vsa_entities (
                    memory_id TEXT PRIMARY KEY,
                    text TEXT,
                    entities TEXT
                )
            """)
            rows = conn.execute("SELECT memory_id, text, entities FROM _vsa_entities").fetchall()
            conn.close()

            for memory_id, text, entities_json in rows:
                entities = json.loads(entities_json)
                self._entity_cache[memory_id] = entities
                for entity in entities:
                    self.hdc.concept(entity)

            logger.info(f"Loaded {len(self._entity_cache)} VSA entries from DB")
        except Exception as e:
            logger.warning(f"Failed to load VSA from DB: {e}")

    def query_by_entity(self, entity: str, top_k: int = 10) -> List[str]:
        try:
            related = self.hdc.decode_relation(self.hdc.concept(entity), top_k=top_k * 2)
            memory_ids: List[str] = []
            seen: Set[str] = set()

            for name, score in related:
                if score < 0.5:
                    continue
                for mem_id, entities in self._entity_cache.items():
                    if name in entities and mem_id not in seen:
                        memory_ids.append(mem_id)
                        seen.add(mem_id)
                        if len(memory_ids) >= top_k:
                            return memory_ids

            return memory_ids
        except Exception as e:
            logger.warning(f"VSA query failed: {e}")
            return []

    def query_relation(self, subject: str, obj: str, predicate: str = "relates_to") -> List[str]:
        try:
            rel_hv = self.hdc.encode_relation(subject, predicate, obj)
            candidates = set()
            for mem_id, entities in self._entity_cache.items():
                for e in entities:
                    if e in (subject.lower(), obj.lower()):
                        candidates.add(mem_id)
            return list(candidates)
        except Exception as e:
            logger.warning(f"VSA relation query failed: {e}")
            return []

    def get_index_stats(self) -> Dict[str, Any]:
        return {
            "indexed_memories": len(self._entity_cache),
            "total_entities": sum(len(e) for e in self._entity_cache.values()),
            "unique_concepts": len(self.hdc._concept_vectors),
        }
