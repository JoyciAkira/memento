from __future__ import annotations

from typing import Sequence


def recall_at_k(retrieved_ids: Sequence[str], expected_ids: Sequence[str], k: int) -> float:
    if not expected_ids:
        return 0.0
    top_k = set(retrieved_ids[:k])
    hits = sum(1 for eid in expected_ids if eid in top_k)
    return hits / len(expected_ids)


def hit_rate(retrieved_ids: Sequence[str], expected_ids: Sequence[str]) -> float:
    if not expected_ids:
        return 0.0
    return 1.0 if any(eid in retrieved_ids for eid in expected_ids) else 0.0


def mrr(retrieved_ids: Sequence[str], expected_ids: Sequence[str]) -> float:
    expected = set(expected_ids)
    for i, rid in enumerate(retrieved_ids, start=1):
        if rid in expected:
            return 1.0 / i
    return 0.0


def ndcg_at_k(retrieved_ids: Sequence[str], expected_ids: Sequence[str], k: int) -> float:
    import math

    if not expected_ids:
        return 0.0
    expected = set(expected_ids)
    dcg = 0.0
    for i, rid in enumerate(retrieved_ids[:k], start=1):
        if rid in expected:
            dcg += 1.0 / math.log2(i + 1)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(expected_ids), k) + 1))
    if ideal == 0.0:
        return 0.0
    return dcg / ideal
