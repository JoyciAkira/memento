# Autonomous Memory Engine vNext Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Memento vNext as a modular autonomous memory engine: retrieval pipeline with fusion+traces, graph consolidation + query surface, eval harness, and an agent loop orchestration layer.

**Architecture:** Add new `memento/retrieval`, `memento/graph`, `memento/eval`, `memento/agent` modules. Keep `NeuroGraphProvider` as the façade and preserve existing APIs. Expose vNext via new MCP tools (`memento_*_vnext`) and feature flags.

**Tech Stack:** Python, asyncio, aiosqlite/SQLite (existing), pytest (existing).

---

## File Structure (Locked In)

**Create (new):**
- `memento/retrieval/types.py`
- `memento/retrieval/pipeline.py`
- `memento/retrieval/lanes/__init__.py`
- `memento/retrieval/lanes/fts.py`
- `memento/retrieval/lanes/recency.py`
- `memento/retrieval/lanes/dense.py`
- `memento/graph/__init__.py`
- `memento/graph/extract.py`
- `memento/graph/consolidate.py`
- `memento/eval/__init__.py`
- `memento/eval/metrics.py`
- `memento/eval/runner.py`
- `memento/eval/report.py`
- `memento/agent/__init__.py`
- `memento/agent/orchestrator.py`
- `memento/tools/vnext_retrieval.py`
- `memento/tools/vnext_graph.py`
- `memento/tools/vnext_eval.py`
- `memento/tools/vnext_agent.py`
- `tests/test_vnext_retrieval.py`
- `tests/test_vnext_graph.py`
- `tests/test_vnext_eval.py`
- `tests/test_vnext_agent.py`

**Modify (existing):**
- `memento/provider.py`
- `memento/tools/__init__.py`

---

## Parallelization Notes (Subagent-Driven)

These tasks can be implemented in parallel without heavy merge conflicts:
- Retrieval module tasks (Tasks 1–3) can run in parallel with Graph (Task 4), Eval (Task 5), and Agent (Task 6).
- Provider/tool wiring tasks (Tasks 7–8) should be done after the module tasks land (or rebase frequently).

---

### Task 1: Retrieval Types + RRF Fusion (Foundation)

**Files:**
- Create: `memento/retrieval/types.py`
- Create: `memento/retrieval/pipeline.py`
- Test: `tests/test_vnext_retrieval.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_vnext_retrieval.py`:

```python
import pytest

from memento.retrieval.pipeline import rrf_fuse

def test_rrf_fuse_prefers_consensus():
    lane_a = [("a", 10.0), ("b", 9.0), ("c", 8.0)]
    lane_b = [("b", 1.0), ("a", 0.9), ("d", 0.8)]

    ranked = rrf_fuse(
        lanes={
            "fts": lane_a,
            "dense": lane_b,
        },
        k=60,
        lane_weights={"fts": 1.0, "dense": 1.0},
        limit=10,
    )

    assert ranked[0][0] in {"a", "b"}
    assert {ranked[0][0], ranked[1][0]} == {"a", "b"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vnext_retrieval.py::test_rrf_fuse_prefers_consensus -v`  
Expected: FAIL (ModuleNotFoundError: No module named 'memento.retrieval')

- [ ] **Step 3: Write minimal types + RRF implementation**

Create `memento/retrieval/types.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

Score = float

@dataclass(frozen=True)
class Candidate:
    memory_id: str
    score: float
    lane: str
    evidence: dict[str, Any]

class LaneTrace(TypedDict):
    lane: str
    considered: int
    returned: int
    top: list[dict[str, Any]]

class ContextBundle(TypedDict):
    query: str
    results: list[dict[str, Any]]
    facts: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    traces: list[LaneTrace]
```

Create `memento/retrieval/pipeline.py`:

```python
from __future__ import annotations

from typing import Iterable

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_vnext_retrieval.py::test_rrf_fuse_prefers_consensus -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add memento/retrieval/types.py memento/retrieval/pipeline.py tests/test_vnext_retrieval.py
git commit -m "feat: add vNext retrieval types and RRF fusion"
```

---

### Task 2: Retrieval Lanes (FTS + Recency + Dense)

**Files:**
- Create: `memento/retrieval/lanes/__init__.py`
- Create: `memento/retrieval/lanes/fts.py`
- Create: `memento/retrieval/lanes/recency.py`
- Create: `memento/retrieval/lanes/dense.py`
- Modify: `memento/retrieval/pipeline.py`
- Test: `tests/test_vnext_retrieval.py`

- [ ] **Step 1: Write the failing test for lane traces shape**

Append to `tests/test_vnext_retrieval.py`:

```python
import os
import tempfile
import pytest

@pytest.mark.asyncio
async def test_vnext_pipeline_returns_traces_and_results():
    from memento.provider import NeuroGraphProvider

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "mem.db")
        p = NeuroGraphProvider(db_path=db_path)

        await p.add("alpha memory", user_id="default")
        await p.add("beta memory", user_id="default")

        bundle = await p.search_vnext_bundle("alpha", user_id="default", limit=5, trace=True)
        assert bundle["query"] == "alpha"
        assert len(bundle["results"]) >= 1
        assert any(t["lane"] == "fts" for t in bundle["traces"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vnext_retrieval.py::test_vnext_pipeline_returns_traces_and_results -v`  
Expected: FAIL (AttributeError: 'NeuroGraphProvider' object has no attribute 'search_vnext_bundle')

- [ ] **Step 3: Implement lanes**

Create `memento/retrieval/lanes/__init__.py`:

```python
__all__ = ["fts", "recency", "dense"]
```

Create `memento/retrieval/lanes/fts.py`:

```python
from __future__ import annotations

import re
from typing import Any

import aiosqlite

def build_fts_query(query: str) -> str:
    terms = re.findall(r"[A-Za-z0-9_]{3,}", query or "")
    fts_query = " OR ".join([f"{t}*" for t in terms]) if terms else (query or "").strip()
    return fts_query or "*"

async def lane_fts(
    *,
    db: aiosqlite.Connection,
    user_id: str,
    query: str,
    filter_sql: str,
    filter_params: list[Any],
    limit: int,
) -> list[tuple[str, float]]:
    fts_query = build_fts_query(query)
    try:
        cur = await db.execute(
            f"SELECT id, bm25(memories) AS fts_score FROM memories WHERE user_id = ? AND memories MATCH ? {filter_sql} LIMIT ?",
            (user_id, fts_query, *filter_params, limit),
        )
        rows = await cur.fetchall()
        return [(r["id"], float(r["fts_score"])) for r in rows]
    except Exception:
        cur = await db.execute(
            f"SELECT id, 1000000 AS fts_score FROM memories WHERE user_id = ? AND text LIKE ? {filter_sql} LIMIT ?",
            (user_id, f"%{query}%", *filter_params, limit),
        )
        rows = await cur.fetchall()
        return [(r["id"], float(r["fts_score"])) for r in rows]
```

Create `memento/retrieval/lanes/recency.py`:

```python
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
        f"SELECT id, created_at FROM memories WHERE user_id = ? {filter_sql} ORDER BY created_at DESC LIMIT ?",
        (user_id, *filter_params, limit),
    )
    rows = await cur.fetchall()
    return [(r["id"], float(limit - i)) for i, r in enumerate(rows)]
```

Create `memento/retrieval/lanes/dense.py`:

```python
from __future__ import annotations

import json
import math
from typing import Any, Awaitable, Callable

import aiosqlite

EmbedFn = Callable[[str], Awaitable[list[float]]]

def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    n1 = math.sqrt(sum(a * a for a in vec1))
    n2 = math.sqrt(sum(b * b for b in vec2))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return dot / (n1 * n2)

async def lane_dense(
    *,
    db: aiosqlite.Connection,
    user_id: str,
    query: str,
    candidate_ids: list[str],
    embed_fn: EmbedFn,
) -> list[tuple[str, float]]:
    query_vec = await embed_fn(query)
    if not candidate_ids:
        return []
    placeholders = ",".join(["?"] * len(candidate_ids))
    cur = await db.execute(
        f"SELECT m.id, e.embedding FROM memories m LEFT JOIN memory_embeddings e ON m.id = e.id WHERE m.user_id = ? AND m.id IN ({placeholders})",
        (user_id, *candidate_ids),
    )
    rows = await cur.fetchall()
    scored: list[tuple[str, float]] = []
    for r in rows:
        emb_str = r["embedding"]
        if not emb_str:
            scored.append((r["id"], 0.0))
            continue
        try:
            vec = json.loads(emb_str)
        except Exception:
            scored.append((r["id"], 0.0))
            continue
        scored.append((r["id"], float(cosine_similarity(query_vec, vec))))
    return sorted(scored, key=lambda x: x[1], reverse=True)
```

- [ ] **Step 4: Wire lanes into pipeline**

Update `memento/retrieval/pipeline.py` to add:

```python
from typing import Any, Awaitable, Callable

import aiosqlite

from memento.retrieval.lanes.fts import lane_fts
from memento.retrieval.lanes.recency import lane_recency
from memento.retrieval.lanes.dense import lane_dense
from memento.retrieval.types import ContextBundle, LaneTrace

EmbedFn = Callable[[str], Awaitable[list[float]]]

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
                f"SELECT id, text, created_at, metadata FROM memories WHERE user_id = ? AND id IN ({placeholders})",
                (user_id, *ids),
            )
            rows = await cur.fetchall()
            row_map = {r["id"]: r for r in rows}
            for doc_id, score in fused:
                r = row_map.get(doc_id)
                if not r:
                    continue
                results.append(
                    {
                        "id": r["id"],
                        "memory": r["text"],
                        "created_at": r["created_at"],
                        "score": score,
                    }
                )

        if trace:
            traces.extend(
                [
                    {"lane": "fts", "considered": len(fts_ranked), "returned": min(10, len(fts_ranked)), "top": [{"id": i, "score": s} for i, s in fts_ranked[:10]]},
                    {"lane": "dense", "considered": len(dense_ranked), "returned": min(10, len(dense_ranked)), "top": [{"id": i, "score": s} for i, s in dense_ranked[:10]]},
                    {"lane": "recency", "considered": len(recent_ranked), "returned": min(10, len(recent_ranked)), "top": [{"id": i, "score": s} for i, s in recent_ranked[:10]]},
                ]
            )

    return {
        "query": query,
        "results": results,
        "facts": [],
        "entities": [],
        "traces": traces,
    }
```

- [ ] **Step 5: Implement provider façade for vNext bundle**

Modify `memento/provider.py` (inside `class NeuroGraphProvider`) to add:

```python
    async def search_vnext_bundle(
        self,
        query: str,
        user_id: str = "default",
        limit: int = 50,
        filters: dict | None = None,
        trace: bool = False,
    ):
        from memento.retrieval.pipeline import retrieve_bundle

        if not self._initialized:
            await self.initialize()

        return await retrieve_bundle(
            db_path=self.db_path,
            query=query,
            user_id=user_id,
            limit=limit,
            filters=filters,
            embed_fn=self._get_embedding,
            trace=trace,
        )
```

- [ ] **Step 6: Run tests to verify it passes**

Run: `uv run pytest tests/test_vnext_retrieval.py::test_vnext_pipeline_returns_traces_and_results -v`  
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add memento/retrieval/lanes memento/retrieval/pipeline.py memento/provider.py tests/test_vnext_retrieval.py
git commit -m "feat: implement vNext retrieval lanes and bundle pipeline"
```

---

### Task 3: Retrieval Explainability Tooling (MCP)

**Files:**
- Create: `memento/tools/vnext_retrieval.py`
- Modify: `memento/tools/__init__.py`
- Test: `tests/test_vnext_retrieval.py`

- [ ] **Step 1: Write failing test for tool output**

Append to `tests/test_vnext_retrieval.py`:

```python
import json
import pytest

@pytest.mark.asyncio
async def test_memento_search_vnext_tool_returns_json_bundle(tmp_path):
    from memento.mcp_server import call_tool

    res_add = await call_tool(
        "memento_add_memory",
        {"workspace_root": str(tmp_path), "text": "hello world", "metadata": {}},
    )
    assert res_add

    res = await call_tool(
        "memento_search_vnext",
        {"workspace_root": str(tmp_path), "query": "hello", "trace": True},
    )
    payload = json.loads(res[0].text)
    assert payload["query"] == "hello"
    assert "results" in payload
    assert "traces" in payload
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vnext_retrieval.py::test_memento_search_vnext_tool_returns_json_bundle -v`  
Expected: FAIL (Unknown tool: memento_search_vnext)

- [ ] **Step 3: Implement new tools**

Create `memento/tools/vnext_retrieval.py`:

```python
import json
import logging

from mcp.types import Tool, TextContent

from memento.registry import registry

logger = logging.getLogger("memento-mcp")

@registry.register(
    Tool(
        name="memento_search_vnext",
        description="Search memories using the vNext retrieval pipeline and return a structured bundle.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
                "filters": {"type": "object", "additionalProperties": True},
                "trace": {"type": "boolean", "default": False},
            },
            "required": ["query"],
        },
    )
)
async def memento_search_vnext(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot search memory. Current access state is: {access_manager.state}")

    query = arguments.get("query")
    limit = int(arguments.get("limit") or 50)
    filters = arguments.get("filters")
    trace = bool(arguments.get("trace") or False)
    bundle = await ctx.provider.search_vnext_bundle(query, user_id="default", limit=limit, filters=filters, trace=trace)
    return [TextContent(type="text", text=json.dumps(bundle, indent=2, ensure_ascii=False))]

@registry.register(
    Tool(
        name="memento_explain_retrieval",
        description="Explain vNext retrieval by returning lane traces only.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "filters": {"type": "object", "additionalProperties": True},
            },
            "required": ["query"],
        },
    )
)
async def memento_explain_retrieval(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot search memory. Current access state is: {access_manager.state}")

    query = arguments.get("query")
    filters = arguments.get("filters")
    bundle = await ctx.provider.search_vnext_bundle(query, user_id="default", limit=1, filters=filters, trace=True)
    return [TextContent(type="text", text=json.dumps(bundle["traces"], indent=2, ensure_ascii=False))]
```

- [ ] **Step 4: Register tool module**

Modify `memento/tools/__init__.py`:

```python
from . import cognitive, coercion, core, memory, vnext_retrieval

__all__ = ["cognitive", "coercion", "core", "memory", "vnext_retrieval"]
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_vnext_retrieval.py::test_memento_search_vnext_tool_returns_json_bundle -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add memento/tools/__init__.py memento/tools/vnext_retrieval.py tests/test_vnext_retrieval.py
git commit -m "feat: add vNext retrieval MCP tools"
```

---

### Task 4: Graph Consolidation (Heuristic Extraction + KG Write)

**Files:**
- Create: `memento/graph/extract.py`
- Create: `memento/graph/consolidate.py`
- Create: `memento/tools/vnext_graph.py`
- Modify: `memento/tools/__init__.py`
- Test: `tests/test_vnext_graph.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_vnext_graph.py`:

```python
import json
import pytest

@pytest.mark.asyncio
async def test_graph_consolidate_adds_triples(tmp_path):
    from memento.mcp_server import call_tool

    await call_tool(
        "memento_add_memory",
        {"workspace_root": str(tmp_path), "text": "Touch file memento/provider.py and run uv run pytest", "metadata": {}},
    )

    res = await call_tool(
        "memento_consolidate",
        {"workspace_root": str(tmp_path), "limit": 50},
    )
    payload = json.loads(res[0].text)
    assert payload["added_triples"] > 0

    res_q = await call_tool(
        "memento_graph_query",
        {"workspace_root": str(tmp_path), "query": "memento/provider.py"},
    )
    triples = json.loads(res_q[0].text)
    assert triples
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vnext_graph.py -v`  
Expected: FAIL (Unknown tool: memento_consolidate)

- [ ] **Step 3: Implement entity extraction**

Create `memento/graph/extract.py`:

```python
from __future__ import annotations

import re

PATH_RE = re.compile(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,6}")
CMD_RE = re.compile(r"\b(uv run pytest|pytest|ruff check|uv sync)\b")

def extract_entities(text: str) -> dict[str, list[str]]:
    paths = sorted(set(PATH_RE.findall(text or "")))
    commands = sorted(set(CMD_RE.findall(text or "")))
    return {"paths": paths, "commands": commands}
```

- [ ] **Step 4: Implement consolidation**

Create `memento/graph/consolidate.py`:

```python
from __future__ import annotations

import json
from typing import Any

import aiosqlite

from memento.graph.extract import extract_entities

async def consolidate_from_memories(
    *,
    db_path: str,
    kg,
    user_id: str,
    limit: int,
) -> dict[str, Any]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, text FROM memories WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, int(limit)),
        )
        rows = await cur.fetchall()

    added = 0
    for r in rows:
        entities = extract_entities(r["text"])
        for p in entities["paths"]:
            kg.add_triple(subject=p, predicate="mentioned_in", obj=r["id"], source_file=r["id"])
            added += 1
        for c in entities["commands"]:
            kg.add_triple(subject=c, predicate="mentioned_in", obj=r["id"], source_file=r["id"])
            added += 1

    return {"scanned": len(rows), "added_triples": added}
```

- [ ] **Step 5: Implement MCP tools**

Create `memento/tools/vnext_graph.py`:

```python
import json

from mcp.types import Tool, TextContent

from memento.registry import registry
from memento.graph.consolidate import consolidate_from_memories

@registry.register(
    Tool(
        name="memento_consolidate",
        description="Heuristic consolidation: extract entities from recent memories and add them to the local knowledge graph with provenance.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 200},
            },
        },
    )
)
async def memento_consolidate(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_write():
        raise PermissionError(f"Cannot consolidate. Current access state is: {access_manager.state}")

    limit = int(arguments.get("limit") or 200)
    report = await consolidate_from_memories(
        db_path=ctx.provider.db_path,
        kg=ctx.provider.kg.kg,
        user_id="default",
        limit=limit,
    )
    return [TextContent(type="text", text=json.dumps(report, indent=2, ensure_ascii=False))]

@registry.register(
    Tool(
        name="memento_graph_query",
        description="Query the local knowledge graph (entity-first).",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "direction": {"type": "string", "default": "both"},
            },
            "required": ["query"],
        },
    )
)
async def memento_graph_query(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot read graph. Current access state is: {access_manager.state}")

    q = arguments.get("query")
    direction = arguments.get("direction") or "both"
    triples = ctx.provider.kg.kg.query_entity(q, direction=direction)
    return [TextContent(type="text", text=json.dumps(triples, indent=2, ensure_ascii=False))]
```

- [ ] **Step 6: Register tool module**

Modify `memento/tools/__init__.py`:

```python
from . import cognitive, coercion, core, memory, vnext_graph, vnext_retrieval

__all__ = ["cognitive", "coercion", "core", "memory", "vnext_graph", "vnext_retrieval"]
```

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_vnext_graph.py -v`  
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add memento/graph memento/tools/vnext_graph.py memento/tools/__init__.py tests/test_vnext_graph.py
git commit -m "feat: add graph consolidation and query tools"
```

---

### Task 5: Eval Harness (Recall@K + MRR) + MCP Tools

**Files:**
- Create: `memento/eval/metrics.py`
- Create: `memento/eval/runner.py`
- Create: `memento/eval/report.py`
- Create: `memento/tools/vnext_eval.py`
- Modify: `memento/tools/__init__.py`
- Test: `tests/test_vnext_eval.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_vnext_eval.py`:

```python
import json
import pytest

@pytest.mark.asyncio
async def test_eval_run_produces_metrics(tmp_path):
    from memento.mcp_server import call_tool

    await call_tool("memento_add_memory", {"workspace_root": str(tmp_path), "text": "delta one", "metadata": {}})
    await call_tool("memento_add_memory", {"workspace_root": str(tmp_path), "text": "delta two", "metadata": {}})

    eval_set = {
        "name": "smoke",
        "k": 5,
        "cases": [
            {"query": "delta", "expected_text_contains": ["delta one", "delta two"]}
        ],
    }

    res = await call_tool(
        "memento_eval_run",
        {"workspace_root": str(tmp_path), "eval_set": eval_set},
    )
    out = json.loads(res[0].text)
    assert out["summary"]["case_count"] == 1
    assert out["summary"]["hit_rate_at_k"] == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vnext_eval.py -v`  
Expected: FAIL (Unknown tool: memento_eval_run)

- [ ] **Step 3: Implement metrics**

Create `memento/eval/metrics.py`:

```python
from __future__ import annotations

def hit_rate_at_k(retrieved: list[str], expected_any: list[str], k: int) -> float:
    top = retrieved[: int(k)]
    return 1.0 if any(e in top for e in expected_any) else 0.0

def mrr(retrieved: list[str], expected_any: list[str], k: int) -> float:
    top = retrieved[: int(k)]
    for idx, item in enumerate(top, start=1):
        if item in expected_any:
            return 1.0 / float(idx)
    return 0.0
```

- [ ] **Step 4: Implement runner**

Create `memento/eval/runner.py`:

```python
from __future__ import annotations

from typing import Any

from memento.eval.metrics import hit_rate_at_k, mrr

async def run_eval_set(*, provider, eval_set: dict[str, Any]) -> dict[str, Any]:
    k = int(eval_set.get("k") or 10)
    cases = eval_set.get("cases") or []

    case_results: list[dict[str, Any]] = []
    hits: list[float] = []
    mrrs: list[float] = []

    for c in cases:
        query = c.get("query") or ""
        expected_text = c.get("expected_text_contains") or []
        bundle = await provider.search_vnext_bundle(query, user_id="default", limit=k, trace=False)
        retrieved_texts = [r["memory"] for r in bundle["results"]]
        hr = hit_rate_at_k(retrieved_texts, expected_text, k)
        rr = mrr(retrieved_texts, expected_text, k)
        hits.append(hr)
        mrrs.append(rr)
        case_results.append(
            {
                "query": query,
                "k": k,
                "expected_text_contains": expected_text,
                "retrieved": retrieved_texts,
                "hit_rate_at_k": hr,
                "mrr": rr,
            }
        )

    summary = {
        "case_count": len(cases),
        "hit_rate_at_k": (sum(hits) / len(hits)) if hits else 0.0,
        "mrr": (sum(mrrs) / len(mrrs)) if mrrs else 0.0,
    }
    return {"summary": summary, "cases": case_results}
```

- [ ] **Step 5: Implement report**

Create `memento/eval/report.py`:

```python
from __future__ import annotations

import json
from typing import Any

def render_report(run: dict[str, Any]) -> str:
    return json.dumps(run, indent=2, ensure_ascii=False)
```

- [ ] **Step 6: Implement MCP tools**

Create `memento/tools/vnext_eval.py`:

```python
import json

from mcp.types import Tool, TextContent

from memento.registry import registry
from memento.eval.runner import run_eval_set
from memento.eval.report import render_report

@registry.register(
    Tool(
        name="memento_eval_run",
        description="Run a retrieval regression eval set against vNext retrieval and return metrics + artifacts.",
        inputSchema={
            "type": "object",
            "properties": {
                "eval_set": {"type": "object", "additionalProperties": True},
            },
            "required": ["eval_set"],
        },
    )
)
async def memento_eval_run(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot run eval. Current access state is: {access_manager.state}")

    eval_set = arguments.get("eval_set")
    run = await run_eval_set(provider=ctx.provider, eval_set=eval_set)
    return [TextContent(type="text", text=json.dumps(run, indent=2, ensure_ascii=False))]

@registry.register(
    Tool(
        name="memento_eval_report",
        description="Render a human-readable report for an eval run object (as returned by memento_eval_run).",
        inputSchema={
            "type": "object",
            "properties": {
                "eval_run": {"type": "object", "additionalProperties": True},
            },
            "required": ["eval_run"],
        },
    )
)
async def memento_eval_report(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot read eval report. Current access state is: {access_manager.state}")

    report = render_report(arguments.get("eval_run"))
    return [TextContent(type="text", text=report)]
```

- [ ] **Step 7: Register tool module**

Modify `memento/tools/__init__.py`:

```python
from . import cognitive, coercion, core, memory, vnext_eval, vnext_graph, vnext_retrieval

__all__ = ["cognitive", "coercion", "core", "memory", "vnext_eval", "vnext_graph", "vnext_retrieval"]
```

- [ ] **Step 8: Run tests**

Run: `uv run pytest tests/test_vnext_eval.py -v`  
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add memento/eval memento/tools/vnext_eval.py memento/tools/__init__.py tests/test_vnext_eval.py
git commit -m "feat: add eval harness and MCP tools for vNext retrieval"
```

---

### Task 6: Agent Orchestrator (On-Demand Tasks) + MCP Tools

**Files:**
- Create: `memento/agent/orchestrator.py`
- Create: `memento/tools/vnext_agent.py`
- Modify: `memento/tools/__init__.py`
- Test: `tests/test_vnext_agent.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_vnext_agent.py`:

```python
import json
import pytest

@pytest.mark.asyncio
async def test_agent_run_consolidate_and_eval(tmp_path):
    from memento.mcp_server import call_tool

    await call_tool("memento_add_memory", {"workspace_root": str(tmp_path), "text": "omega memory", "metadata": {}})

    res = await call_tool(
        "memento_agent_run",
        {
            "workspace_root": str(tmp_path),
            "task": "consolidate",
            "options": {"limit": 50},
        },
    )
    out = json.loads(res[0].text)
    assert out["task"] == "consolidate"

    res_status = await call_tool("memento_agent_status", {"workspace_root": str(tmp_path)})
    status = json.loads(res_status[0].text)
    assert "last_runs" in status
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vnext_agent.py -v`  
Expected: FAIL (Unknown tool: memento_agent_run)

- [ ] **Step 3: Implement orchestrator**

Create `memento/agent/orchestrator.py`:

```python
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

TaskFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

@dataclass
class AgentOrchestrator:
    tasks: dict[str, TaskFn]
    last_runs: list[dict[str, Any]] = field(default_factory=list)

    async def run(self, task: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        if task not in self.tasks:
            raise ValueError(f"Unknown agent task: {task}")
        opts = options or {}
        started = time.time()
        result = await self.tasks[task](opts)
        record = {"task": task, "started_at": started, "result": result}
        self.last_runs.append(record)
        self.last_runs = self.last_runs[-50:]
        return {"task": task, "result": result}
```

- [ ] **Step 4: Implement MCP tools**

Create `memento/tools/vnext_agent.py`:

```python
import json

from mcp.types import Tool, TextContent

from memento.registry import registry
from memento.agent.orchestrator import AgentOrchestrator
from memento.graph.consolidate import consolidate_from_memories
from memento.eval.runner import run_eval_set

def _get_orchestrator(ctx) -> AgentOrchestrator:
    if getattr(ctx, "agent_orchestrator", None) is None:
        async def _consolidate(opts: dict) -> dict:
            limit = int(opts.get("limit") or 200)
            return await consolidate_from_memories(
                db_path=ctx.provider.db_path,
                kg=ctx.provider.kg.kg,
                user_id="default",
                limit=limit,
            )

        async def _eval(opts: dict) -> dict:
            eval_set = opts.get("eval_set") or {"name": "empty", "k": 10, "cases": []}
            return await run_eval_set(provider=ctx.provider, eval_set=eval_set)

        ctx.agent_orchestrator = AgentOrchestrator(tasks={"consolidate": _consolidate, "eval": _eval})
    return ctx.agent_orchestrator

@registry.register(
    Tool(
        name="memento_agent_run",
        description="Run a single agent maintenance task (safe on-demand).",
        inputSchema={
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "One of: consolidate, eval"},
                "options": {"type": "object", "additionalProperties": True},
            },
            "required": ["task"],
        },
    )
)
async def memento_agent_run(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_write():
        raise PermissionError(f"Cannot run agent tasks. Current access state is: {access_manager.state}")
    orch = _get_orchestrator(ctx)
    out = await orch.run(arguments.get("task"), arguments.get("options"))
    return [TextContent(type="text", text=json.dumps(out, indent=2, ensure_ascii=False))]

@registry.register(
    Tool(
        name="memento_agent_status",
        description="Return agent loop status for the current workspace (last runs, available tasks).",
        inputSchema={"type": "object", "properties": {}},
    )
)
async def memento_agent_status(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot read agent status. Current access state is: {access_manager.state}")
    orch = _get_orchestrator(ctx)
    payload = {"tasks": sorted(list(orch.tasks.keys())), "last_runs": orch.last_runs}
    return [TextContent(type="text", text=json.dumps(payload, indent=2, ensure_ascii=False))]
```

- [ ] **Step 5: Register tool module**

Modify `memento/tools/__init__.py`:

```python
from . import cognitive, coercion, core, memory, vnext_agent, vnext_eval, vnext_graph, vnext_retrieval

__all__ = ["cognitive", "coercion", "core", "memory", "vnext_agent", "vnext_eval", "vnext_graph", "vnext_retrieval"]
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_vnext_agent.py -v`  
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add memento/agent memento/tools/vnext_agent.py memento/tools/__init__.py tests/test_vnext_agent.py
git commit -m "feat: add on-demand agent orchestrator and tools"
```

---

### Task 7: Full Test Run + Ruff

**Files:**
- Modify: (only if failures)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -q`  
Expected: PASS

- [ ] **Step 2: Run ruff**

Run: `uv run ruff check .`  
Expected: PASS (or fix and re-run)

- [ ] **Step 3: Commit (if any fixups)**

```bash
git add -A
git commit -m "chore: stabilize vNext modules (tests/ruff)"
```

