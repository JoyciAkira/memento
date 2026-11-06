#!/usr/bin/env python3
"""
VSA exact-search scale benchmark for Memento — latency at growing N.

SEALED FILE — DO NOT MODIFY (self-improve harness rule H-SEAL).
This benchmark characterizes how the EXACT VSA Hamming search scales with corpus
size, and asserts a self-query recall of 1.0 (sanity: exact search must always
rank a memory's own vector first). It exists as a guard-rail: a future change
that regresses search correctness or makes latency blow up will move this score.

Note: an approximate LSH prefilter was evaluated and rejected (these bundle()
hypervectors are near-orthogonal, recall collapsed <0.2), so search is exact and
O(N). This benchmark therefore tracks the exact path's latency envelope.

Runs fully offline and deterministically:
  - MEMENTO_EMBEDDING_BACKEND=none  (no network)
  - fixed synthetic corpus seeded by a fixed RNG
  - in-memory VSAIndex per N (no sqlite I/O)

Composite score (higher is better):
  score = self_query_recall              if median latency at the largest N is
                                           within LATENCY_BUDGET_S
        = self_query_recall * 0.5        otherwise (correct but slow)

Output: a single JSON object on stdout:
  {"score": <float>, "metric": "vsa_scale_exact", "direction": "higher_is_better",
   "components": {"self_query_recall": ..., "max_n_median_ms": ..., "latency_ok": bool},
   "per_n": {"1000": {...}, "5000": {...}, "20000": {...}}}
"""

from __future__ import annotations

import json
import os
import time
from statistics import median

os.environ["MEMENTO_EMBEDDING_BACKEND"] = "none"
os.environ.pop("OPENAI_API_KEY", None)

import numpy as np  # noqa: E402

from memento.memory.hdc import HDCEncoder  # noqa: E402
from memento.memory.vsa_index import VSAIndex  # noqa: E402

N_SIZES = [1000, 5000, 20000]
ITERATIONS = 25
TOP_K = 10
SEED = 1234
LATENCY_BUDGET_S = 0.30  # exact O(N) median latency budget at the largest N
VOCAB = [f"tok{i}" for i in range(200)]


def _seed_index(idx: VSAIndex, n: int, rng) -> None:
    for i in range(n):
        words = rng.choice(VOCAB, size=8, replace=False)
        text = f"mem{i} " + " ".join(words)
        ents = idx.extract_entities(text)
        idx._entity_cache[f"m{i}"] = ents
        for e in ents:
            idx.hdc.concept(e)
        idx._vector_cache[f"m{i}"] = int(idx.hdc.encode_text(text, ents))


def _p95(durations: list[float]) -> float:
    if not durations:
        return 0.0
    s = sorted(durations)
    return s[int(0.95 * (len(s) - 1))]


def _evaluate() -> dict:
    per_n: dict[str, dict] = {}
    self_hits = 0
    self_total = 0
    max_n_median = 0.0

    for n in N_SIZES:
        hdc = HDCEncoder()
        idx = VSAIndex(":memory:", hdc=hdc)
        _seed_index(idx, n, np.random.default_rng(SEED + n))

        # Warmup: force the numpy matrix + popcount LUT build.
        idx._batch_hv_similarity(idx._vector_cache["m0"])

        # Self-query recall: a memory's own vector must rank itself #1.
        recall_hits_n = 0
        targets = [f"m{j}" for j in range(0, n, max(1, n // 20))][:20]
        for t in targets:
            ranked = idx._batch_hv_similarity(idx._vector_cache[t])
            top = max(ranked, key=lambda x: x[1])[0]
            recall_hits_n += 1 if top == t else 0
        self_hits += recall_hits_n
        self_total += len(targets)

        # Latency.
        durations = []
        for it in range(ITERATIONS):
            q = idx._vector_cache[f"m{it % n}"]
            t0 = time.perf_counter()
            idx._batch_hv_similarity(q)
            durations.append(time.perf_counter() - t0)
        med = median(durations)
        if n == N_SIZES[-1]:
            max_n_median = med

        per_n[str(n)] = {
            "median_ms": round(med * 1000, 3),
            "p95_ms": round(_p95(durations) * 1000, 3),
            "max_ms": round(max(durations) * 1000, 3),
            "self_query_recall": round(recall_hits_n / len(targets), 6),
        }

    self_recall = self_hits / max(1, self_total)
    latency_ok = max_n_median <= LATENCY_BUDGET_S
    score = self_recall if latency_ok else self_recall * 0.5

    return {
        "score": round(score, 6),
        "metric": "vsa_scale_exact",
        "direction": "higher_is_better",
        "components": {
            "self_query_recall": round(self_recall, 6),
            "max_n_median_ms": round(max_n_median * 1000, 3),
            "latency_ok": latency_ok,
            "latency_budget_ms": LATENCY_BUDGET_S * 1000,
        },
        "per_n": per_n,
    }


def main() -> int:
    print(json.dumps(_evaluate()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
