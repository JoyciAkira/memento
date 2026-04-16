from __future__ import annotations

from typing import Any

import aiosqlite


async def lane_recency(
    *,
    db: aiosqlite.Connection,
    user_id: str,
    filter_sql: str,
    filter_params: list[Any],
    limit: int,
) -> list[tuple[str, float]]:
    cur = await db.execute(
        f"SELECT id FROM memories WHERE user_id = ? {filter_sql} "
        f"ORDER BY created_at DESC LIMIT ?",
        (user_id, *filter_params, limit),
    )
    rows = await cur.fetchall()
    return [(r["id"], float(limit - i)) for i, r in enumerate(rows)]
