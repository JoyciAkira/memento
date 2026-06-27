#!/usr/bin/env python3
"""
End-to-End Memory Accuracy Benchmark for Memento.

SEALED FILE — DO NOT MODIFY (self-improve harness rule H-SEAL).
This benchmark defines the evaluation contract. Improvements must come from
changes to the retrieval/memory pipeline (orchestrator, tiers, vsa_index,
retrieval lanes, relevance scoring), NOT from changing the test itself.

It drives the real MemoryOrchestrator multi-tier retrieval path against a
realistic corpus seeded with semantically-adjacent distractors and noise, then
computes a single composite accuracy score in [0, 1].

Runs fully offline and deterministically:
  - MEMENTO_EMBEDDING_BACKEND=none  (no network)
  - fixed corpus + fixed query set with known-relevant gold IDs
  - fresh migrated SQLite DB in a temp dir each run

Composite score (higher is better):
    score = 0.45 * recall@5  +  0.40 * MRR@10  +  0.15 * tier_retention

Output: a single JSON object on stdout:
    {"score": <float>, "metric": "composite_accuracy", "direction": "higher_is_better",
     "components": {"recall_at_5": ..., "mrr_at_10": ..., "tier_retention": ...},
     "n_queries": <int>}
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile

# Force deterministic offline mode BEFORE importing memento.
os.environ["MEMENTO_EMBEDDING_BACKEND"] = "none"
os.environ.pop("OPENAI_API_KEY", None)

from memento.migrations.runner import MigrationRunner  # noqa: E402
from memento.migrations.versions import get_all_migrations  # noqa: E402
from memento.memory.orchestrator import MemoryOrchestrator  # noqa: E402


# ---------------------------------------------------------------------------
# Corpus: gold facts (the answers we want retrieved) plus distractors that are
# lexically/semantically adjacent, so naive whole-string matching is not enough.
# Each gold entry: (gold_key, content, tier).
# ---------------------------------------------------------------------------
GOLD = [
    ("fastapi_async", "FastAPI is an asynchronous Python web framework built on Starlette and Pydantic", "semantic"),
    ("sqlite_fts5", "SQLite provides FTS5, a full-text search extension with BM25 ranking", "semantic"),
    ("python_gil", "CPython has a Global Interpreter Lock that serializes bytecode execution across threads", "semantic"),
    ("rust_ownership", "Rust enforces memory safety at compile time through its ownership and borrowing system", "semantic"),
    ("postgres_mvcc", "PostgreSQL uses MVCC so readers never block writers and writers never block readers", "semantic"),
    ("react_hooks", "React hooks let function components manage state and side effects without classes", "semantic"),
    ("docker_layers", "Docker images are composed of stacked read only layers cached by content hash", "semantic"),
    ("tcp_handshake", "TCP establishes a connection with a three way SYN SYN-ACK ACK handshake", "semantic"),
    ("git_rebase", "Git rebase rewrites commit history by replaying commits onto a new base", "episodic"),
    ("kafka_partition", "Kafka topics are split into partitions to allow parallel consumption and ordering per key", "semantic"),
    ("redis_single_thread", "Redis processes commands on a single thread which guarantees atomic command execution", "semantic"),
    ("jwt_stateless", "JWT tokens carry signed claims so the server authenticates requests without server side sessions", "semantic"),
    ("k8s_pod", "In Kubernetes a Pod is the smallest deployable unit and may contain one or more containers", "semantic"),
    ("http2_multiplex", "HTTP2 multiplexes many streams over a single TCP connection to avoid head of line blocking", "semantic"),
    ("grpc_protobuf", "gRPC uses Protocol Buffers as its interface definition language and wire format", "semantic"),
]

# Distractors share vocabulary with gold facts but are NOT the right answer.
DISTRACTORS = [
    "Flask is a synchronous Python micro web framework without built in async support",
    "MySQL also offers a full text search index but uses a different ranking than SQLite",
    "Jython runs Python on the JVM and does not have the same interpreter lock semantics",
    "Go uses a garbage collector rather than compile time ownership for memory management",
    "MongoDB uses document locking rather than multiversion concurrency control by default",
    "Vue composition api also lets components manage reactive state outside of classes",
    "A virtual machine image is a single monolithic disk file unlike layered container images",
    "UDP is connectionless and performs no handshake before sending datagrams",
    "Git merge combines branches by creating a new commit instead of rewriting history",
    "RabbitMQ routes messages through exchanges and queues rather than partitioned topics",
    "Memcached is multi threaded and does not guarantee single threaded command atomicity",
    "Session cookies store a server side session id rather than self contained signed claims",
    "A Docker container is a running instance whereas a Pod is a Kubernetes scheduling unit",
    "HTTP 1.1 keeps connections alive but still suffers head of line blocking per connection",
    "Apache Thrift is an alternative rpc framework that also supports multiple languages",
]

# Generic noise to grow the corpus and dilute the signal.
NOISE = [f"Routine log entry number {i} nothing notable happened during this session" for i in range(60)]

# Queries are graded by difficulty so the metric has a smooth gradient:
#   EASY   — a contiguous phrase lifted from the gold doc. A naive whole-string
#            substring match can already find these (baseline > 0).
#   MEDIUM — the gold doc's words, reordered / with gaps. Needs token-aware
#            matching; whole-string substring fails.
#   HARD   — pure paraphrase sharing only individual content words. Needs real
#            term-overlap / BM25-style ranking to surface the gold answer.
# Each query maps to its gold_key.
QUERIES = [
    # --- EASY: contiguous substring of the gold fact ---
    ("asynchronous Python web framework built on Starlette", "fastapi_async"),
    ("full-text search extension with BM25 ranking", "sqlite_fts5"),
    ("Global Interpreter Lock that serializes bytecode execution", "python_gil"),
    ("replaying commits onto a new base", "git_rebase"),
    ("Protocol Buffers as its interface definition language", "grpc_protobuf"),
    # --- MEDIUM: gold words, reordered or with gaps ---
    ("compile time memory safety ownership borrowing", "rust_ownership"),
    ("readers never block writers MVCC", "postgres_mvcc"),
    ("function components state side effects without classes", "react_hooks"),
    ("single thread atomic command execution store", "redis_single_thread"),
    ("smallest deployable unit one or more containers", "k8s_pod"),
    # --- HARD: paraphrase, only individual content words shared ---
    ("container images built from cached stacked layers", "docker_layers"),
    ("connection setup using a three way handshake of packets", "tcp_handshake"),
    ("message topics divided into parallel ordered partitions", "kafka_partition"),
    ("authenticate api requests without storing sessions on the server", "jwt_stateless"),
    ("protocol that multiplexes many streams over one tcp connection", "http2_multiplex"),
]

K_RECALL = 5
K_MRR = 10


def _seed(orch: MemoryOrchestrator) -> dict[str, str]:
    """Insert corpus, return gold_key -> memory_id map."""
    gold_ids: dict[str, str] = {}
    for key, content, tier in GOLD:
        gold_ids[key] = orch.add(content, metadata={"gold_key": key}, tier=tier)
    for content in DISTRACTORS:
        orch.add(content, tier="semantic")
    for content in NOISE:
        orch.add(content, tier="episodic")
    return gold_ids


def _result_ids(results) -> list[str]:
    ids = []
    for r in results:
        if isinstance(r, dict):
            ids.append(r.get("id") or r.get("memory_id"))
        else:
            ids.append(getattr(r, "id", None))
    return [i for i in ids if i]


def _evaluate() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "e2e_bench.db")

        runner = MigrationRunner(db_path)
        for version, name, fn in get_all_migrations():
            runner.register(version, name, fn)
        runner.run()

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        orch = MemoryOrchestrator(conn)

        gold_ids = _seed(orch)

        recall_hits = 0
        reciprocal_ranks: list[float] = []
        tier_hits = 0

        for query, gold_key in QUERIES:
            gold_id = gold_ids[gold_key]
            results = orch.search(query, tier="all", limit=K_MRR)
            ids = _result_ids(results)

            if gold_id in ids[:K_RECALL]:
                recall_hits += 1

            rr = 0.0
            for rank, mid in enumerate(ids[:K_MRR], start=1):
                if mid == gold_id:
                    rr = 1.0 / rank
                    break
            reciprocal_ranks.append(rr)

            if gold_id in ids[:K_MRR]:
                tier_hits += 1

        conn.close()

        n = len(QUERIES)
        recall_at_5 = recall_hits / n
        mrr_at_10 = sum(reciprocal_ranks) / n
        tier_retention = tier_hits / n

        score = 0.45 * recall_at_5 + 0.40 * mrr_at_10 + 0.15 * tier_retention

        return {
            "score": round(score, 6),
            "metric": "composite_accuracy",
            "direction": "higher_is_better",
            "components": {
                "recall_at_5": round(recall_at_5, 6),
                "mrr_at_10": round(mrr_at_10, 6),
                "tier_retention": round(tier_retention, 6),
            },
            "n_queries": n,
        }


def main() -> int:
    print(json.dumps(_evaluate()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
