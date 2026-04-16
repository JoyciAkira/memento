from __future__ import annotations

import json
import math
from typing import Awaitable, Callable

import aiosqlite

EmbedFn = Callable[[str], Awaitable[list[float]]]


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    n1 = math.sqrt(sum(a * a for a in vec1))
    n2 = math.sqrt(sum(b * b for b in vec2))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return dot / (n1 * n2)


async def lane_dense(
    *,
    db: aiosqlite.Connection,
    user_id: str,
    query: str,
    candidate_ids: list[str],
    embed_fn: EmbedFn,
) -> list[tuple[str, float]]:
    query_vec = await embed_fn(query)
    if not candidate_ids:
        return []
    placeholders = ",".join(["?"] * len(candidate_ids))
    cur = await db.execute(
        f"SELECT m.id, e.embedding FROM memories m "
        f"LEFT JOIN memory_embeddings e ON m.id = e.id "
        f"WHERE m.user_id = ? AND m.id IN ({placeholders})",
        (user_id, *candidate_ids),
    )
    rows = await cur.fetchall()
    scored: list[tuple[str, float]] = []
    for r in rows:
        emb_str = r["embedding"]
        if not emb_str:
            scored.append((r["id"], 0.0))
            continue
        try:
            vec = json.loads(emb_str)
        except Exception:
            scored.append((r["id"], 0.0))
            continue
        scored.append((r["id"], float(cosine_similarity(query_vec, vec))))
    return sorted(scored, key=lambda x: x[1], reverse=True)
