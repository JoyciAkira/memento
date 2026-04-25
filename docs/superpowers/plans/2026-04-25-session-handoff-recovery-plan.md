# Session Handoff & Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow developers to checkpoint (manual + automatic) and resume a Memento “session” across chat resets/rate-limits with one tool call, using an LLM-agnostic handoff prompt and persistent recovery (including volatile L1 working memory).

**Architecture:** Introduce persistent session tracking in the workspace SQLite DB (`sessions` + `session_events`). Wrap every MCP tool call to append an event, trigger auto-checkpoints, and produce a structured handoff prompt. Provide new MCP tools for handoff/resume/list/status. Serialize/restore L1 working memory via `NeuroGraphProvider.orchestrator.l1`.

**Tech Stack:** Python, SQLite (WAL), aiosqlite, MCP tools, pytest.

---

### Task 1: Add DB schema for sessions + events (migration v010)

**Files:**
- Create: `memento/migrations/versions/v010_sessions_handoff.py`
- Modify: `memento/migrations/versions/__init__.py`
- Test: `tests/test_sessions_migration.py`

- [ ] **Step 1: Write failing migration test**

Create `tests/test_sessions_migration.py`:

```python
import sqlite3

from memento.migrations.runner import MigrationRunner
from memento.migrations.versions import get_all_migrations


def test_sessions_tables_exist_after_migrations(tmp_path):
    db_path = tmp_path / "mem.db"
    runner = MigrationRunner(str(db_path))
    for version, name, fn in get_all_migrations():
        runner.register(version, name, fn)
    runner.run()

    conn = sqlite3.connect(str(db_path))
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' OR type='view'"
        ).fetchall()
    }
    conn.close()

    assert "sessions" in tables
    assert "session_events" in tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_sessions_migration.py`
Expected: FAIL because the tables do not exist yet.

- [ ] **Step 3: Implement migration v010**

Create `memento/migrations/versions/v010_sessions_handoff.py`:

```python
def up(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            workspace_root TEXT NOT NULL,
            parent_session_id TEXT,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            last_event_at TEXT,
            last_checkpoint_at TEXT,
            checkpoint_data TEXT,
            handoff_prompt TEXT,
            metadata TEXT
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_events (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            workspace_root TEXT NOT NULL,
            event_type TEXT NOT NULL,
            tool_name TEXT,
            active_context TEXT,
            arguments_summary TEXT,
            result_summary TEXT,
            is_error INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_workspace_started ON sessions(workspace_root, started_at DESC);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status, started_at DESC);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_events_session_created ON session_events(session_id, created_at DESC);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_events_workspace_created ON session_events(workspace_root, created_at DESC);"
    )
```

- [ ] **Step 4: Register migration in versions/__init__.py**

Modify `memento/migrations/versions/__init__.py`:

```python
from memento.migrations.versions.v010_sessions_handoff import up as up_010


def get_all_migrations():
    return [
        (1, "initial_schema", up_001),
        (2, "consolidation_log", up_002),
        (3, "kg_extraction", up_003),
        (4, "relevance_tracking", up_004),
        (5, "cross_workspace", up_005),
        (7, "performance_indexes", up_007),
        (8, "kg_schema", up_008),
        (9, "memory_tiers", up_009),
        (10, "sessions_handoff", up_010),
    ]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest -q tests/test_sessions_migration.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add memento/migrations/versions/__init__.py memento/migrations/versions/v010_sessions_handoff.py tests/test_sessions_migration.py
git commit -m "feat(sessions): add sessions + session_events schema"
```

---

### Task 2: Add serialization + restore for L1WorkingMemory

**Files:**
- Modify: `memento/memory/l1_working.py`
- Test: `tests/test_l1_working_memory_dump_restore.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_l1_working_memory_dump_restore.py`:

```python
from memento.memory.l1_working import L1WorkingMemory


def test_l1_dump_roundtrip_restores_order_and_content():
    l1 = L1WorkingMemory(max_size=10)
    l1.add("a", "A", {"x": 1})
    l1.add("b", "B", {"x": 2})

    dump = l1.dump()
    assert len(dump) == 2

    l1_new = L1WorkingMemory(max_size=10)
    l1_new.restore(dump)
    restored = l1_new.get_all()

    assert [r["id"] for r in restored] == ["a", "b"]
    assert restored[0]["content"] == "A"
    assert restored[0]["metadata"] == {"x": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_l1_working_memory_dump_restore.py`
Expected: FAIL because `dump/restore` do not exist.

- [ ] **Step 3: Implement dump/restore**

Modify `memento/memory/l1_working.py` by adding methods:

```python
from typing import Iterable


class L1WorkingMemory:
    def dump(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": item.get("id"),
                "content": item.get("content"),
                "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
                "timestamp": float(item.get("timestamp") or 0.0),
            }
            for item in self.get_all()
        ]

    def restore(self, items: Iterable[Dict[str, Any]]) -> None:
        self._cache.clear()
        seq = list(items or [])
        for raw in seq:
            if not isinstance(raw, dict):
                continue
            entry_id = raw.get("id")
            content = raw.get("content", "")
            metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
            ts = float(raw.get("timestamp") or time.time())
            if not isinstance(entry_id, str) or not entry_id:
                continue
            self._cache[entry_id] = {
                "id": entry_id,
                "content": str(content),
                "metadata": metadata,
                "timestamp": ts,
            }
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_l1_working_memory_dump_restore.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add memento/memory/l1_working.py tests/test_l1_working_memory_dump_restore.py
git commit -m "feat(l1): add dump/restore for working memory"
```

---

### Task 3: Introduce SessionStore (DB API) + HandoffPrompt renderer

**Files:**
- Create: `memento/session_store.py`
- Create: `memento/handoff_prompt.py`
- Test: `tests/test_session_store.py`

- [ ] **Step 1: Write failing tests for SessionStore**

Create `tests/test_session_store.py`:

```python
import sqlite3
import pytest

from memento.migrations.runner import MigrationRunner
from memento.migrations.versions import get_all_migrations
from memento.session_store import SessionStore


def _run_migrations(path: str) -> None:
    runner = MigrationRunner(path)
    for version, name, fn in get_all_migrations():
        runner.register(version, name, fn)
    runner.run()


@pytest.mark.asyncio
async def test_session_store_creates_session_and_logs_events(tmp_path):
    db_path = str(tmp_path / "mem.db")
    _run_migrations(db_path)

    store = SessionStore(db_path=db_path, workspace_root=str(tmp_path))
    session_id = await store.ensure_active_session()
    assert isinstance(session_id, str) and session_id

    await store.append_tool_event(
        session_id=session_id,
        tool_name="memento_search_memory",
        arguments={"query": "hello"},
        result_text="[]",
        is_error=False,
        active_context=str(tmp_path / "file.py"),
    )

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT tool_name, is_error FROM session_events WHERE session_id=?",
        (session_id,),
    ).fetchone()
    conn.close()
    assert row[0] == "memento_search_memory"
    assert row[1] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_session_store.py`
Expected: FAIL because `SessionStore` does not exist.

- [ ] **Step 3: Implement SessionStore**

Create `memento/session_store.py`:

```python
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiosqlite

from memento.redaction import redact_secrets


def _now() -> str:
    return datetime.now().isoformat()


def _truncate(text: str, limit: int) -> str:
    s = text if isinstance(text, str) else str(text)
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _safe_json(obj: Any) -> str:
    try:
        raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        raw = json.dumps({"unserializable": True}, ensure_ascii=False)
    return redact_secrets(raw)


@dataclass
class SessionRow:
    id: str
    workspace_root: str
    parent_session_id: str | None
    status: str
    started_at: str
    ended_at: str | None
    last_event_at: str | None
    last_checkpoint_at: str | None
    checkpoint_data: str | None
    handoff_prompt: str | None
    metadata: str | None


class SessionStore:
    def __init__(self, *, db_path: str, workspace_root: str):
        self.db_path = db_path
        self.workspace_root = os.path.abspath(workspace_root)

    async def ensure_active_session(self) -> str:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id FROM sessions
                WHERE workspace_root = ? AND status = 'active'
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (self.workspace_root,),
            )
            row = await cursor.fetchone()
            if row and row["id"]:
                return str(row["id"])

            session_id = str(uuid.uuid4())
            now = _now()
            await db.execute(
                """
                INSERT INTO sessions
                (id, workspace_root, parent_session_id, status, started_at, ended_at, last_event_at, last_checkpoint_at, checkpoint_data, handoff_prompt, metadata)
                VALUES (?, ?, NULL, 'active', ?, NULL, NULL, NULL, NULL, NULL, ?)
                """,
                (session_id, self.workspace_root, now, "{}"),
            )
            await db.commit()
            return session_id

    async def close_active_sessions(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            now = _now()
            await db.execute(
                """
                UPDATE sessions SET status='closed', ended_at=?
                WHERE workspace_root=? AND status='active'
                """,
                (now, self.workspace_root),
            )
            await db.commit()

    async def create_child_session(self, *, parent_session_id: str) -> str:
        await self.close_active_sessions()
        child_id = str(uuid.uuid4())
        now = _now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO sessions
                (id, workspace_root, parent_session_id, status, started_at, ended_at, last_event_at, last_checkpoint_at, checkpoint_data, handoff_prompt, metadata)
                VALUES (?, ?, ?, 'active', ?, NULL, NULL, NULL, NULL, NULL, ?)
                """,
                (child_id, self.workspace_root, parent_session_id, now, "{}"),
            )
            await db.commit()
        return child_id

    async def append_tool_event(
        self,
        *,
        session_id: str,
        tool_name: str,
        arguments: dict,
        result_text: str,
        is_error: bool,
        active_context: str | None,
    ) -> str:
        event_id = str(uuid.uuid4())
        now = _now()
        args_summary = _truncate(_safe_json(arguments), 2000)
        res_summary = _truncate(redact_secrets(result_text or ""), 2000)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO session_events
                (id, session_id, workspace_root, event_type, tool_name, active_context, arguments_summary, result_summary, is_error, created_at)
                VALUES (?, ?, ?, 'tool_call', ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    session_id,
                    self.workspace_root,
                    tool_name,
                    active_context,
                    args_summary,
                    res_summary,
                    1 if is_error else 0,
                    now,
                ),
            )
            await db.execute(
                "UPDATE sessions SET last_event_at=? WHERE id=?",
                (now, session_id),
            )
            await db.commit()
        return event_id

    async def update_checkpoint(
        self,
        *,
        session_id: str,
        checkpoint_data: dict,
        handoff_prompt: str | None,
    ) -> None:
        now = _now()
        data_str = _safe_json(checkpoint_data)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE sessions
                SET last_checkpoint_at=?, checkpoint_data=?, handoff_prompt=?
                WHERE id=?
                """,
                (now, data_str, handoff_prompt, session_id),
            )
            await db.commit()

    async def get_session(self, session_id: str) -> SessionRow | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, workspace_root, parent_session_id, status, started_at, ended_at,
                       last_event_at, last_checkpoint_at, checkpoint_data, handoff_prompt, metadata
                FROM sessions
                WHERE id=?
                """,
                (session_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return SessionRow(
                id=row["id"],
                workspace_root=row["workspace_root"],
                parent_session_id=row["parent_session_id"],
                status=row["status"],
                started_at=row["started_at"],
                ended_at=row["ended_at"],
                last_event_at=row["last_event_at"],
                last_checkpoint_at=row["last_checkpoint_at"],
                checkpoint_data=row["checkpoint_data"],
                handoff_prompt=row["handoff_prompt"],
                metadata=row["metadata"],
            )

    async def list_sessions(self, *, limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
        safe_limit = min(int(limit), 200)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            where = "WHERE workspace_root=?"
            params: list[Any] = [self.workspace_root]
            if status:
                where += " AND status=?"
                params.append(status)
            cursor = await db.execute(
                f"""
                SELECT id, parent_session_id, status, started_at, ended_at, last_event_at, last_checkpoint_at
                FROM sessions
                {where}
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (*params, safe_limit),
            )
            rows = await cursor.fetchall()
        return [
            {
                "id": r["id"],
                "parent_session_id": r["parent_session_id"],
                "status": r["status"],
                "started_at": r["started_at"],
                "ended_at": r["ended_at"],
                "last_event_at": r["last_event_at"],
                "last_checkpoint_at": r["last_checkpoint_at"],
            }
            for r in rows
        ]

    async def get_recent_events(self, *, session_id: str, limit: int = 25) -> list[dict[str, Any]]:
        safe_limit = min(int(limit), 200)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT tool_name, active_context, arguments_summary, result_summary, is_error, created_at
                FROM session_events
                WHERE session_id=?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, safe_limit),
            )
            rows = await cursor.fetchall()
        return [
            {
                "tool_name": r["tool_name"],
                "active_context": r["active_context"],
                "arguments_summary": r["arguments_summary"],
                "result_summary": r["result_summary"],
                "is_error": bool(r["is_error"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]
```

- [ ] **Step 4: Add prompt renderer (LLM-agnostic)**

Create `memento/handoff_prompt.py`:

```python
from __future__ import annotations

from typing import Any


def _as_list(v: Any) -> list:
    return v if isinstance(v, list) else []


def render_handoff_prompt(*, session_id: str, snapshot: dict[str, Any]) -> str:
    ws = snapshot.get("workspace_root") or ""
    summary = snapshot.get("summary") or ""
    goals = _as_list(snapshot.get("goals"))
    l1 = _as_list(snapshot.get("l1"))
    files = _as_list(snapshot.get("active_contexts"))
    git_context = snapshot.get("git_context") or ""
    events = _as_list(snapshot.get("recent_events"))

    goals_lines = "\n".join(f"- {g.get('goal')}" for g in goals if isinstance(g, dict) and g.get("goal"))
    goals_block = goals_lines if goals_lines else "(none)"

    l1_lines = "\n".join(
        f"- {i.get('id')}: {i.get('content')}"
        for i in l1[:20]
        if isinstance(i, dict) and i.get("id") and i.get("content")
    )
    l1_block = l1_lines if l1_lines else "(empty)"

    files_lines = "\n".join(f"- {p}" for p in files if isinstance(p, str) and p)
    files_block = files_lines if files_lines else "(none)"

    ev_lines = []
    for idx, e in enumerate(reversed(events[:15]), start=1):
        if not isinstance(e, dict):
            continue
        tn = e.get("tool_name") or ""
        ac = e.get("active_context") or ""
        ev_lines.append(f"{idx}. {tn}" + (f" ({ac})" if ac else ""))
    ev_block = "\n".join(ev_lines) if ev_lines else "(none)"

    parts = [
        "MEMENTO SESSION HANDOFF",
        f"Session: {session_id}",
        f"Workspace: {ws}",
        "",
        "WHAT I WAS DOING",
        summary or "(no summary available)",
        "",
        "ACTIVE GOALS",
        goals_block,
        "",
        "WORKING MEMORY (L1)",
        l1_block,
        "",
        "FILES / ACTIVE CONTEXTS",
        files_block,
        "",
        "GIT CONTEXT",
        git_context.strip() or "(not a git repo / unavailable)",
        "",
        "RECENT TOOL CALLS",
        ev_block,
        "",
        "TO RESUME",
        f"Call: memento_resume_session(session_id=\"{session_id}\")",
    ]
    return "\n".join(parts).strip() + "\n"
```

- [ ] **Step 5: Run tests**

Run: `pytest -q tests/test_session_store.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add memento/session_store.py memento/handoff_prompt.py tests/test_session_store.py
git commit -m "feat(sessions): add SessionStore and handoff prompt renderer"
```

---

### Task 4: Implement SessionManager (snapshot + checkpoint + restore)

**Files:**
- Create: `memento/session_manager.py`
- Test: `tests/test_session_manager_checkpoint_resume.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_session_manager_checkpoint_resume.py`:

```python
import json
import pytest

from memento.migrations.runner import MigrationRunner
from memento.migrations.versions import get_all_migrations
from memento.provider import NeuroGraphProvider
from memento.session_manager import SessionManager


def _run_migrations(path: str) -> None:
    runner = MigrationRunner(path)
    for version, name, fn in get_all_migrations():
        runner.register(version, name, fn)
    runner.run()


@pytest.mark.asyncio
async def test_checkpoint_includes_goals_and_l1(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    db_path = str(tmp_path / "mem.db")
    _run_migrations(db_path)

    p = NeuroGraphProvider(db_path=db_path)
    await p.set_goals(goals=["ship v1"], context=None, mode="replace", delete_reason="init")
    await p.initialize()
    p.orchestrator.l1.add("l1a", "hot context", {"k": "v"})

    mgr = SessionManager(db_path=db_path, workspace_root=str(tmp_path), provider=p)
    session_id = await mgr.ensure_session()
    snap = await mgr.create_checkpoint(session_id=session_id, reason="manual")

    assert any(g.get("goal") == "ship v1" for g in snap.get("goals", []))
    assert any(i.get("id") == "l1a" for i in snap.get("l1", []))


@pytest.mark.asyncio
async def test_resume_restores_l1_into_new_active_session(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    db_path = str(tmp_path / "mem.db")
    _run_migrations(db_path)

    p = NeuroGraphProvider(db_path=db_path)
    await p.initialize()
    p.orchestrator.l1.add("l1a", "hot context", {})

    mgr = SessionManager(db_path=db_path, workspace_root=str(tmp_path), provider=p)
    session_id = await mgr.ensure_session()
    await mgr.create_checkpoint(session_id=session_id, reason="manual")

    p.orchestrator.l1.clear()
    out = await mgr.resume_from(session_id=session_id)
    assert out["resumed_from"] == session_id
    assert out["new_session_id"]
    assert any(i.get("id") == "l1a" for i in p.orchestrator.l1.dump())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest -q tests/test_session_manager_checkpoint_resume.py`
Expected: FAIL because SessionManager does not exist.

- [ ] **Step 3: Implement SessionManager**

Create `memento/session_manager.py`:

```python
import json
import os
from typing import Any

from memento.git_context import build_auto_context
from memento.handoff_prompt import render_handoff_prompt
from memento.session_store import SessionStore


class SessionManager:
    def __init__(self, *, db_path: str, workspace_root: str, provider):
        self.db_path = db_path
        self.workspace_root = os.path.abspath(workspace_root)
        self.provider = provider
        self.store = SessionStore(db_path=db_path, workspace_root=self.workspace_root)

    async def ensure_session(self) -> str:
        return await self.store.ensure_active_session()

    async def create_checkpoint(self, *, session_id: str, reason: str) -> dict[str, Any]:
        await self.provider.initialize()

        goals = await self.provider.list_goals(context=None, active_only=True, limit=50, offset=0)
        l1 = []
        try:
            l1 = self.provider.orchestrator.l1.dump()
        except Exception:
            l1 = []

        git_context = build_auto_context(self.workspace_root)
        recent_events = await self.store.get_recent_events(session_id=session_id, limit=25)

        active_contexts = []
        for e in recent_events:
            ac = e.get("active_context")
            if isinstance(ac, str) and ac and ac not in active_contexts:
                active_contexts.append(ac)

        summary = ""
        if recent_events:
            last = [e.get("tool_name") for e in recent_events[:5] if isinstance(e, dict) and e.get("tool_name")]
            summary = "Recent activity: " + ", ".join(reversed(last))

        snapshot = {
            "reason": reason,
            "workspace_root": self.workspace_root,
            "summary": summary,
            "goals": goals,
            "l1": l1,
            "active_contexts": active_contexts,
            "git_context": git_context,
            "recent_events": list(reversed(recent_events)),
        }
        prompt = render_handoff_prompt(session_id=session_id, snapshot=snapshot)
        await self.store.update_checkpoint(session_id=session_id, checkpoint_data=snapshot, handoff_prompt=prompt)
        return snapshot

    async def resume_from(self, *, session_id: str) -> dict[str, Any]:
        await self.provider.initialize()

        row = await self.store.get_session(session_id)
        if row is None:
            raise ValueError(f"Unknown session_id: {session_id}")
        if not row.checkpoint_data:
            await self.create_checkpoint(session_id=session_id, reason="resume")
            row = await self.store.get_session(session_id)
            if row is None or not row.checkpoint_data:
                raise RuntimeError("Failed to create checkpoint for session")

        data = json.loads(row.checkpoint_data) if row.checkpoint_data else {}
        l1_items = data.get("l1") if isinstance(data, dict) else []
        try:
            self.provider.orchestrator.l1.restore(l1_items)
        except Exception:
            pass

        new_id = await self.store.create_child_session(parent_session_id=session_id)
        return {"resumed_from": session_id, "new_session_id": new_id}
```

- [ ] **Step 4: Run tests**

Run: `pytest -q tests/test_session_manager_checkpoint_resume.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add memento/session_manager.py tests/test_session_manager_checkpoint_resume.py
git commit -m "feat(sessions): add checkpoint and resume manager"
```

---

### Task 5: Wire SessionManager into WorkspaceContext

**Files:**
- Modify: `memento/workspace_context.py`
- Test: `tests/test_workspace_context_has_session_manager.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_workspace_context_has_session_manager.py`:

```python
def test_workspace_context_has_session_manager(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")
    from memento.workspace_context import get_workspace_context

    ctx = get_workspace_context(str(tmp_path))
    assert hasattr(ctx, "session_manager")
```

- [ ] **Step 2: Implement**

Modify `memento/workspace_context.py` to initialize the manager:

```python
from memento.session_manager import SessionManager


class WorkspaceContext:
    def __init__(self, workspace_root: str):
        self.workspace_root = os.path.abspath(workspace_root)
        self.memento_dir = os.path.join(self.workspace_root, ".memento")
        os.makedirs(self.memento_dir, exist_ok=True)

        self.db_path = os.path.join(self.memento_dir, "neurograph_memory.db")
        self.provider = NeuroGraphProvider(db_path=self.db_path)
        self.cognitive_engine = CognitiveEngine(self.provider, workspace_root=self.workspace_root)
        settings_path = os.path.join(self.memento_dir, "settings.json")
        self.access_manager = MementoAccessManager(state_path=settings_path)

        self.config = WorkspaceConfigStore(self.memento_dir, self.workspace_root)
        self.config.load()

        self.daemon = None
        self.consolidation_scheduler = None
        self.kg_extraction_scheduler = None
        self.relevance_tracker = None
        self.predictive_cache = None
        self.notification_manager = None

        self.session_manager = SessionManager(
            db_path=self.db_path,
            workspace_root=self.workspace_root,
            provider=self.provider,
        )
```

- [ ] **Step 3: Run tests**

Run: `pytest -q tests/test_workspace_context_has_session_manager.py`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add memento/workspace_context.py tests/test_workspace_context_has_session_manager.py
git commit -m "feat(sessions): attach SessionManager to WorkspaceContext"
```

---

### Task 6: Log every MCP tool call as a session event + auto-checkpoint policy

**Files:**
- Modify: `memento/mcp_server.py`
- Test: `tests/test_mcp_session_event_logging.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_mcp_session_event_logging.py`:

```python
import sqlite3
import pytest

from memento.mcp_server import call_tool


@pytest.mark.asyncio
async def test_mcp_call_tool_logs_session_event(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")
    monkeypatch.setenv("MEMENTO_HANDOFF_AUTO_CHECKPOINT_EVERY_N_EVENTS", "1000000")

    ws = str(tmp_path)
    await call_tool("memento_list_goals", {"workspace_root": ws})

    db_path = tmp_path / ".memento" / "neurograph_memory.db"
    conn = sqlite3.connect(str(db_path))
    cnt = conn.execute("SELECT COUNT(*) FROM session_events").fetchone()[0]
    conn.close()
    assert cnt >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_mcp_session_event_logging.py`
Expected: FAIL because logging isn’t wired yet.

- [ ] **Step 3: Implement event logging + auto checkpoint**

Modify `memento/mcp_server.py` `call_tool()` to:
1) Ensure an active session exists for the workspace
2) Execute the tool
3) Log the event in `session_events`
4) If auto-checkpoint policy triggers, create a checkpoint

Implementation sketch to apply inside `call_tool()`:

```python
import os


def _auto_checkpoint_every_n() -> int:
    try:
        return max(int(os.environ.get("MEMENTO_HANDOFF_AUTO_CHECKPOINT_EVERY_N_EVENTS", "25")), 1)
    except Exception:
        return 25


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    ctx = get_workspace_context(workspace_root)
    session_id = await ctx.session_manager.ensure_session()

    is_error = False
    out: list[TextContent] = []
    try:
        out = await registry.execute(name, arguments, ctx, access_manager=ctx.access_manager)
        return out
    except Exception:
        is_error = True
        raise
    finally:
        try:
            active_context = arguments.get("active_context") if isinstance(arguments, dict) else None
            result_text = "\n".join(
                c.text for c in out if getattr(c, "type", None) == "text" and isinstance(getattr(c, "text", None), str)
            )
            await ctx.session_manager.store.append_tool_event(
                session_id=session_id,
                tool_name=name,
                arguments=arguments if isinstance(arguments, dict) else {},
                result_text=result_text,
                is_error=is_error,
                active_context=active_context if isinstance(active_context, str) else None,
            )

            n = _auto_checkpoint_every_n()
            events = await ctx.session_manager.store.get_recent_events(session_id=session_id, limit=n)
            if len(events) >= n:
                await ctx.session_manager.create_checkpoint(session_id=session_id, reason="auto")
        except Exception:
            pass
```

- [ ] **Step 4: Run test**

Run: `pytest -q tests/test_mcp_session_event_logging.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add memento/mcp_server.py tests/test_mcp_session_event_logging.py
git commit -m "feat(sessions): log MCP tool calls and auto-checkpoint"
```

---

### Task 7: Add MCP tools: begin_session, handoff, resume_session, list_sessions, session_status

**Files:**
- Create: `memento/tools/sessions.py`
- Modify: `memento/tools/__init__.py`
- Test: `tests/test_mcp_sessions_tools.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_mcp_sessions_tools.py`:

```python
import pytest
from memento.mcp_server import call_tool


@pytest.mark.asyncio
async def test_handoff_and_resume_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")
    ws = str(tmp_path)

    out = await call_tool("memento_handoff", {"workspace_root": ws})
    text = out[0].text
    assert "MEMENTO SESSION HANDOFF" in text
    assert "Session:" in text

    session_id_line = next(line for line in text.splitlines() if line.startswith("Session:"))
    session_id = session_id_line.split("Session:", 1)[1].strip()
    out2 = await call_tool("memento_resume_session", {"workspace_root": ws, "session_id": session_id})
    assert "resumed_from" in out2[0].text
```

- [ ] **Step 2: Implement tools**

Create `memento/tools/sessions.py`:

```python
import json
import logging

from mcp.types import Tool, TextContent

from memento.registry import registry

logger = logging.getLogger("memento-mcp")


@registry.register(
    Tool(
        name="memento_begin_session",
        description="Start a new Memento session for this workspace (closes any active session).",
        inputSchema={"type": "object", "properties": {"workspace_root": {"type": "string"}}},
    )
)
async def memento_begin_session(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_write():
        raise PermissionError(f"Cannot begin session. Current access state is: {access_manager.state}")
    await ctx.session_manager.store.close_active_sessions()
    sid = await ctx.session_manager.store.ensure_active_session()
    return [TextContent(type="text", text=json.dumps({"session_id": sid}, ensure_ascii=False))]


@registry.register(
    Tool(
        name="memento_handoff",
        description="Create a checkpoint and generate an LLM-agnostic handoff prompt for continuing in a new chat.",
        inputSchema={
            "type": "object",
            "properties": {"workspace_root": {"type": "string"}, "reason": {"type": "string"}},
        },
    )
)
async def memento_handoff(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot read handoff. Current access state is: {access_manager.state}")
    sid = await ctx.session_manager.ensure_session()
    reason = arguments.get("reason") or "manual"
    await ctx.session_manager.create_checkpoint(session_id=sid, reason=str(reason))
    row = await ctx.session_manager.store.get_session(sid)
    prompt = row.handoff_prompt if row else None
    return [TextContent(type="text", text=prompt or "")]


@registry.register(
    Tool(
        name="memento_resume_session",
        description="Resume from a previous session_id by restoring its checkpoint (including L1) and opening a new active session.",
        inputSchema={
            "type": "object",
            "properties": {"workspace_root": {"type": "string"}, "session_id": {"type": "string"}},
            "required": ["session_id"],
        },
    )
)
async def memento_resume_session(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_write():
        raise PermissionError(f"Cannot resume session. Current access state is: {access_manager.state}")
    session_id = arguments.get("session_id")
    out = await ctx.session_manager.resume_from(session_id=str(session_id))
    return [TextContent(type="text", text=json.dumps(out, ensure_ascii=False))]


@registry.register(
    Tool(
        name="memento_list_sessions",
        description="List recent sessions for the current workspace.",
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_root": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
                "status": {"type": "string"},
            },
        },
    )
)
async def memento_list_sessions(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot list sessions. Current access state is: {access_manager.state}")
    limit = int(arguments.get("limit") or 20)
    status = arguments.get("status")
    out = await ctx.session_manager.store.list_sessions(limit=limit, status=status)
    return [TextContent(type="text", text=json.dumps(out, ensure_ascii=False, indent=2))]


@registry.register(
    Tool(
        name="memento_session_status",
        description="Show status for the current active session in this workspace.",
        inputSchema={"type": "object", "properties": {"workspace_root": {"type": "string"}}},
    )
)
async def memento_session_status(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot read session status. Current access state is: {access_manager.state}")
    sid = await ctx.session_manager.ensure_session()
    row = await ctx.session_manager.store.get_session(sid)
    out = {
        "session_id": sid,
        "status": row.status if row else None,
        "started_at": row.started_at if row else None,
        "last_event_at": row.last_event_at if row else None,
        "last_checkpoint_at": row.last_checkpoint_at if row else None,
    }
    return [TextContent(type="text", text=json.dumps(out, ensure_ascii=False, indent=2))]
```

- [ ] **Step 3: Register the new tools module**

Modify `memento/tools/__init__.py` to include `sessions`:

```python
from . import (
    sessions,
)

__all__ = [
    "sessions",
]
```

- [ ] **Step 4: Run tests**

Run: `pytest -q tests/test_mcp_sessions_tools.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add memento/tools/__init__.py memento/tools/sessions.py tests/test_mcp_sessions_tools.py
git commit -m "feat(sessions): add MCP tools for handoff and resume"
```

---

### Task 8: Update tool smoke suite to include new tools and keep contracts green

**Files:**
- Modify: `tests/test_tools_smoke.py`
- Modify: `tests/test_mcp_tool_contracts.py` (if it enumerates expected tool names)

- [ ] **Step 1: Extend smoke payloads**

Add payloads for:
- `memento_begin_session`
- `memento_handoff`
- `memento_resume_session`
- `memento_list_sessions`
- `memento_session_status`

Use `ws` and for resume parse `session_id` from `memento_handoff` response.

- [ ] **Step 2: Run smoke test**

Run: `pytest -q tests/test_tools_smoke.py::test_all_tools_smoke -k sessions -vv`
Expected: PASS (or isolate failures and fix).

- [ ] **Step 3: Commit**

```bash
git add tests/test_tools_smoke.py tests/test_mcp_tool_contracts.py
git commit -m "test(sessions): cover handoff tools in MCP smoke suite"
```

---

### Task 9: End-to-end validation script (manual)

**Goal:** Validate handoff/resume across “new chat” conditions without relying on an LLM provider.

- [ ] **Step 1: Start MCP server (dev)**

Run: `python -m memento.mcp_server`

- [ ] **Step 2: In chat A**

Call:
- `memento_add_memory` (a few times)
- `memento_set_goals`
- `memento_handoff`

Copy the returned prompt and session id.

- [ ] **Step 3: In chat B**

Call:
- `memento_resume_session(session_id="PASTE_SESSION_ID_HERE")`
- `memento_session_status`
- `memento_handoff`

Expected:
- Resume returns a new active session id
- L1 restored (visible indirectly via subsequent `memento_handoff` containing L1)

---

## Plan Self-Review

- Coverage: introduces DB schema, logs every tool call, auto-checkpoints, manual handoff, resume with L1 restoration, and list/status tools.
- No placeholders: every task contains concrete code and test commands.
- Consistency: `SessionStore` owns DB I/O; `SessionManager` owns snapshot/restore; MCP server owns interception.
