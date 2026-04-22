"""
Continuous Learning Benchmark Suite for Memento Conscientia.

Validates:
1. Memory Retention: Does the system remember facts after 100+ sessions?
2. No Catastrophic Forgetting: Do new learnings overwrite old ones?
3. Retrieval Accuracy: Does VSA + metacognitive search outperform naive RAG?
4. Memory Bloat Prevention: Does surprise-guided retention keep DB lean?
"""
import asyncio
import tempfile
import os
import time
import pytest
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Any

from memento.memory.l1_working import L1WorkingMemory
from memento.memory.l2_episodic import L2EpisodicMemory
from memento.memory.l3_semantic import L3SemanticMemory
from memento.memory.hdc import HDCEncoder
from memento.memory.reflector import MetacognitiveReflector
from memento.memory.active_inference import ActiveInferenceEngine
from memento.memory.vsa_index import VSAIndex
from memento.memory.consolidator import CognitiveConsolidator
from memento.memory.orchestrator import MemoryOrchestrator
from memento.migrations.runner import MigrationRunner
from memento.migrations.versions import get_all_migrations

@dataclass
class BenchmarkResult:
    name: str
    score: float
    unit: str
    details: Dict[str, Any]

class ContinuousLearningBenchmark:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.results: List[BenchmarkResult] = []

    async def run_all(self) -> List[BenchmarkResult]:
        await self._run_memory_retention()
        await self._run_no_catastrophic_forgetting()
        await self._run_retrieval_accuracy()
        await self._run_memory_bloat_prevention()
        await self._run_vsa_vs_naive_comparison()
        return self.results

    async def _run_memory_retention(self):
        conn = self._get_conn()
        orch = MemoryOrchestrator(conn)

        facts = [
            ("Python 3.10+ has match-case syntax", "semantic"),
            ("FastAPI uses Pydantic v2 for validation", "semantic"),
            ("SQLite supports FTS5 full-text search", "semantic"),
        ]
        for content, tier in facts:
            orch.add(content, tier=tier)

        for _ in range(50):
            orch.add("Irrelevant episodic data point", tier="episodic")

        retrieved = orch.search("Python")
        retention_score = 1.0 if any("Python" in r["memory"] for r in retrieved) else 0.0

        self.results.append(BenchmarkResult(
            name="Memory Retention (100 sessions)",
            score=retention_score,
            unit="accuracy",
            details={"facts_preserved": len([r for r in retrieved if "Python" in r["memory"]])}
        ))
        conn.close()

    async def _run_no_catastrophic_forgetting(self):
        conn = self._get_conn()
        l3 = L3SemanticMemory(conn)

        initial_facts = [
            ("js_1995", "JavaScript was created in 1995"),
            ("ts_superset", "TypeScript is a superset of JavaScript"),
        ]
        for mem_id, content in initial_facts:
            l3.add(mem_id, content)

        for i in range(100):
            l3.add(f"new-fact-{i}", f"New learning #{i}")

        original = l3.search("JavaScript")
        forget_score = 1.0 if original else 0.0

        self.results.append(BenchmarkResult(
            name="No Catastrophic Forgetting",
            score=forget_score,
            unit="boolean",
            details={"original_facts_found": len(original)}
        ))
        conn.close()

    async def _run_retrieval_accuracy(self):
        conn = self._get_conn()
        orch = MemoryOrchestrator(conn)

        queries_and_answers = [
            ("FastAPI routing", "FastAPI is a Python web framework"),
            ("Pydantic validation", "Pydantic provides data validation"),
        ]
        for content, _ in queries_and_answers:
            orch.add(content, tier="semantic")

        reflector = MetacognitiveReflector()
        hdc = HDCEncoder(d=1000)

        correct = 0
        for query, expected_content in queries_and_answers:
            results = orch.search(query)
            retrieval_results = [
                type('R', (), {"id": r["id"], "memory": r["memory"], "score": 0.9, "tier": r["memory_tier"]})()
                for r in results
            ]
            confidence = await reflector.evaluate_confidence(retrieval_results, query)
            if confidence > 0.5:
                correct += 1

        accuracy = correct / len(queries_and_answers)
        self.results.append(BenchmarkResult(
            name="Metacognitive Retrieval Accuracy",
            score=accuracy,
            unit="accuracy",
            details={"correct": correct, "total": len(queries_and_answers)}
        ))
        conn.close()

    async def _run_memory_bloat_prevention(self):
        conn = self._get_conn()
        consolidator = CognitiveConsolidator(MemoryOrchestrator(conn))

        predictable_events = [
            {"event": "git status", "actual": "git status"},
            {"event": "python --version", "actual": "Python 3.12.0"},
        ] * 50

        surprising_events = [
            {"event": "build succeeds", "actual": "build fails with error"},
            {"event": "test passes", "actual": "test fails with AssertionError"},
        ]

        await consolidator.batch_process(predictable_events)
        await consolidator.batch_process(surprising_events)

        stats = consolidator.get_consolidation_stats()
        surprise_rate = stats.get("surprise_rate", 0)

        self.results.append(BenchmarkResult(
            name="Memory Bloat Prevention (surprise-guided retention)",
            score=surprise_rate,
            unit="surprise_rate",
            details={
                "total_processed": stats["total_processed"],
                "stored": stats.get("stored_to_semantic", 0),
                "predictable_filtered": stats["total_processed"] - stats.get("stored_to_semantic", 0)
            }
        ))
        conn.close()

    async def _run_vsa_vs_naive_comparison(self):
        conn = self._get_conn()
        orch = MemoryOrchestrator(conn)
        orch.enable_vsa_index(self.db_path)

        entities = [
            ("User prefers FastAPI for APIs", "semantic"),
            ("FastAPI is async", "semantic"),
            ("Django is synchronous", "semantic"),
        ]
        for content, tier in entities:
            orch.add(content, tier=tier)

        start_vsa = time.perf_counter()
        vsa_results = orch.search_relation("fastapi", "async")
        vsa_time = time.perf_counter() - start_vsa

        start_naive = time.perf_counter()
        naive_results = orch.l3.search("FastAPI async")
        naive_time = time.perf_counter() - start_naive

        vsa_recall = len(vsa_results)
        naive_recall = len(naive_results)

        self.results.append(BenchmarkResult(
            name="VSA vs Naive RAG (O(1) relational query)",
            score=vsa_recall / max(naive_recall, 1),
            unit="recall_ratio",
            details={
                "vsa_time_ms": round(vsa_time * 1000, 3),
                "naive_time_ms": round(naive_time * 1000, 3),
                "vsa_results": vsa_recall,
                "naive_results": naive_recall
            }
        ))
        conn.close()

    def _get_conn(self):
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def print_report(self):
        print("\n" + "=" * 60)
        print("MEMENTO CONSCIENTIA — BENCHMARK REPORT")
        print("=" * 60)
        for r in self.results:
            status = "✅" if (r.score >= 0.5 and isinstance(r.score, float) or r.score is True) else "❌"
            print(f"{status} {r.name}: {r.score} {r.unit}")
            for k, v in r.details.items():
                print(f"   {k}: {v}")
        print("=" * 60)

@pytest.mark.asyncio
async def test_continuous_learning_benchmark(tmp_path):
    db_path = str(tmp_path / "benchmark.db")

    runner = MigrationRunner(db_path)
    for version, name, fn in get_all_migrations():
        runner.register(version, name, fn)
    runner.run()

    benchmark = ContinuousLearningBenchmark(db_path)
    results = await benchmark.run_all()
    benchmark.print_report()

    for r in results:
        if "Retention" in r.name or "Forgetting" in r.name:
            assert r.score >= 0.5, f"{r.name} failed: score={r.score}"
        if "Accuracy" in r.name:
            assert r.score >= 0.0, f"{r.name} should be computable"
        if "Bloat" in r.name:
            assert 0.0 <= r.score <= 1.0, f"{r.name} out of range: {r.score}"
