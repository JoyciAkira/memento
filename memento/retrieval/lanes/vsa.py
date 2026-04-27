from __future__ import annotations

import asyncio
from typing import Any

from memento.memory.vsa_index import VSAIndex


async def lane_vsa(
    *,
    db_path: str,
    query: str,
    limit: int,
    filters: dict[str, Any] | None = None,
) -> list[tuple[str, float]]:
    def _run() -> list[tuple[str, float]]:
        idx = VSAIndex(db_path)
        idx.load_from_db()
        ranked = idx.query(query, top_k=limit)
        if not filters:
            return ranked
        return ranked

    return await asyncio.to_thread(_run)
