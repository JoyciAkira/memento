from __future__ import annotations

import re
from typing import Any

import aiosqlite


def build_fts_query(query: str) -> str:
    terms = re.findall(r"[A-Za-z0-9_]{3,}", query or "")
    fts_query = " OR ".join([f"{t}*" for t in terms]) if terms else (query or "").strip()
    return fts_query or "*"


async def lane_fts(
    *,
    db: aiosqlite.Connection,
    user_id: str,
    query: str,
    filter_sql: str,
    filter_params: list[Any],
    limit: int,
) -> list[tuple[str, float]]:
    fts_query = build_fts_query(query)
    try:
        cur = await db.execute(
            f"SELECT id, bm25(memories) AS fts_score "
            f"FROM memories WHERE user_id = ? AND memories MATCH ? {filter_sql} LIMIT ?",
            (user_id, fts_query, *filter_params, limit),
        )
        rows = await cur.fetchall()
        return [(r["id"], float(r["fts_score"])) for r in rows]
    except Exception:
        cur = await db.execute(
            f"SELECT id, 1000000.0 AS fts_score "
            f"FROM memories WHERE user_id = ? AND text LIKE ? {filter_sql} LIMIT ?",
            (user_id, f"%{query}%", *filter_params, limit),
        )
        rows = await cur.fetchall()
        return [(r["id"], float(r["fts_score"])) for r in rows]
