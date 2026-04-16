from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Awaitable, Callable

from memento.eval.datasets import EvalCase, EvalSet
from memento.eval.metrics import hit_rate, mrr, ndcg_at_k, recall_at_k

SearchFn = Callable[[str], Awaitable[list[dict[str, Any]]]]


class EvalResult:
    __slots__ = ("case", "retrieved_ids", "metrics")

    def __init__(self, case: EvalCase, retrieved_ids: list[str], metrics: dict[str, float]):
        self.case = case
        self.retrieved_ids = retrieved_ids
        self.metrics = metrics


class EvalRun:
    __slots__ = ("id", "eval_set", "started_at", "ended_at", "results", "summary")

    def __init__(self, eval_set: EvalSet):
        self.id = str(uuid.uuid4())[:8]
        self.eval_set = eval_set
        self.started_at = datetime.now().isoformat()
        self.ended_at: str | None = None
        self.results: list[EvalResult] = []
        self.summary: dict[str, float] = {}

    async def execute(self, search_fn: SearchFn, k: int = 10) -> None:
        for case in self.eval_set.cases:
            raw = await search_fn(case.query)
            retrieved_ids = [r["id"] for r in raw]
            metrics = {
                "recall@k": recall_at_k(retrieved_ids, case.expected_ids, k),
                "hit_rate": hit_rate(retrieved_ids, case.expected_ids),
                "mrr": mrr(retrieved_ids, case.expected_ids),
                f"ndcg@{k}": ndcg_at_k(retrieved_ids, case.expected_ids, k),
            }
            self.results.append(EvalResult(case=case, retrieved_ids=retrieved_ids, metrics=metrics))
        self.ended_at = datetime.now().isoformat()
        self._compute_summary()

    def _compute_summary(self) -> None:
        if not self.results:
            return
        n = len(self.results)
        keys = self.results[0].metrics.keys()
        self.summary = {k: sum(r.metrics[k] for r in self.results) / n for k in keys}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "eval_set": self.eval_set.name,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "summary": self.summary,
            "results": [
                {
                    "query": r.case.query,
                    "expected_ids": r.case.expected_ids,
                    "retrieved_ids": r.retrieved_ids[:20],
                    "metrics": r.metrics,
                }
                for r in self.results
            ],
        }

    def save_report(self, dir_path: str) -> str:
        os.makedirs(dir_path, exist_ok=True)
        fname = f"eval_{self.eval_set.name}_{self.id}.json"
        path = os.path.join(dir_path, fname)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        return path
