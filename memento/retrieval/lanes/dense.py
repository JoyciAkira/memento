from __future__ import annotations

import json
from typing import Awaitable, Callable

import aiosqlite

from memento.math_utils import cosine_similarity

EmbedFn = Callable[[str], Awaitable[list[float]]]


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
    if not query_vec:
        return [(cid, 0.0) for cid in candidate_ids]

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
