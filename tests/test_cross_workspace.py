"""Tests for cross-workspace memory sharing."""

import os
import sqlite3

import pytest

from memento.cross_workspace import CrossWorkspaceManager
from memento.migrations.versions.v001_initial_schema import up as v001_up
from memento.migrations.versions.v005_cross_workspace import up as v005_up


def _init_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    v001_up(conn)
    v005_up(conn)
    conn.commit()
    conn.close()


def _insert_memory(db_path: str, memory_id: str, text: str, metadata: str = "{}") -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO memories (id, user_id, text, created_at, metadata) "
        "VALUES (?, 'default', ?, datetime('now'), ?)",
        (memory_id, text, metadata),
    )
    conn.commit()
    conn.close()


def test_migration_creates_table(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    v005_up(conn)
    conn.commit()

    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='cross_workspace_sync_log'"
    ).fetchone()
    assert row is not None

    indexes = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_cross_workspace%'"
    ).fetchall()
    conn.close()
    assert len(indexes) >= 2


def test_migration_idempotent(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    v005_up(conn)
    conn.commit()
    v005_up(conn)
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_share_memory(tmp_path):
    os.environ["MEMENTO_EMBEDDING_BACKEND"] = "none"
    db_path = str(tmp_path / "test.db")
    _init_db(db_path)
    _insert_memory(db_path, "mem-001", "Important architectural decision about caching")

    mgr = CrossWorkspaceManager(db_path=db_path)
    result = await mgr.share_memory(
        memory_id="mem-001",
        target_workspace_path="/target/workspace",
        source_workspace_path="/source/workspace",
    )

    assert "error" not in result
    assert result["original_id"] == "mem-001"
    assert result["shared_id"].startswith("shared_")
    assert result["target_workspace"] == "/target/workspace"
    assert result["status"] == "shared"


@pytest.mark.asyncio
async def test_share_nonexistent_memory(tmp_path):
    os.environ["MEMENTO_EMBEDDING_BACKEND"] = "none"
    db_path = str(tmp_path / "test.db")
    _init_db(db_path)

    mgr = CrossWorkspaceManager(db_path=db_path)
    result = await mgr.share_memory(
        memory_id="nonexistent",
        target_workspace_path="/target/workspace",
        source_workspace_path="/source/workspace",
    )

    assert "error" in result
    assert "not found" in result["error"].lower()


@pytest.mark.asyncio
async def test_list_shared_outgoing(tmp_path):
    os.environ["MEMENTO_EMBEDDING_BACKEND"] = "none"
    db_path = str(tmp_path / "test.db")
    _init_db(db_path)
    _insert_memory(db_path, "mem-010", "Outgoing memory A")
    _insert_memory(db_path, "mem-011", "Outgoing memory B")

    mgr = CrossWorkspaceManager(db_path=db_path)
    await mgr.share_memory("mem-010", "/target/ws", "/source/ws")
    await mgr.share_memory("mem-011", "/target/ws", "/source/ws")

    outgoing = await mgr.list_shared_memories(direction="outgoing", workspace_path="/source/ws")
    assert len(outgoing) == 2
    assert all(o["source_workspace"] == "/source/ws" for o in outgoing)


@pytest.mark.asyncio
async def test_list_shared_incoming(tmp_path):
    os.environ["MEMENTO_EMBEDDING_BACKEND"] = "none"
    db_path = str(tmp_path / "test.db")
    _init_db(db_path)
    _insert_memory(db_path, "mem-020", "Incoming memory")

    mgr = CrossWorkspaceManager(db_path=db_path)
    await mgr.share_memory("mem-020", "/my/workspace", "/other/workspace")

    incoming = await mgr.list_shared_memories(direction="incoming", workspace_path="/my/workspace")
    assert len(incoming) == 1
    assert incoming[0]["target_workspace"] == "/my/workspace"
    assert incoming[0]["source_workspace"] == "/other/workspace"


@pytest.mark.asyncio
async def test_get_sync_stats(tmp_path):
    os.environ["MEMENTO_EMBEDDING_BACKEND"] = "none"
    db_path = str(tmp_path / "test.db")
    _init_db(db_path)
    _insert_memory(db_path, "mem-s1", "Stat memory 1")
    _insert_memory(db_path, "mem-s2", "Stat memory 2")

    mgr = CrossWorkspaceManager(db_path=db_path)
    await mgr.share_memory("mem-s1", "/ws/a", "/ws/source")
    await mgr.share_memory("mem-s2", "/ws/b", "/ws/source")

    stats = await mgr.get_sync_stats()
    assert stats["total"] == 2
    assert stats["shared"] == 2
    assert stats["imported"] == 0
    assert stats["pending"] == 0
    assert "/ws/source" in stats["source_workspaces"]


@pytest.mark.asyncio
async def test_import_shared_memory(tmp_path):
    os.environ["MEMENTO_EMBEDDING_BACKEND"] = "none"
    db_path = str(tmp_path / "test.db")
    _init_db(db_path)
    _insert_memory(db_path, "mem-imp", "Knowledge to import")

    mgr = CrossWorkspaceManager(db_path=db_path)
    share_result = await mgr.share_memory("mem-imp", "/target/ws", "/source/ws")
    shared_id = share_result["shared_id"]

    import_result = await mgr.import_shared_memory(
        shared_memory_id=shared_id,
        source_workspace_path="/source/ws",
        text="Knowledge to import",
        metadata={"category": "architecture"},
    )

    assert import_result["status"] == "imported"
    assert import_result["source_workspace"] == "/source/ws"
    assert "imported_memory_id" in import_result

    stats = await mgr.get_sync_stats()
    assert stats["imported"] == 1
    assert stats["shared"] == 0
