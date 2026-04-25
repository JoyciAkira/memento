import sqlite3

import pytest

from memento.mcp_server import call_tool
from memento.workspace_context import get_workspace_context, _contexts


@pytest.mark.asyncio
async def test_auto_checkpoint_triggers_every_n_events_only(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")
    monkeypatch.setenv("MEMENTO_HANDOFF_AUTO_CHECKPOINT_EVERY_N_EVENTS", "2")

    ws = str(tmp_path)
    try:
        await call_tool("memento_list_goals", {"workspace_root": ws})

        db_path = tmp_path / ".memento" / "neurograph_memory.db"
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT last_checkpoint_at FROM sessions ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        first_ckpt = row[0]
        conn.close()
        assert first_ckpt is None

        await call_tool("memento_list_goals", {"workspace_root": ws})
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT last_checkpoint_at FROM sessions ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        second_ckpt = row[0]
        conn.close()
        assert second_ckpt is not None

        await call_tool("memento_list_goals", {"workspace_root": ws})
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT last_checkpoint_at FROM sessions ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        third_ckpt = row[0]
        conn.close()

        assert third_ckpt == second_ckpt
    finally:
        ctx = get_workspace_context(ws)
        if getattr(ctx.provider, "_db", None) is not None:
            await ctx.provider._db.close()
        if getattr(ctx.provider, "_db_read", None) is not None:
            await ctx.provider._db_read.close()
        if getattr(ctx.provider, "_sync_db", None) is not None:
            ctx.provider._sync_db.close()
        _contexts.clear()

