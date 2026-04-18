"""Quality metrics — measures health of the memory system."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiosqlite

logger = logging.getLogger(__name__)


class QualityMetrics:
    """Computes quality and health metrics for the Memento memory system."""

    COVERAGE_THRESHOLD = 0.5
    STALE_DAYS = 60

    def __init__(self, db_path: str, kg_db_path: str = None):
        self.db_path = db_path
        self.kg_db_path = kg_db_path

    async def memory_stats(self) -> Dict[str, Any]:
        """Basic memory statistics."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM memories")
            total = await cur.fetchone()
            cur = await db.execute(
                "SELECT COUNT(*) FROM memories m LEFT JOIN memory_meta mm ON m.id = mm.id WHERE COALESCE(mm.is_deleted, 0) = 0"
            )
            active = await cur.fetchone()
            cur = await db.execute(
                "SELECT COUNT(*) FROM memory_meta WHERE is_deleted = 1"
            )
            deleted = await cur.fetchone()
            cur = await db.execute(
                "SELECT COUNT(*) FROM memory_meta WHERE delete_reason = 'consolidated'"
            )
            consolidated = await cur.fetchone()

            # Age distribution
            cur = await db.execute(
                "SELECT created_at FROM memories WHERE COALESCE((SELECT is_deleted FROM memory_meta WHERE memory_meta.id = memories.id), 0) = 0"
            )
            with_ages = await cur.fetchall()
            ages = []
            for row in with_ages:
                try:
                    ct = datetime.fromisoformat(row[0])
                    days = (datetime.now() - ct).total_seconds() / 86400
                    ages.append(days)
                except (ValueError, TypeError):
                    pass

            age_stats = {}
            if ages:
                age_stats = {
                    "avg_days": round(sum(ages) / len(ages), 1),
                    "max_days": round(max(ages), 1),
                    "min_days": round(min(ages), 1),
                    "median_days": round(sorted(ages)[len(ages) // 2], 1),
                }

            # User distribution
            cur = await db.execute(
                "SELECT user_id, COUNT(*) as cnt FROM memories GROUP BY user_id ORDER BY cnt DESC LIMIT 10"
            )
            users = await cur.fetchall()

            return {
                "total_memories": total[0] if total else 0,
                "active_memories": active[0] if active else 0,
                "deleted_memories": deleted[0] if deleted else 0,
                "consolidated_memories": consolidated[0] if consolidated else 0,
                "age_distribution": age_stats,
                "users": [{"user_id": r[0], "count": r[1]} for r in users],
            }

    async def kg_health(self) -> Dict[str, Any]:
        """Knowledge graph health metrics."""
        if not self.kg_db_path:
            return {"error": "KG DB path not configured"}

        import sqlite3

        try:
            conn = sqlite3.connect(self.kg_db_path)
            entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()
            triples = conn.execute("SELECT COUNT(*) FROM triples").fetchone()
            current = conn.execute(
                "SELECT COUNT(*) FROM triples WHERE valid_to IS NULL"
            ).fetchone()
            expired = triples[0] - current[0] if triples else 0

            # Predicate distribution
            predicates = conn.execute(
                "SELECT predicate, COUNT(*) as cnt FROM triples GROUP BY predicate ORDER BY cnt DESC LIMIT 20"
            ).fetchall()

            # Entity type distribution
            types = conn.execute(
                "SELECT type, COUNT(*) as cnt FROM entities GROUP BY type ORDER BY cnt DESC LIMIT 20"
            ).fetchall()

            # Temporal coverage
            with_dates = conn.execute(
                "SELECT valid_from FROM triples WHERE valid_from IS NOT NULL LIMIT 1000"
            ).fetchall()
            dated = 0
            for row in with_dates:
                try:
                    datetime.fromisoformat(row[0])
                    dated += 1
                except (ValueError, TypeError):
                    pass

            conn.close()

            return {
                "entities": entities[0] if entities else 0,
                "total_triples": triples[0] if triples else 0,
                "current_triples": current[0] if current else 0,
                "expired_triples": expired,
                "temporal_coverage": (
                    f"{dated}/{triples[0]}" if triples else "N/A"
                ),
                "top_predicates": [
                    {"predicate": r[0], "count": r[1]} for r in predicates
                ],
                "entity_types": [
                    {"type": r[0], "count": r[1]} for r in types
                ],
            }
        except Exception as e:
            logger.error(f"KG health check error: {e}")
            return {"error": str(e)}

    async def consolidation_effectiveness(self) -> Dict[str, Any]:
        """Measure how effective consolidation has been."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT COUNT(*) FROM consolidation_log"
            )
            log_count = await cur.fetchone()
            cur = await db.execute(
                "SELECT COALESCE(SUM(source_count), 0) FROM consolidation_log"
            )
            total_fused = await cur.fetchone()
            cur = await db.execute(
                "SELECT AVG(source_count) FROM consolidation_log WHERE source_count > 0"
            )
            avg_sources = await cur.fetchone()

            return {
                "consolidation_runs": log_count[0] if log_count else 0,
                "total_memories_fused": total_fused[0] if total_fused else 0,
                "avg_sources_per_run": (
                    round(avg_sources[0], 2)
                    if avg_sources and avg_sources[0]
                    else 0
                ),
            }

    async def extraction_coverage(self) -> Dict[str, Any]:
        """Measure KG extraction coverage."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM memories")
            total = await cur.fetchone()
            cur = await db.execute(
                "SELECT COUNT(*) FROM kg_extraction_log"
            )
            extracted = await cur.fetchone()
            cur = await db.execute(
                "SELECT COUNT(*) FROM kg_extraction_log WHERE entities_found > 0"
            )
            with_entities = await cur.fetchone()
            cur = await db.execute(
                "SELECT COUNT(*) FROM kg_extraction_log WHERE triples_found > 0"
            )
            with_triples = await cur.fetchone()
            cur = await db.execute(
                "SELECT COUNT(*) FROM kg_extraction_log WHERE extraction_error IS NOT NULL"
            )
            with_errors = await cur.fetchone()

            coverage = (
                (extracted[0] / total[0] * 100) if total and total[0] > 0 else 0
            )

            return {
                "total_memories": total[0] if total else 0,
                "extracted_memories": extracted[0] if extracted else 0,
                "with_entities": with_entities[0] if with_entities else 0,
                "with_triples": with_triples[0] if with_triples else 0,
                "with_errors": with_errors[0] if with_errors else 0,
                "coverage_percent": round(coverage, 1),
            }

    async def system_health(self) -> Dict[str, Any]:
        """Combined system health report."""
        memory = await self.memory_stats()
        kg = await self.kg_health()
        consolidation = await self.consolidation_effectiveness()
        extraction = await self.extraction_coverage()

        # Health score (0-100)
        score = 0
        score += min(memory.get("active_memories", 0) / 10, 15)
        score += min(kg.get("entities", 0) / 5, 15)
        score += min(kg.get("current_triples", 0) / 10, 15)
        score += min(extraction.get("coverage_percent", 0) / 10, 15)
        score += min(consolidation.get("consolidation_runs", 0) * 2, 10)
        score += (
            15
            if extraction.get("with_errors", 0) == 0
            and memory.get("active_memories", 0) > 0
            else 0
        )
        score += (
            15
            if memory.get("deleted_memories", 0)
            < memory.get("active_memories", 0) * 0.3
            else 0
        )

        return {
            "health_score": round(min(score, 100)),
            "memory": memory,
            "knowledge_graph": kg,
            "consolidation": consolidation,
            "extraction": extraction,
        }

    async def compute_memory_health(self) -> Dict[str, Any]:
        """Compute overall memory health score (0-100)."""
        async with aiosqlite.connect(self.db_path) as db:
            total_cursor = await db.execute(
                "SELECT COUNT(*) FROM memory_meta WHERE is_deleted = 0"
            )
            total_row = await total_cursor.fetchone()
            total = total_row[0] if total_row else 0

            if total == 0:
                return {
                    "health_score": 0,
                    "factors": {"coverage": 0, "freshness": 0, "size_health": 0, "redundancy": 100},
                    "total_memories": 0,
                }

            fresh_cursor = await db.execute(
                """SELECT COUNT(*) FROM memory_meta
                   WHERE is_deleted = 0
                   AND last_accessed_at IS NOT NULL
                   AND last_accessed_at >= datetime('now', '-30 days')"""
            )
            fresh_row = await fresh_cursor.fetchone()
            fresh_count = fresh_row[0] if fresh_row else 0
            freshness = (fresh_count / total) * 100

            if total < 10:
                size_health = (total / 10) * 100
            elif total > 10000:
                size_health = max(0, 100 - (total - 10000) / 100)
            else:
                size_health = 100

            try:
                merge_cursor = await db.execute(
                    "SELECT COUNT(*) FROM consolidation_log"
                )
                merge_row = await merge_cursor.fetchone()
                merge_count = merge_row[0] if merge_row else 0
            except Exception:
                merge_count = 0
            redundancy = 100 - min(merge_count * 2, 50)

            coverage_data = await self.compute_coverage()
            coverage_score = coverage_data.get("coverage_score", 0)

            score = (
                freshness * 0.30
                + coverage_score * 0.25
                + size_health * 0.20
                + redundancy * 0.25
            )
            score = round(min(max(score, 0), 100))

            return {
                "health_score": score,
                "factors": {
                    "coverage": round(coverage_score, 1),
                    "freshness": round(freshness, 1),
                    "size_health": round(size_health, 1),
                    "redundancy": round(redundancy, 1),
                },
                "total_memories": total,
            }

    async def compute_coverage(self) -> Dict[str, Any]:
        """Analyze memory coverage — how many distinct topics are represented."""
        async with aiosqlite.connect(self.db_path) as db:
            count_cursor = await db.execute(
                """SELECT COUNT(*) FROM memories m
                   JOIN memory_meta mm ON m.id = mm.id
                   WHERE mm.is_deleted = 0"""
            )
            count_row = await count_cursor.fetchone()
            total = count_row[0] if count_row else 0

            if total == 0:
                return {
                    "coverage_score": 0,
                    "total_memories": 0,
                    "estimated_topics": 0,
                    "top_terms": [],
                }

            rows_cursor = await db.execute(
                """SELECT m.text FROM memories m
                   JOIN memory_meta mm ON m.id = mm.id
                   WHERE mm.is_deleted = 0"""
            )
            rows = await rows_cursor.fetchall()

            stop_words = {
                "the", "a", "an", "is", "are", "was", "were", "be", "been",
                "have", "has", "had", "do", "does", "did", "will", "would",
                "could", "should", "may", "might", "can", "to", "of", "in",
                "for", "on", "with", "at", "by", "from", "as", "into",
                "through", "during", "before", "after", "and", "but", "or",
                "not", "so", "if", "when", "where", "how", "what", "which",
                "who", "this", "that", "these", "those", "it", "its",
            }

            word_freq: Dict[str, int] = {}
            for row in rows:
                text = row[0] or ""
                words = text.lower().split()
                for word in words:
                    clean = word.strip(".,;:!?'\"()[]{}").strip()
                    if len(clean) > 2 and clean not in stop_words:
                        word_freq[clean] = word_freq.get(clean, 0) + 1

            unique_terms = len(word_freq)
            coverage_score = min((unique_terms / max(total, 1)) * 50, 100)
            top_terms = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:20]

            return {
                "coverage_score": round(coverage_score, 1),
                "total_memories": total,
                "estimated_topics": unique_terms,
                "top_terms": [{"term": t, "count": c} for t, c in top_terms],
            }

    async def identify_stale_memories(self, days: int = 60) -> List[Dict[str, Any]]:
        """Find memories that haven't been accessed in N days."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT mm.id, m.text, mm.created_at, mm.last_accessed_at
                   FROM memory_meta mm
                   JOIN memories m ON mm.id = m.id
                   WHERE mm.is_deleted = 0
                   AND (mm.last_accessed_at IS NULL
                        OR mm.last_accessed_at < datetime('now', ?))
                   ORDER BY mm.created_at ASC
                   LIMIT 50""",
                (f"-{days} days",),
            )
            rows = await cursor.fetchall()

            now = datetime.now()
            result = []
            for mem_id, text, created_at, last_accessed in rows:
                if last_accessed:
                    try:
                        accessed_dt = datetime.fromisoformat(last_accessed)
                        days_since = (now - accessed_dt).days
                    except (ValueError, TypeError):
                        days_since = days
                else:
                    try:
                        created_dt = datetime.fromisoformat(created_at)
                        days_since = (now - created_dt).days
                    except (ValueError, TypeError):
                        days_since = days

                result.append({
                    "id": mem_id,
                    "text": (text[:100] + "...") if text and len(text) > 100 else text,
                    "days_since_access": days_since,
                    "created_at": created_at,
                })

            return result

    async def identify_orphan_memories(self) -> List[Dict[str, Any]]:
        """Find memories with 0 hits and no references in knowledge graph."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT mm.id, m.text, mm.created_at
                   FROM memory_meta mm
                   JOIN memories m ON mm.id = m.id
                   WHERE mm.is_deleted = 0 AND COALESCE(mm.hit_count, 0) = 0
                   ORDER BY mm.created_at ASC
                   LIMIT 50""",
            )
            rows = await cursor.fetchall()

            return [
                {
                    "id": row[0],
                    "text": (row[1][:100] + "...") if row[1] and len(row[1]) > 100 else row[1],
                    "created_at": row[2],
                }
                for row in rows
            ]

    async def get_quality_report(self) -> Dict[str, Any]:
        """Full quality report combining all metrics."""
        health = await self.compute_memory_health()
        coverage = await self.compute_coverage()
        stale = await self.identify_stale_memories()
        orphans = await self.identify_orphan_memories()

        return {
            "health_score": health["health_score"],
            "health_factors": health["factors"],
            "coverage": coverage,
            "stale_memories": stale,
            "stale_count": len(stale),
            "orphan_memories": orphans,
            "orphan_count": len(orphans),
            "total_memories": health["total_memories"],
        }

    async def record_evaluation(
        self, memory_id: str, score: float, reason: str = ""
    ) -> None:
        """Record a quality evaluation for a specific memory."""
        import uuid

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """CREATE TABLE IF NOT EXISTS quality_evaluations (
                    id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    score REAL NOT NULL,
                    reason TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )"""
            )
            eval_id = str(uuid.uuid4())
            now = datetime.now().isoformat()
            await db.execute(
                "INSERT INTO quality_evaluations (id, memory_id, score, reason, created_at) VALUES (?, ?, ?, ?, ?)",
                (eval_id, memory_id, score, reason, now),
            )
            await db.commit()
            logger.info(
                "Recorded quality evaluation for memory %s: score=%s",
                memory_id,
                score,
            )
