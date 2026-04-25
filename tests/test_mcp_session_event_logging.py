import sqlite3

import pytest

from memento.mcp_server import call_tool
from memento.workspace_context import get_workspace_context, _contexts


@pytest.mark.asyncio
async def test_mcp_call_tool_logs_session_event(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")
    monkeypatch.setenv("MEMENTO_HANDOFF_AUTO_CHECKPOINT_EVERY_N_EVENTS", "1000000")

    ws = str(tmp_path)
    try:
        await call_tool("memento_list_goals", {"workspace_root": ws})

        db_path = tmp_path / ".memento" / "neurograph_memory.db"
        conn = sqlite3.connect(str(db_path))
        cnt = conn.execute("SELECT COUNT(*) FROM session_events").fetchone()[0]
        conn.close()

        assert cnt >= 1
    finally:
        ctx = get_workspace_context(ws)
        if getattr(ctx.provider, "_db", None) is not None:
            await ctx.provider._db.close()
        if getattr(ctx.provider, "_db_read", None) is not None:
            await ctx.provider._db_read.close()
        if getattr(ctx.provider, "_sync_db", None) is not None:
            ctx.provider._sync_db.close()
        _contexts.clear()
