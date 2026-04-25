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

