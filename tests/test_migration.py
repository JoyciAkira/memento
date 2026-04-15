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
        _insert(
            source_db,
            "id1",
            "NEXUS-LM PROJECT GOAL: determinism",
            "2026-01-01T00:00:00",
        )
        _insert(
            source_db,
            "id2",
            "Zeronode Swarm Inference God Architecture",
            "2026-01-02T00:00:00",
        )
        _insert(source_db, "id3", "Generic note without match", "2026-01-03T00:00:00")
        _insert(source_db, "id4", "NEXUS-LM and ZERONODE together (ambiguous)", "2026-01-04T00:00:00")

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
