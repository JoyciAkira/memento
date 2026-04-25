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

