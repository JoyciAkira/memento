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

