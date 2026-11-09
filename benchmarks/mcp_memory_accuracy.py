#!/usr/bin/env python3
"""Accuracy benchmark for the retrieval paths agents actually use.

The sealed ``e2e_memory_accuracy.py`` benchmark drives ``MemoryOrchestrator``
directly.  MCP agents instead call ``provider.search`` for basic mode and
``provider.search_vnext_bundle`` for advanced mode, so those are the paths
measured here.  The corpus and query set are intentionally shared with the
sealed benchmark to keep the evaluation contract aligned.

Output: JSON with per-path recall@5, MRR@10, tier retention and composite score.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List

# Keep the benchmark deterministic and offline.
os.environ["MEMENTO_EMBEDDING_BACKEND"] = "none"
os.environ.pop("OPENAI_API_KEY", None)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks.e2e_memory_accuracy import (  # noqa: E402
    DISTRACTORS,
    GOLD,
    K_MRR,
    K_RECALL,
    NOISE,
    QUERIES,
)
from memento.provider import NeuroGraphProvider  # noqa: E402

SearchFn = Callable[[NeuroGraphProvider, str, int], Coroutine[Any, Any, List[dict]]]


def _result_ids(results: Any) -> List[str]:
    if isinstance(results, dict):
        results = results.get("results", [])
    ids: List[str] = []
    for result in results or []:
        if isinstance(result, dict):
            ids.append(result.get("id") or result.get("memory_id") or "")
        else:
            ids.append(getattr(result, "id", "") or "")
    return [memory_id for memory_id in ids if memory_id]


def _metrics(
    name: str,
    path: str,
    results_by_query: List[List[dict]],
    gold_ids: Dict[str, str],
) -> Dict[str, Any]:
    recall_hits = 0
    reciprocal_ranks: List[float] = []
    tier_hits = 0
    limits_ok = True

    for (_, gold_key), results in zip(QUERIES, results_by_query):
        ids = _result_ids(results)
        if len(ids) > K_MRR:
            limits_ok = False
        gold_id = gold_ids[gold_key]
        if gold_id in ids[:K_RECALL]:
            recall_hits += 1
        reciprocal_rank = 0.0
        for rank, memory_id in enumerate(ids[:K_MRR], start=1):
            if memory_id == gold_id:
                reciprocal_rank = 1.0 / rank
                break
        reciprocal_ranks.append(reciprocal_rank)
        if gold_id in ids[:K_MRR]:
            tier_hits += 1

    n = len(QUERIES)
    recall_at_5 = recall_hits / n
    mrr_at_10 = sum(reciprocal_ranks) / n
    tier_retention = tier_hits / n
    score = 0.45 * recall_at_5 + 0.40 * mrr_at_10 + 0.15 * tier_retention

    return {
        "path": path,
        "score": round(score, 6),
        "components": {
            "recall_at_5": round(recall_at_5, 6),
            "mrr_at_10": round(mrr_at_10, 6),
            "tier_retention": round(tier_retention, 6),
        },
        "n_queries": n,
        "result_limits_ok": limits_ok,
    }


async def _basic(provider: NeuroGraphProvider, query: str, limit: int) -> List[dict]:
    return await provider.search(query, user_id="default", limit=limit)


async def _advanced(provider: NeuroGraphProvider, query: str, limit: int) -> List[dict]:
    bundle = await provider.search_vnext_bundle(query, user_id="default", limit=limit)
    if isinstance(bundle, dict):
        return bundle.get("results", [])
    return list(bundle or [])


async def evaluate_paths() -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as workspace:
        provider = NeuroGraphProvider(
            db_path=os.path.join(workspace, "mcp_paths.db"),
            workspace_root=workspace,
        )
        await provider.initialize()
        try:
            gold_ids: Dict[str, str] = {}
            for key, content, tier in GOLD:
                result = await provider.add(
                    content,
                    user_id="default",
                    metadata={"gold_key": key, "memory_tier": tier},
                )
                gold_ids[key] = result["id"]
            for content in DISTRACTORS:
                await provider.add(content, user_id="default")
            for content in NOISE:
                await provider.add(content, user_id="default")

            paths: Dict[str, Any] = {}
            for name, search_fn in (("basic", _basic), ("advanced", _advanced)):
                results_by_query = [
                    await search_fn(provider, query, K_MRR) for query, _ in QUERIES
                ]
                paths[name] = _metrics(
                    name,
                    "provider.search"
                    if name == "basic"
                    else "provider.search_vnext_bundle",
                    results_by_query,
                    gold_ids,
                )
        finally:
            await provider.close()

    return {
        "benchmark": "mcp_memory_accuracy",
        "n_queries": len(QUERIES),
        "paths": paths,
    }


def main() -> None:
    print(json.dumps(asyncio.run(evaluate_paths()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
