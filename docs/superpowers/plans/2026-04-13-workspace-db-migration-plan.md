# Workspace Memory Isolation + Safe Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every workspace uses its own SQLite memory DB (`<workspace>/.memento/neurograph_memory.db`) and provide a safe, deterministic, copy-only migration tool to redistribute memories from a global DB into per-workspace DBs.

**Architecture:** Harden workspace selection to rely on `MEMENTO_DIR` and avoid treating `.memento` as a project-root marker. Add a migration module that reads memories from a source DB, classifies them into exactly one target workspace via deterministic text heuristics, copies them idempotently into `<workspace>/.memento/neurograph_memory.db`, and writes a report (including ambiguous/unassigned entries).

**Tech Stack:** Python stdlib (sqlite3, json, os, pathlib, shutil, datetime), pytest, ruff, MCP server tools.

---

## File map (new/modified)

**New**
- `memento/migration.py` — DB I/O + classification + copy-only migration + report generation
- `tests/test_migration.py` — integration tests for migration (copy, idempotent, report, unassigned/ambiguous)
- `tests/test_workspace_binding.py` — workspace root hardening tests (avoid `.memento` as marker, honor `MEMENTO_DIR`)

**Modified**
- `memento/mcp_server.py` — harden `find_project_root()` markers; add new MCP tool `memento_migrate_workspace_memories`
- `memento/provider.py` — inject workspace metadata into `NeuroGraphProvider.add()` (future-proofing)

---

### Task 1: Harden workspace root detection (don’t use `.memento` as a root marker)

**Files:**
- Modify: `memento/mcp_server.py`
- Test: `tests/test_workspace_binding.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_workspace_binding.py`:

```python
import os
import tempfile

import pytest


def test_find_project_root_does_not_use_memento_marker(monkeypatch):
    import memento.mcp_server as ms

    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as repo:
        monkeypatch.chdir(home)
        os.makedirs(os.path.join(home, ".memento"), exist_ok=True)

        os.makedirs(os.path.join(repo, ".git"), exist_ok=True)
        nested = os.path.join(repo, "src", "deep")
        os.makedirs(nested, exist_ok=True)

        root = ms.find_project_root(nested)
        assert root == os.path.abspath(repo)


@pytest.mark.asyncio
async def test_mcp_server_workspace_prefers_memento_dir(monkeypatch):
    import importlib

    with tempfile.TemporaryDirectory() as ws:
        monkeypatch.setenv("MEMENTO_DIR", ws)
        import memento.mcp_server as ms
        importlib.reload(ms)
        res = await ms.call_tool("memento_status", {})
        assert ws in res[0].text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_workspace_binding.py -v
```

Expected: FAIL (the first test fails if `.memento` is treated as a marker and root detection is wrong, or second fails if workspace isn’t honoring env).

- [ ] **Step 3: Implement the hardening**

Update `memento/mcp_server.py` by removing `.memento` from `markers` in `find_project_root()`:

```python
def find_project_root(current_dir):
    markers = [".git", "package.json", "pyproject.toml", "cargo.toml"]
    d = os.path.abspath(current_dir)
    original_dir = d
    while True:
        for marker in markers:
            if os.path.exists(os.path.join(d, marker)):
                return d
        parent = os.path.dirname(d)
        if parent == d:
            return original_dir
        d = parent
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_workspace_binding.py -v
```

Expected: PASS.

- [ ] **Step 5: Run the full test suite**

Run:

```bash
uv run pytest tests/ -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add memento/mcp_server.py tests/test_workspace_binding.py
git commit -m "fix: harden workspace root detection to avoid global .memento marker"
```

---

### Task 2: Add workspace metadata on writes (future-proofing for deterministic migrations)

**Files:**
- Modify: `memento/provider.py`
- Test: `tests/test_provider.py` (new test added there)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_provider.py`:

```python
import os
import tempfile

from unittest.mock import patch


def test_neurograph_add_injects_workspace_metadata():
    from memento.provider import NeuroGraphProvider

    with tempfile.TemporaryDirectory() as ws:
        with patch.dict(os.environ, {"MEMENTO_DIR": ws}):
            p = NeuroGraphProvider()
            p.add("hello", metadata={})

            db = p.db_path
            import sqlite3
            conn = sqlite3.connect(db)
            row = conn.execute(
                "SELECT metadata FROM memories ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            assert row is not None
            assert "workspace_root" in row[0]
            assert os.path.basename(ws) in row[0]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/test_provider.py::test_neurograph_add_injects_workspace_metadata -v
```

Expected: FAIL (metadata currently does not automatically include workspace fields).

- [ ] **Step 3: Implement metadata injection**

Update `NeuroGraphProvider.add()` in `memento/provider.py`:

```python
    def add(self, text: str, user_id: str = "default", metadata: dict = None) -> Dict[str, Any]:
        text = redact_secrets(text)
        memory_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        import json

        meta = dict(metadata) if isinstance(metadata, dict) else {}
        workspace_root = os.environ.get("MEMENTO_DIR")
        if isinstance(workspace_root, str) and workspace_root.strip():
            meta.setdefault("workspace_root", os.path.abspath(workspace_root))
            meta.setdefault("workspace_name", os.path.basename(os.path.abspath(workspace_root)))

        meta_str = json.dumps(meta) if meta else "{}"
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
uv run pytest tests/test_provider.py::test_neurograph_add_injects_workspace_metadata -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run:

```bash
uv run pytest tests/ -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add memento/provider.py tests/test_provider.py
git commit -m "feat: inject workspace metadata into neurograph memories"
```

---

### Task 3: Implement safe copy-only migration module (heuristic classification + idempotent copy + report)

**Files:**
- Create: `memento/migration.py`
- Test: `tests/test_migration.py`

- [ ] **Step 1: Write failing migration tests**

Create `tests/test_migration.py`:

```python
import json
import os
import sqlite3
import tempfile

from memento.migration import migrate_memories_copy_only


def _init_db(db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS memories USING fts5(id UNINDEXED, user_id UNINDEXED, text, created_at UNINDEXED, metadata UNINDEXED);"
    )
    conn.commit()
    conn.close()


def _insert(db_path: str, mem_id: str, text: str, created_at: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO memories (id, user_id, text, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
        (mem_id, "default", text, created_at, "{}"),
    )
    conn.commit()
    conn.close()


def _count(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    n = conn.execute("SELECT count(*) FROM memories").fetchone()[0]
    conn.close()
    return n


def test_migration_copy_only_is_idempotent_and_creates_report():
    with tempfile.TemporaryDirectory() as tmp:
        ws1 = os.path.join(tmp, "NEXUS-LM")
        ws2 = os.path.join(tmp, "ZERONODE")
        os.makedirs(ws1, exist_ok=True)
        os.makedirs(ws2, exist_ok=True)

        source_db = os.path.join(tmp, "global", "neurograph_memory.db")
        _init_db(source_db)
        _insert(source_db, "id1", "OBIETTIVO PROGETTO NEXUS-LM: determinismo", "2026-01-01T00:00:00")
        _insert(source_db, "id2", "Zeronode Swarm Inference God Architecture", "2026-01-02T00:00:00")
        _insert(source_db, "id3", "Nota generica senza match", "2026-01-03T00:00:00")
        _insert(source_db, "id4", "NEXUS-LM e ZERONODE insieme (ambiguous)", "2026-01-04T00:00:00")

        report_path = os.path.join(tmp, "report.json")

        r1 = migrate_memories_copy_only(
            source_db_path=source_db,
            workspace_roots=[ws1, ws2],
            report_path=report_path,
        )
        assert os.path.exists(report_path)
        assert r1["summary"]["copied_total"] == 2
        assert r1["summary"]["unassigned_total"] == 1
        assert r1["summary"]["ambiguous_total"] == 1

        target1 = os.path.join(ws1, ".memento", "neurograph_memory.db")
        target2 = os.path.join(ws2, ".memento", "neurograph_memory.db")
        assert _count(target1) == 1
        assert _count(target2) == 1
        assert _count(source_db) == 4

        r2 = migrate_memories_copy_only(
            source_db_path=source_db,
            workspace_roots=[ws1, ws2],
            report_path=report_path,
        )
        assert r2["summary"]["copied_total"] == 0
        assert _count(target1) == 1
        assert _count(target2) == 1

        with open(report_path, "r") as f:
            payload = json.load(f)
        assert "unassigned" in payload
        assert "ambiguous" in payload
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_migration.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'memento.migration'`.

- [ ] **Step 3: Implement `memento/migration.py`**

Create `memento/migration.py`:

```python
from __future__ import annotations

import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class WorkspaceTarget:
    root: str
    name: str
    db_path: str


def _init_db(db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS memories USING fts5(id UNINDEXED, user_id UNINDEXED, text, created_at UNINDEXED, metadata UNINDEXED);"
    )
    conn.commit()
    conn.close()


def _read_all_memories(db_path: str) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT id, user_id, text, created_at, metadata FROM memories ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "user_id": r[1],
            "text": r[2],
            "created_at": r[3],
            "metadata": r[4],
        }
        for r in rows
    ]


def _exists_id(db_path: str, mem_id: str) -> bool:
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT 1 FROM memories WHERE id = ? LIMIT 1", (mem_id,)).fetchone()
    conn.close()
    return row is not None


def _insert_memory(db_path: str, mem: dict[str, Any]) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO memories (id, user_id, text, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
        (mem["id"], mem.get("user_id", "default"), mem["text"], mem["created_at"], mem.get("metadata") or "{}"),
    )
    conn.commit()
    conn.close()


def _targets_from_workspace_roots(workspace_roots: list[str]) -> list[WorkspaceTarget]:
    targets: list[WorkspaceTarget] = []
    for root in workspace_roots:
        abs_root = os.path.abspath(root)
        name = os.path.basename(abs_root)
        db_path = os.path.join(abs_root, ".memento", "neurograph_memory.db")
        targets.append(WorkspaceTarget(root=abs_root, name=name, db_path=db_path))
    return targets


def classify_memory_to_targets(memory_text: str, targets: list[WorkspaceTarget]) -> list[WorkspaceTarget]:
    text = (memory_text or "").lower()
    matches: list[WorkspaceTarget] = []
    for t in targets:
        if t.name.lower() and t.name.lower() in text:
            matches.append(t)
    return matches


def migrate_memories_copy_only(
    source_db_path: str,
    workspace_roots: list[str],
    report_path: str | None = None,
) -> dict[str, Any]:
    if not os.path.exists(source_db_path):
        raise FileNotFoundError(source_db_path)

    targets = _targets_from_workspace_roots(workspace_roots)
    for t in targets:
        _init_db(t.db_path)

    backup_dir = os.path.join(os.path.dirname(source_db_path), "backup")
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(
        backup_dir,
        f"{os.path.basename(source_db_path)}.{datetime.now().strftime('%Y%m%d%H%M%S')}.bak",
    )
    shutil.copy2(source_db_path, backup_path)

    memories = _read_all_memories(source_db_path)

    per_workspace: dict[str, dict[str, int]] = {t.root: {"copied": 0, "skipped_existing": 0} for t in targets}
    unassigned: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []

    copied_total = 0
    for mem in memories:
        mem_id = str(mem.get("id") or "")
        text = str(mem.get("text") or "")

        matches = classify_memory_to_targets(text, targets)
        if len(matches) == 0:
            unassigned.append({"id": mem_id, "created_at": mem.get("created_at"), "snippet": text[:200]})
            continue
        if len(matches) > 1:
            ambiguous.append(
                {
                    "id": mem_id,
                    "created_at": mem.get("created_at"),
                    "candidates": [m.root for m in matches],
                    "snippet": text[:200],
                }
            )
            continue

        target = matches[0]
        if _exists_id(target.db_path, mem_id):
            per_workspace[target.root]["skipped_existing"] += 1
            continue

        _insert_memory(target.db_path, mem)
        per_workspace[target.root]["copied"] += 1
        copied_total += 1

    payload = {
        "source_db_path": os.path.abspath(source_db_path),
        "backup_path": os.path.abspath(backup_path),
        "workspaces": [{"root": t.root, "name": t.name, "db_path": t.db_path} for t in targets],
        "per_workspace": per_workspace,
        "unassigned": unassigned,
        "ambiguous": ambiguous,
        "summary": {
            "seen_total": len(memories),
            "copied_total": copied_total,
            "unassigned_total": len(unassigned),
            "ambiguous_total": len(ambiguous),
        },
        "generated_at": datetime.now().isoformat(),
    }

    if report_path:
        os.makedirs(os.path.dirname(os.path.abspath(report_path)), exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    return payload
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_migration.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add memento/migration.py tests/test_migration.py
git commit -m "feat: add copy-only memory migration to per-workspace databases"
```

---

### Task 4: Expose migration as an MCP tool (manual workspace list + copy-only)

**Files:**
- Modify: `memento/mcp_server.py`
- Test: `tests/test_mcp_daemon.py` (new test appended)

- [ ] **Step 1: Write a failing MCP-tool test**

Append to `tests/test_mcp_daemon.py`:

```python
import os
import tempfile

import pytest


@pytest.mark.asyncio
async def test_migrate_workspace_memories_tool(monkeypatch):
    import importlib
    import sqlite3

    with tempfile.TemporaryDirectory() as tmp:
        ws1 = os.path.join(tmp, "NEXUS-LM")
        os.makedirs(ws1, exist_ok=True)
        monkeypatch.setenv("MEMENTO_DIR", ws1)

        import memento.mcp_server as ms
        importlib.reload(ms)

        source_db = os.path.join(tmp, "global.db")
        conn = sqlite3.connect(source_db)
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS memories USING fts5(id UNINDEXED, user_id UNINDEXED, text, created_at UNINDEXED, metadata UNINDEXED);"
        )
        conn.execute(
            "INSERT INTO memories (id, user_id, text, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
            ("id1", "default", "OBIETTIVO NEXUS-LM", "2026-01-01T00:00:00", "{}"),
        )
        conn.commit()
        conn.close()

        res = await ms.call_tool(
            "memento_migrate_workspace_memories",
            {"source_db_path": source_db, "workspace_roots": [ws1]},
        )
        assert "copied_total" in res[0].text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_mcp_daemon.py::test_migrate_workspace_memories_tool -v
```

Expected: FAIL with “Unknown tool” or missing handler.

- [ ] **Step 3: Add tool schema and handler**

In `memento/mcp_server.py`, add tool to `list_tools()`:

```python
        Tool(
            name="memento_migrate_workspace_memories",
            description="Copy-only migration: redistribute memories from a source DB into per-workspace DBs using deterministic text heuristics. Produces a JSON report.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source_db_path": {"type": "string"},
                    "workspace_roots": {"type": "array", "items": {"type": "string"}},
                    "report_path": {"type": "string"},
                },
                "required": ["source_db_path", "workspace_roots"],
            },
        ),
```

Then add a handler branch in `call_tool()`:

```python
    elif name == "memento_migrate_workspace_memories":
        source_db_path = arguments.get("source_db_path")
        workspace_roots = arguments.get("workspace_roots")
        report_path = arguments.get("report_path") or os.path.join(workspace, ".memento", "migration_report.json")

        if not source_db_path or not isinstance(source_db_path, str):
            raise ValueError("source_db_path is required")
        if not isinstance(workspace_roots, list) or not workspace_roots:
            raise ValueError("workspace_roots must be a non-empty list")

        from memento.migration import migrate_memories_copy_only

        report = migrate_memories_copy_only(
            source_db_path=source_db_path,
            workspace_roots=workspace_roots,
            report_path=report_path,
        )

        import json
        return [TextContent(type="text", text=json.dumps(report["summary"], indent=2, ensure_ascii=False))]
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_mcp_daemon.py::test_migrate_workspace_memories_tool -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run:

```bash
uv run pytest tests/ -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add memento/mcp_server.py tests/test_mcp_daemon.py
git commit -m "feat: expose workspace memory migration as MCP tool"
```

---

## Self-review checklist (plan author)

- Spec coverage: workspace binding hardening, per-workspace DB path, copy-only migration, idempotence, report, safety backup, metadata future-proofing.
- Placeholder scan: no TBD/TODO; every step has concrete code, commands, and expected outcomes.
- Type consistency: migration payload keys and the MCP tool’s output schema align with tests.
