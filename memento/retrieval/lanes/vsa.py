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
    vsa_index: Any | None = None,
) -> list[tuple[str, float]]:
    def _run() -> list[tuple[str, float]]:
        # Reuse a live, already-loaded VSAIndex when the caller provides one
        # (the provider keeps one warm and updated on every add). Building a
        # fresh VSAIndex + load_from_db() on every search re-derives all concept
        # vectors from scratch and dominates search latency.
        idx = vsa_index
        if idx is None:
            idx = VSAIndex(db_path)
            idx.load_from_db()
        ranked = idx.query(query, top_k=limit)
        if not filters:
            return ranked
        return ranked

    return await asyncio.to_thread(_run)
