# Memento Tools + Offline Mode + Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Memento easier to adopt and debug by (1) adding a deterministic smoke test for all MCP tools, (2) adding an offline-first mode that avoids external model calls by default, and (3) adding retrieval tracing + an explain tool.

**Architecture:** Keep the existing MCP surface and provider classes, but introduce: a tool smoke-test harness in `tests/`, an embedding backend selector in `NeuroGraphProvider`, and an on-disk trace format for retrieval runs that can be surfaced via a new MCP tool.

**Tech Stack:** Python, asyncio, SQLite/FTS5, pytest, ruff.

---

## Scope Notes

- This plan intentionally does **not** add new third-party embedding libraries (fastembed/sentence-transformers). That will be a separate plan once offline-mode is stable.
- “Offline mode” here means: no network calls are required for basic add/search/status/tools. Optional LLM-backed features degrade gracefully.

---

## Task 1: Commit Current vNext Retrieval/Eval Scaffolding (Repo Hygiene)

**Files:**
- Add: `docs/superpowers/specs/2026-04-16-autonomous-memory-engine-vnext-design.md`
- Add: `docs/superpowers/plans/2026-04-16-autonomous-memory-engine-vnext-plan.md`
- Add: `memento/retrieval/**`
- Add: `memento/eval/**`
- Add: `tests/test_vnext_retrieval.py`
- Modify: `memento/provider.py`

- [ ] **Step 1: Confirm tests + lint are green**

Run:
```bash
uv run pytest -q
uv run ruff check .
```
Expected: PASS

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-04-16-autonomous-memory-engine-vnext-design.md
git add docs/superpowers/plans/2026-04-16-autonomous-memory-engine-vnext-plan.md
git add memento/retrieval memento/eval tests/test_vnext_retrieval.py memento/provider.py
git commit -m "feat: add vNext retrieval scaffolding and eval utilities"
```

---

## Task 2: Deterministic Smoke Test for All MCP Tools

**Goal:** Ensure every registered MCP tool can be invoked in a clean workspace without crashing (exceptions escaping), so regressions are caught in CI.

**Files:**
- Create: `tests/test_tools_smoke.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_tools_smoke.py`:

```python
import asyncio
import os
import sqlite3
import subprocess
import tempfile
from datetime import datetime

import pytest

from memento.mcp_server import call_tool, list_tools


def _init_source_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS memories USING fts5(id UNINDEXED, user_id UNINDEXED, text, created_at UNINDEXED, metadata UNINDEXED);"
    )
    conn.execute(
        "INSERT INTO memories (id, user_id, text, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
        ("m1", "default", "", datetime.now().isoformat(), "{}"),
    )
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_all_tools_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")

    ws = tmp_path
    subprocess.run(["git", "init"], cwd=str(ws), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    ws2 = tmp_path / "ws2"
    ws2.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(ws2), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    source_db = ws / "source.db"
    _init_source_db(str(source_db))

    conn = sqlite3.connect(str(source_db))
    conn.execute("UPDATE memories SET text=? WHERE id='m1'", (f"note about {ws.name} and migration",))
    conn.commit()
    conn.close()

    tools = await list_tools()
    tool_names = [t.name for t in tools]

    payloads = {
        "memento_status": {"workspace_root": str(ws)},
        "memento_toggle_access": {"workspace_root": str(ws), "state": "read-only"},
        "memento_toggle_superpowers": {"workspace_root": str(ws), "warnings": True, "tasks": True},
        "memento_configure_enforcement": {"workspace_root": str(ws), "level1": False, "level2": False, "level3": False},
        "memento_add_memory": {"workspace_root": str(ws), "text": "hello memory", "metadata": {}},
        "memento_search_memory": {"workspace_root": str(ws), "query": "hello"},
        "memento_get_warnings": {"workspace_root": str(ws), "context": "Using sqlite and asyncio"},
        "memento_generate_tasks": {"workspace_root": str(ws)},
        "memento_toggle_dependency_tracker": {"workspace_root": str(ws), "enabled": True},
        "memento_audit_dependencies": {"workspace_root": str(ws)},
        "memento_toggle_active_coercion": {"workspace_root": str(ws), "enabled": True},
        "memento_list_active_coercion_presets": {"workspace_root": str(ws)},
        "memento_apply_active_coercion_preset": {"workspace_root": str(ws), "preset": "python-dev-basics"},
        "memento_list_active_coercion_rules": {"workspace_root": str(ws)},
        "memento_add_active_coercion_rule": {
            "workspace_root": str(ws),
            "id": "no_print",
            "path_globs": ["**/*.py"],
            "kind": "regex",
            "regex": "\\bprint\\(",
            "message": "no print",
        },
        "memento_remove_active_coercion_rule": {"workspace_root": str(ws), "rule_id": "no_print"},
        "memento_install_git_hooks": {"workspace_root": str(ws)},
        "memento_toggle_precognition": {"workspace_root": str(ws), "enabled": False},
        "memento_check_goal_alignment": {"workspace_root": str(ws), "content": "test"},
        "memento_synthesize_dreams": {"workspace_root": str(ws), "context": "test"},
        "memento_migrate_workspace_memories": {
            "workspace_root": str(ws),
            "source_db_path": str(source_db),
            "workspace_roots": [str(ws), str(ws2)],
        },
        "memento": {"workspace_root": str(ws), "query": "list"},
    }

    await call_tool("memento_toggle_access", {"workspace_root": str(ws), "state": "read-write"})

    failures: list[tuple[str, str]] = []
    for name in tool_names:
        args = payloads.get(name, {"workspace_root": str(ws)})
        if name == "memento_toggle_access":
            try:
                await call_tool(name, args)
            except Exception as e:
                failures.append((name, str(e)))
            await call_tool("memento_toggle_access", {"workspace_root": str(ws), "state": "read-write"})
            continue

        try:
            await call_tool(name, args)
        except Exception as e:
            failures.append((name, str(e)))

    assert failures == []
```

- [ ] **Step 2: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_tools_smoke.py -v
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_tools_smoke.py
git commit -m "test: add smoke test for all MCP tools"
```

---

## Task 3: Offline-First Embedding Backend (No Network by Default)

**Goal:** Make basic usage work without any API keys or external calls. When no embedding backend is configured, Memento should:
- Still persist and return memories via FTS + recency.
- Never attempt embedding network calls.

**Files:**
- Modify: `memento/provider.py`
- Test: `tests/test_neuro_provider.py`
- Test: `tests/test_provider.py`

- [ ] **Step 1: Write failing test (no API key should not do network)**

Append to `tests/test_neuro_provider.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_neuro_provider_works_without_openai_api_key(tmp_path, monkeypatch):
    from memento.provider import NeuroGraphProvider

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    p = NeuroGraphProvider(db_path=str(tmp_path / "mem.db"))
    await p.add("offline memory", user_id="default")
    res = await p.search("offline", user_id="default")
    assert res
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_neuro_provider.py::test_neuro_provider_works_without_openai_api_key -v
```
Expected: FAIL (current provider still instantiates OpenAI client and/or calls embeddings)

- [ ] **Step 3: Implement backend selector**

In `memento/provider.py`:
1) Add an env selector in `NeuroGraphProvider.__init__`:
   - `MEMENTO_EMBEDDING_BACKEND=none|openai` (default: `none` when `OPENAI_API_KEY` missing; else `openai`)
2) When backend is `none`:
   - set `self.llm_client = None`
   - `_get_embedding()` returns `[]` immediately with no HTTP calls
3) Keep existing behavior for `openai`.

Minimal code to add inside `NeuroGraphProvider.__init__`:

```python
        requested_backend = os.environ.get("MEMENTO_EMBEDDING_BACKEND", "").strip().lower()
        has_openai_key = bool(os.environ.get("OPENAI_API_KEY", "").strip())
        if requested_backend:
            self.embedding_backend = requested_backend
        else:
            self.embedding_backend = "openai" if has_openai_key else "none"

        self.llm_client = None
        if self.embedding_backend == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "sk-dummy")
            base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
            self.embed_model = os.environ.get("MEM0_EMBEDDING_MODEL", "text-embedding-3-small")
            self.llm_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        else:
            self.embed_model = os.environ.get("MEM0_EMBEDDING_MODEL", "none")
```

And update `_get_embedding`:

```python
        if self.embedding_backend != "openai" or self.llm_client is None:
            return []
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_neuro_provider.py::test_neuro_provider_works_without_openai_api_key -v
```
Expected: PASS

- [ ] **Step 5: Run full suite**

Run:
```bash
uv run pytest -q
uv run ruff check .
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add memento/provider.py tests/test_neuro_provider.py
git commit -m "feat: add offline-first embedding backend selector"
```

---

## Task 4: Retrieval Tracing + Explain Tool (Observability)

**Goal:** For any query, be able to answer: which lanes contributed which candidates and why the final list looks like it does.

**Files:**
- Modify: `memento/provider.py`
- Create: `memento/tools/explain.py`
- Modify: `memento/tools/__init__.py`
- Test: `tests/test_provider.py`

- [ ] **Step 1: Write failing test for explain tool**

Append to `tests/test_provider.py`:

```python
import json
import pytest


@pytest.mark.asyncio
async def test_memento_explain_search(tmp_path):
    from memento.mcp_server import call_tool

    await call_tool("memento_add_memory", {"workspace_root": str(tmp_path), "text": "alpha hello", "metadata": {}})
    await call_tool("memento_add_memory", {"workspace_root": str(tmp_path), "text": "beta world", "metadata": {}})

    res = await call_tool("memento_explain_search", {"workspace_root": str(tmp_path), "query": "alpha"})
    payload = json.loads(res[0].text)
    assert payload["query"] == "alpha"
    assert "lanes" in payload
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_provider.py::test_memento_explain_search -v
```
Expected: FAIL (Unknown tool: memento_explain_search)

- [ ] **Step 3: Implement tracing in provider.search**

In `memento/provider.py`, inside `NeuroGraphProvider.search`:
- Capture three ranked lists:
  - `fts_ranked`: list of `{id, fts_score}`
  - `dense_ranked`: list of `{id, semantic_score}`
  - `recency_ranked`: list of `{id, recency_rank}`
- Store a trace object:

```python
trace = {
    "query": query,
    "filters": filters or {},
    "lanes": {
        "fts": [{"id": r["id"], "score": float(r["fts_score"])} for r in fts_sorted[:20]],
        "dense": [{"id": rid, "score": float(s)} for rid, s in semantic_sorted[:20]],
        "recency": [{"id": r["id"], "score": float(k_rrf + 1 - i)} for i, r in enumerate(recent_sorted[:20])],
    },
    "final": [{"id": rid, "score": float(s)} for rid, s in final_sorted[:50]],
}
```

- Save it to `ctx.workspace_root/.memento/traces/last_search.json` (ring-buffer optional later).

Because `provider.search` doesn’t know `workspace_root`, write it relative to the DB path:
- Derive `memento_dir = os.path.join(os.path.dirname(self.db_path), "traces")` if DB path is `.../.memento/neurograph_memory.db`.

- [ ] **Step 4: Add explain tool**

Create `memento/tools/explain.py`:

```python
import json
import os

from mcp.types import Tool, TextContent

from memento.registry import registry


@registry.register(
    Tool(
        name="memento_explain_search",
        description="Return the last retrieval trace for a given query (best-effort, local-only).",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    )
)
async def memento_explain_search(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f\"Cannot read memory. Current access state is: {access_manager.state}\")

    query = arguments.get(\"query\") or \"\"
    trace_path = os.path.join(ctx.workspace_root, \".memento\", \"traces\", \"last_search.json\")
    if not os.path.exists(trace_path):
        return [TextContent(type=\"text\", text=json.dumps({\"query\": query, \"error\": \"no trace\"}, indent=2, ensure_ascii=False))]

    with open(trace_path, \"r\") as f:
        payload = json.load(f)
    return [TextContent(type=\"text\", text=json.dumps(payload, indent=2, ensure_ascii=False))]
```

- [ ] **Step 5: Register module**

Modify `memento/tools/__init__.py`:

```python
from . import cognitive, coercion, core, explain, memory

__all__ = ["cognitive", "coercion", "core", "explain", "memory"]
```

- [ ] **Step 6: Run tests**

Run:
```bash
uv run pytest tests/test_provider.py::test_memento_explain_search -v
uv run pytest -q
uv run ruff check .
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add memento/provider.py memento/tools/explain.py memento/tools/__init__.py tests/test_provider.py
git commit -m "feat: add retrieval trace and explain tool"
```

---

## Follow-Up Plans (Separate Documents)

Create separate plan docs for these (so each stays reviewable and testable):
- Adaptive blending (query routing) + temporal decay for recency scoring (replacing the current recency rank boost).
- Optional reranker (top-k) behind a strict budget flag.
- Local embedding backend (`fastembed` or `sentence-transformers`) as an optional extra.
- Active Coercion override audit log (who/when/where) + report tooling.
- Threat model + SECURITY.md + poisoning/prompt-injection guidance.

