import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

class L3SemanticMemory:
    """
    Long-term crystallized memory for facts, rules, and invariants.
    Saved to SQLite with memory_tier='semantic'.
    """
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def add(self, memory_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        now = datetime.now().isoformat()
        meta_str = json.dumps(metadata) if metadata else "{}"

        self.db.execute(
            """
            INSERT OR REPLACE INTO memories (id, text, metadata, memory_tier, created_at)
            VALUES (?, ?, ?, 'semantic', ?)
            """,
            (memory_id, content, meta_str, now)
        )
        self.db.commit()

    def search(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        cursor = self.db.execute(
            """
            SELECT id, text, metadata, memory_tier
            FROM memories
            WHERE memory_tier = 'semantic' AND text LIKE ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (f"%{query}%", limit)
        )
        rows = cursor.fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r[0],
                "memory": r[1],
                "metadata": json.loads(r[2]) if r[2] else {},
                "memory_tier": r[3]
            })
        return results
