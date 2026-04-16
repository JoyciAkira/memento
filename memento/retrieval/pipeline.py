from __future__ import annotations

from typing import Any, Awaitable, Callable

import aiosqlite

from memento.retrieval.lanes.dense import lane_dense
from memento.retrieval.lanes.fts import lane_fts
from memento.retrieval.lanes.recency import lane_recency
from memento.retrieval.types import ContextBundle, LaneTrace

EmbedFn = Callable[[str], Awaitable[list[float]]]


def rrf_fuse(
    *,
    lanes: dict[str, list[tuple[str, float]]],
    k: int,
    lane_weights: dict[str, float] | None = None,
    limit: int = 50,
) -> list[tuple[str, float]]:
    weights = lane_weights or {}
    scores: dict[str, float] = {}
    for lane_name, ranked in lanes.items():
        w = float(weights.get(lane_name, 1.0))
        for rank, (doc_id, _) in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + w * (1.0 / (k + rank))
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]


def _build_filter(filters: dict | None) -> tuple[str, list[Any]]:
    allowed = {"workspace_root", "workspace_name", "room", "module", "type"}
    clauses: list[str] = []
    params: list[Any] = []
    if isinstance(filters, dict):
        for k, v in filters.items():
            if k not in allowed:
                continue
            clauses.append("json_extract(metadata, ?) = ?")
            params.extend([f"$.{k}", v])
    sql = f" AND {' AND '.join(clauses)}" if clauses else ""
    return sql, params


async def retrieve_bundle(
    *,
    db_path: str,
    query: str,
    user_id: str,
    limit: int,
    filters: dict | None,
    embed_fn: EmbedFn,
    trace: bool,
) -> ContextBundle:
    filter_sql, filter_params = _build_filter(filters)
    traces: list[LaneTrace] = []

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        fts_ranked = await lane_fts(
            db=db,
            user_id=user_id,
            query=query,
            filter_sql=filter_sql,
            filter_params=filter_params,
            limit=200,
        )
        recent_ranked = await lane_recency(
            db=db,
            user_id=user_id,
            filter_sql=filter_sql,
            filter_params=filter_params,
            limit=200,
        )

        seen: set[str] = set()
        candidate_ids: list[str] = []
        for doc_id, _ in list(fts_ranked) + list(recent_ranked):
            if doc_id in seen:
                continue
            seen.add(doc_id)
            candidate_ids.append(doc_id)
            if len(candidate_ids) >= 400:
                break

        dense_ranked = await lane_dense(
            db=db,
            user_id=user_id,
            query=query,
            candidate_ids=candidate_ids,
            embed_fn=embed_fn,
        )

        fused = rrf_fuse(
            lanes={"fts": fts_ranked, "dense": dense_ranked, "recency": recent_ranked},
            k=60,
            lane_weights={"fts": 1.0, "dense": 1.0, "recency": 0.5},
            limit=limit,
        )

        ids = [doc_id for doc_id, _ in fused]
        results: list[dict[str, Any]] = []
        if ids:
            placeholders = ",".join(["?"] * len(ids))
            cur = await db.execute(
                f"SELECT id, text, created_at, metadata "
                f"FROM memories WHERE user_id = ? AND id IN ({placeholders})",
                (user_id, *ids),
            )
            rows = await cur.fetchall()
            row_map = {r["id"]: r for r in rows}
            for doc_id, score in fused:
                r = row_map.get(doc_id)
                if not r:
                    continue
                results.append({
                    "id": r["id"],
                    "memory": r["text"],
                    "created_at": r["created_at"],
                    "score": score,
                })

        if trace:
            traces.extend([
                {
                    "lane": "fts",
                    "considered": len(fts_ranked),
                    "returned": min(10, len(fts_ranked)),
                    "top": [{"id": i, "score": s} for i, s in fts_ranked[:10]],
                },
                {
                    "lane": "dense",
                    "considered": len(dense_ranked),
                    "returned": min(10, len(dense_ranked)),
                    "top": [{"id": i, "score": s} for i, s in dense_ranked[:10]],
                },
                {
                    "lane": "recency",
                    "considered": len(recent_ranked),
                    "returned": min(10, len(recent_ranked)),
                    "top": [{"id": i, "score": s} for i, s in recent_ranked[:10]],
                },
            ])

    return {
        "query": query,
        "results": results,
        "facts": [],
        "entities": [],
        "traces": traces,
    }
