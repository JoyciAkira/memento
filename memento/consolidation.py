"""
consolidation.py — Auto-Consolidation Engine for Memento
=====================================================
Detects semantically similar memories and merges them into a single
enriched memory. Prevents duplicate accumulation and improves retrieval quality.
"""

import json
import logging
import math
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Set, Tuple

import aiosqlite

from memento.math_utils import cosine_similarity

logger = logging.getLogger(__name__)

# Similarity threshold for considering memories as duplicates
DEFAULT_SIMILARITY_THRESHOLD = 0.92
# Minimum age for a memory to be eligible for consolidation (avoid merging recent work)
DEFAULT_MIN_AGE_HOURS = 1
# Maximum number of memories to consolidate in one run
DEFAULT_BATCH_SIZE = 200


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec1 or not vec2:
        return 0.0
    if len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm_a = math.sqrt(sum(a * a for a in vec1))
    norm_b = math.sqrt(sum(b * b for b in vec2))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class UnionFind:
    """Union-Find data structure for transitive clustering."""

    def __init__(self):
        self.parent: Dict[str, str] = {}
        self.rank: Dict[str, int] = {}

    def find(self, x: str) -> str:
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0
            return x
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: str, y: str) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1


def _extract_sentences(text: str) -> List[str]:
    """Extract individual sentences from text, filtering very short ones."""
    import re

    # Split on sentence-ending punctuation followed by whitespace or end
    raw = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in raw if len(s.strip()) > 10]


def fuse_texts(texts: List[str], max_length: int = 2000) -> str:
    """
    Merge multiple memory texts into a single enriched text.
    Strategy: extract sentences from all sources, deduplicate, append unique ones.
    """
    seen: Set[str] = set()
    fragments: List[str] = []
    total_length = 0

    # Process longer texts first (they're likely more complete)
    for text in sorted(texts, key=len, reverse=True):
        for sentence in _extract_sentences(text):
            if sentence not in seen and total_length + len(sentence) + 2 <= max_length:
                seen.add(sentence)
                fragments.append(sentence)
                total_length += len(sentence) + 2  # +2 for separator

    if not fragments:
        # Fallback: use the longest original text
        return max(texts, key=len) if texts else ""

    return ". ".join(fragments)


def merge_metadatas(metadatas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge metadata dicts. Strategy:
    - Use metadata with the most keys as the base
    - Deep merge dicts, union lists, first-wins for primitives
    """
    if not metadatas:
        return {}
    if len(metadatas) == 1:
        return metadatas[0]

    # Find the metadata with the most keys as the base
    base = max(metadatas, key=lambda m: len(m) if isinstance(m, dict) else 0)

    merged = dict(base)
    for meta in metadatas[1:]:
        if not isinstance(meta, dict):
            continue
        for key, value in meta.items():
            if key not in merged:
                merged[key] = value
            elif isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = {**merged[key], **value}
            elif isinstance(merged[key], list) and isinstance(value, list):
                existing = set(
                    json.dumps(v, sort_keys=True) if isinstance(v, (dict, list))
                    else v
                    for v in merged[key]
                )
                for item in value:
                    item_key = (
                        json.dumps(item, sort_keys=True)
                        if isinstance(item, (dict, list))
                        else item
                    )
                    if item_key not in existing:
                        merged[key].append(item)
            # For primitives (str, int, etc.), first-wins (keep base value)

    return merged


class ConsolidationEngine:
    """Engine for detecting and merging similar memories."""

    def __init__(
        self,
        db_path: str,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        min_age_hours: float = DEFAULT_MIN_AGE_HOURS,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        self.db_path = db_path
        self.threshold = threshold
        self.min_age_hours = min_age_hours
        self.batch_size = batch_size

    async def find_similar_pairs(
        self,
    ) -> List[Tuple[str, str, float]]:
        """
        Find all pairs of memories with cosine similarity above threshold.
        Returns list of (id_a, id_b, similarity) tuples.
        Excludes already-deleted memories and goals.
        """
        cutoff = datetime.now() - timedelta(hours=self.min_age_hours)
        cutoff_str = cutoff.isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT m.id, m.text, e.embedding
                FROM memories m
                LEFT JOIN memory_embeddings e ON m.id = e.id
                LEFT JOIN memory_meta mm ON mm.id = m.id
                WHERE m.user_id = ?
                  AND COALESCE(mm.is_deleted, 0) = 0
                  AND m.created_at < ?
                ORDER BY m.created_at ASC
                LIMIT ?
                """,
                ("default", cutoff_str, self.batch_size),
            )
            rows = await cursor.fetchall()

        # Build embedding map
        embeddings: Dict[str, List[float]] = {}
        texts: Dict[str, str] = {}
        for row in rows:
            row_id = row["id"]
            emb_str = row["embedding"]
            if emb_str and emb_str != "[]":
                try:
                    embeddings[row_id] = json.loads(emb_str)
                    texts[row_id] = row["text"]
                except (json.JSONDecodeError, TypeError):
                    pass

        # Compare all pairs
        ids = list(embeddings.keys())
        if len(ids) > self.batch_size:
            ids = ids[:self.batch_size]
        pairs: List[Tuple[str, str, float]] = []
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                sim = cosine_similarity(embeddings[ids[i]], embeddings[ids[j]])
                if sim >= self.threshold:
                    pairs.append((ids[i], ids[j], sim))

        logger.info(
            f"Found {len(pairs)} similar pairs among {len(ids)} memories "
            f"(threshold={self.threshold:.2f})"
        )
        return pairs

    def cluster_pairs(
        self, pairs: List[Tuple[str, str, float]]
    ) -> Dict[str, List[str]]:
        """
        Cluster similar memories using Union-Find for transitive closure.
        A~B and B~C should merge A, B, C into one cluster.
        """
        uf = UnionFind()
        for id_a, id_b, _ in pairs:
            uf.union(id_a, id_b)

        clusters: Dict[str, set] = {}
        for id_a, id_b, _ in pairs:
            root = uf.find(id_a)
            if root not in clusters:
                clusters[root] = set()
            clusters[root].add(id_a)
            clusters[root].add(id_b)

        return {root: list(members) for root, members in clusters.items()}

    async def consolidate(self) -> Dict[str, Any]:
        """
        Run the full consolidation pipeline:
        1. Find similar pairs
        2. Cluster into groups
        3. Fuse each cluster into one memory
        4. Add the new memory
        5. Soft-delete old memories
        6. Log the operation
        Returns a summary dict.
        """
        logger.info("Starting memory consolidation...")

        pairs = await self.find_similar_pairs()
        if not pairs:
            return {"consolidated": 0, "pairs_found": 0, "clusters": 0}

        clusters = self.cluster_pairs(pairs)
        logger.info(f"Found {len(clusters)} clusters to consolidate")

        consolidated_count = 0
        total_deleted = 0

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            for root_id, members in clusters.items():
                if len(members) < 2:
                    continue

                # Gather texts and metadatas for this cluster
                texts: List[str] = []
                metadatas: List[Dict[str, Any]] = []
                text_by_id: Dict[str, str] = {}

                for mid in members:
                    cursor = await db.execute(
                        "SELECT m.text, m.metadata FROM memories m WHERE m.id = ?",
                        (mid,),
                    )
                    row = await cursor.fetchone()
                    if row:
                        texts.append(row["text"])
                        text_by_id[mid] = row["text"]
                        meta_str = row["metadata"] if row["metadata"] else "{}"
                        try:
                            meta = json.loads(meta_str) if meta_str else {}
                            if isinstance(meta, dict):
                                metadatas.append(meta)
                        except (json.JSONDecodeError, TypeError):
                            metadatas.append({})

                if not texts:
                    continue

                # Fuse texts and metadata
                fused_text = fuse_texts(texts)
                merged_meta = merge_metadatas(metadatas)
                merged_meta["consolidated_from"] = len(texts)
                merged_meta["consolidation_date"] = datetime.now().isoformat()

                # Find the best embedding (from longest text)
                best_emb_id = max(text_by_id, key=lambda mid: len(text_by_id[mid]))
                cursor = await db.execute(
                    "SELECT embedding FROM memory_embeddings WHERE id = ?",
                    (best_emb_id,),
                )
                emb_row = await cursor.fetchone()
                best_embedding = emb_row["embedding"] if emb_row else "[]"

                # Add the new consolidated memory
                new_id = str(uuid.uuid4())
                now = datetime.now().isoformat()
                meta_str = json.dumps(merged_meta) if merged_meta else "{}"
                emb_str = (
                    best_embedding if isinstance(best_embedding, str)
                    else json.dumps([])
                )

                await db.execute(
                    "INSERT INTO memories (id, user_id, text, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
                    (new_id, "default", fused_text, now, meta_str),
                )
                await db.execute(
                    "INSERT OR IGNORE INTO memory_meta (id, created_at, updated_at, is_deleted) VALUES (?, ?, ?, 0)",
                    (new_id, now, now),
                )
                await db.execute(
                    "INSERT OR REPLACE INTO memory_embeddings (id, embedding) VALUES (?, ?)",
                    (new_id, emb_str),
                )

                # Soft-delete old memories, pointing to the new one
                for old_id in members:
                    await db.execute(
                        """
                        INSERT OR IGNORE INTO memory_meta (id, created_at, updated_at, is_deleted)
                        VALUES (?, ?, ?, 0)
                        """,
                        (old_id, now, now),
                    )
                    await db.execute(
                        """
                        UPDATE memory_meta
                        SET is_deleted = 1,
                            deleted_at = ?,
                            delete_reason = ?,
                            supersedes_id = ?,
                            replaced_by_id = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            now,
                            "consolidated into " + new_id[:8],
                            new_id,
                            new_id,
                            now,
                            old_id,
                        ),
                    )

                # Log the consolidation
                await db.execute(
                    """
                    INSERT OR REPLACE INTO consolidation_log
                        (id, consolidated_into_id, source_ids, source_count,
                         fused_text_preview, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        new_id,
                        json.dumps(members),
                        len(members),
                        fused_text[:200],
                        now,
                    ),
                )

                await db.commit()
                consolidated_count += 1
                total_deleted += len(members)

        logger.info(
            f"Consolidation complete: {consolidated_count} new memories created, "
            f"{total_deleted} old memories superseded"
        )
        return {
            "consolidated": consolidated_count,
            "pairs_found": len(pairs),
            "clusters": len(clusters),
            "total_superseded": total_deleted,
        }
