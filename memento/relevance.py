"""Relevance tracking — hit counting, temporal boosting, and time decay for memories."""

import logging
import math
from datetime import datetime
from typing import Any, Dict, List

import aiosqlite

logger = logging.getLogger(__name__)


class RelevanceTracker:
    """Tracks memory access patterns and computes relevance scores."""

    DECAY_HALF_LIFE_DAYS = 30.0  # memories halve in relevance every 30 days without access
    BOOST_FACTOR = 1.5  # max boost multiplier for frequently accessed memories
    RECENT_ACCESS_BOOST = 0.3  # extra boost for memories accessed in last 24h

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def record_hit(self, memory_id: str) -> None:
        """Record that a memory was retrieved/accessed."""
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO memory_meta (id, created_at, updated_at, is_deleted)
                VALUES (
                    ?,
                    COALESCE((SELECT created_at FROM memories WHERE id = ?), ?),
                    ?, 0
                )
                """,
                (memory_id, memory_id, now, now),
            )
            await db.execute(
                """
                UPDATE memory_meta
                SET hit_count = COALESCE(hit_count, 0) + 1,
                    last_accessed_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, now, memory_id),
            )
            await db.commit()

    async def record_hits(self, memory_ids: List[str]) -> None:
        """Record hits for multiple memories at once (efficient batch)."""
        if not memory_ids:
            return
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            for mid in memory_ids:
                await db.execute(
                    """
                    INSERT OR IGNORE INTO memory_meta (id, created_at, updated_at, is_deleted)
                    VALUES (
                        ?,
                        COALESCE((SELECT created_at FROM memories WHERE id = ?), ?),
                        ?, 0
                    )
                    """,
                    (mid, mid, now, now),
                )
                await db.execute(
                    """
                    UPDATE memory_meta
                    SET hit_count = COALESCE(hit_count, 0) + 1,
                        last_accessed_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, mid),
                )
            await db.commit()

    def _compute_boost(self, hit_count: int, last_accessed: str | None, created_at: str | None) -> float:
        """Compute relevance boost from hit count, recency, and decay."""
        if hit_count == 0:
            return 1.0  # no data, neutral

        # Frequency boost: logarithmic scale, capped at BOOST_FACTOR
        freq_boost = min(math.log2(hit_count + 1) / 5.0, 1.0) * (self.BOOST_FACTOR - 1.0) + 1.0

        # Recency boost: accessed recently?
        recency_boost = 1.0
        if last_accessed:
            try:
                dt = datetime.fromisoformat(last_accessed)
                hours_since = (datetime.now() - dt).total_seconds() / 3600
                if hours_since < 24:
                    recency_boost = 1.0 + self.RECENT_ACCESS_BOOST
                elif hours_since < 168:  # within a week
                    recency_boost = 1.0 + self.RECENT_ACCESS_BOOST * 0.3
            except (ValueError, TypeError):
                pass

        # Time decay: older memories get lower scores
        decay = 1.0
        if created_at:
            try:
                ct = datetime.fromisoformat(created_at)
                days_old = (datetime.now() - ct).total_seconds() / 86400
                decay = math.exp(-0.693 * days_old / self.DECAY_HALF_LIFE_DAYS)
                decay = max(decay, 0.1)  # floor at 10%
            except (ValueError, TypeError):
                pass

        return freq_boost * recency_boost * decay

    async def get_boost(self, memory_id: str) -> float:
        """Calculate relevance boost for a single memory (1.0 = no change)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT hit_count, last_accessed_at, created_at FROM memory_meta WHERE id = ?",
                (memory_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return 1.0

            return self._compute_boost(
                hit_count=row["hit_count"] or 0,
                last_accessed=row["last_accessed_at"],
                created_at=row["created_at"],
            )

    async def get_boosts(self, memory_ids: List[str]) -> Dict[str, float]:
        """Get relevance boosts for multiple memories."""
        if not memory_ids:
            return {}
        boosts: Dict[str, float] = {}
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            placeholders = ",".join(["?"] * len(memory_ids))
            cursor = await db.execute(
                f"SELECT id, hit_count, last_accessed_at, created_at FROM memory_meta WHERE id IN ({placeholders})",
                memory_ids,
            )
            rows = await cursor.fetchall()
            for row in rows:
                mid = row["id"]
                boosts[mid] = self._compute_boost(
                    hit_count=row["hit_count"] or 0,
                    last_accessed=row["last_accessed_at"],
                    created_at=row["created_at"],
                )

        return boosts

    async def get_stats(self) -> Dict[str, Any]:
        """Return relevance statistics."""
        async with aiosqlite.connect(self.db_path) as db:
            total = await db.execute(
                "SELECT COUNT(*) FROM memory_meta WHERE COALESCE(is_deleted, 0) = 0"
            )
            total_row = await total.fetchone()

            with_hits = await db.execute(
                "SELECT COUNT(*) FROM memory_meta WHERE hit_count > 0 AND COALESCE(is_deleted, 0) = 0"
            )
            with_hits_row = await with_hits.fetchone()

            hot = await db.execute(
                "SELECT COUNT(*) FROM memory_meta WHERE hit_count >= 5 AND COALESCE(is_deleted, 0) = 0"
            )
            hot_row = await hot.fetchone()

            cold = await db.execute(
                "SELECT COUNT(*) FROM memory_meta WHERE (hit_count = 0 OR hit_count IS NULL) AND COALESCE(is_deleted, 0) = 0"
            )
            cold_row = await cold.fetchone()

            avg_hits = await db.execute(
                "SELECT AVG(hit_count) FROM memory_meta WHERE COALESCE(is_deleted, 0) = 0"
            )
            avg_hits_row = await avg_hits.fetchone()

            return {
                "total_memories": total_row[0] if total_row else 0,
                "with_hits": with_hits_row[0] if with_hits_row else 0,
                "hot_memories": hot_row[0] if hot_row else 0,
                "cold_memories": cold_row[0] if cold_row else 0,
                "avg_hit_count": round(avg_hits_row[0], 2) if avg_hits_row and avg_hits_row[0] else 0,
            }
