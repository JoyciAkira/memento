"""Tests for relevance tracking — hit counting, temporal boosting, and time decay."""

import sqlite3

import pytest

from memento.relevance import RelevanceTracker
from memento.migrations.versions.v001_initial_schema import up as v001_up
from memento.migrations.versions.v004_relevance_tracking import up as v004_up


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_relevance.db")


@pytest.fixture
def setup_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    v001_up(conn)
    v004_up(conn)
    conn.commit()
    conn.close()
    return db_path


def _insert_memory(conn, memory_id, text="test memory", created_at=None):
    from datetime import datetime

    now = created_at or datetime.now().isoformat()
    conn.execute(
        "INSERT INTO memories (id, user_id, text, created_at, metadata) VALUES (?, 'default', ?, ?, '{}')",
        (memory_id, text, now),
    )
    conn.execute(
        "INSERT INTO memory_meta (id, created_at, updated_at, is_deleted) VALUES (?, ?, ?, 0)",
        (memory_id, now, now),
    )
    conn.commit()


@pytest.mark.asyncio
async def test_record_hit_increments_count(setup_db):
    tracker = RelevanceTracker(db_path=setup_db)

    conn = sqlite3.connect(setup_db)
    _insert_memory(conn, "mem-1", "alpha")
    conn.close()

    await tracker.record_hit("mem-1")

    conn = sqlite3.connect(setup_db)
    row = conn.execute("SELECT hit_count FROM memory_meta WHERE id = 'mem-1'").fetchone()
    conn.close()
    assert row[0] == 1


@pytest.mark.asyncio
async def test_record_hits_batch(setup_db):
    tracker = RelevanceTracker(db_path=setup_db)

    conn = sqlite3.connect(setup_db)
    _insert_memory(conn, "mem-a", "alpha")
    _insert_memory(conn, "mem-b", "beta")
    _insert_memory(conn, "mem-c", "gamma")
    conn.close()

    await tracker.record_hits(["mem-a", "mem-b", "mem-c"])

    conn = sqlite3.connect(setup_db)
    rows = conn.execute(
        "SELECT id, hit_count FROM memory_meta WHERE id IN ('mem-a', 'mem-b', 'mem-c') ORDER BY id"
    ).fetchall()
    conn.close()
    assert all(r[1] == 1 for r in rows)


@pytest.mark.asyncio
async def test_get_boost_no_hits(setup_db):
    tracker = RelevanceTracker(db_path=setup_db)

    conn = sqlite3.connect(setup_db)
    _insert_memory(conn, "mem-1", "alpha")
    conn.close()

    boost = await tracker.get_boost("mem-1")
    assert boost == 1.0


@pytest.mark.asyncio
async def test_get_boost_unknown_memory(setup_db):
    tracker = RelevanceTracker(db_path=setup_db)
    boost = await tracker.get_boost("nonexistent")
    assert boost == 1.0


@pytest.mark.asyncio
async def test_get_boost_with_hits(setup_db):
    tracker = RelevanceTracker(db_path=setup_db)

    conn = sqlite3.connect(setup_db)
    _insert_memory(conn, "mem-1", "alpha")
    conn.close()

    await tracker.record_hit("mem-1")
    await tracker.record_hit("mem-1")
    await tracker.record_hit("mem-1")

    boost = await tracker.get_boost("mem-1")
    assert boost > 1.0


@pytest.mark.asyncio
async def test_get_boosts_multiple(setup_db):
    tracker = RelevanceTracker(db_path=setup_db)

    conn = sqlite3.connect(setup_db)
    _insert_memory(conn, "mem-x", "x content")
    _insert_memory(conn, "mem-y", "y content")
    conn.close()

    await tracker.record_hits(["mem-x", "mem-x", "mem-x"])

    boosts = await tracker.get_boosts(["mem-x", "mem-y"])
    assert boosts["mem-x"] > 1.0
    assert boosts["mem-y"] == 1.0


@pytest.mark.asyncio
async def test_get_boosts_empty(setup_db):
    tracker = RelevanceTracker(db_path=setup_db)
    boosts = await tracker.get_boosts([])
    assert boosts == {}


@pytest.mark.asyncio
async def test_get_stats(setup_db):
    tracker = RelevanceTracker(db_path=setup_db)

    conn = sqlite3.connect(setup_db)
    _insert_memory(conn, "mem-1", "alpha")
    _insert_memory(conn, "mem-2", "beta")
    _insert_memory(conn, "mem-3", "gamma")
    conn.close()

    stats = await tracker.get_stats()
    assert stats["total_memories"] == 3
    assert stats["with_hits"] == 0
    assert stats["hot_memories"] == 0
    assert stats["cold_memories"] == 3

    await tracker.record_hits(["mem-1"] * 6)

    stats = await tracker.get_stats()
    assert stats["with_hits"] == 1
    assert stats["hot_memories"] == 1
    assert stats["cold_memories"] == 2


@pytest.mark.asyncio
async def test_decay_older_memories_lower(setup_db):
    from datetime import datetime, timedelta

    tracker = RelevanceTracker(db_path=setup_db)

    old_date = (datetime.now() - timedelta(days=90)).isoformat()
    recent_date = datetime.now().isoformat()

    conn = sqlite3.connect(setup_db)
    _insert_memory(conn, "old-mem", "old", created_at=old_date)
    _insert_memory(conn, "new-mem", "new", created_at=recent_date)
    conn.close()

    await tracker.record_hits(["old-mem", "new-mem"])
    await tracker.record_hits(["old-mem", "new-mem"])

    old_boost = await tracker.get_boost("old-mem")
    new_boost = await tracker.get_boost("new-mem")
    assert new_boost > old_boost


@pytest.mark.asyncio
async def test_record_hits_empty_list(setup_db):
    tracker = RelevanceTracker(db_path=setup_db)
    await tracker.record_hits([])


def test_migration_creates_columns(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    v001_up(conn)
    v004_up(conn)
    conn.commit()

    cursor = conn.execute("PRAGMA table_info(memory_meta)")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()

    assert "hit_count" in columns
    assert "last_accessed_at" in columns


def test_migration_idempotent(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    v001_up(conn)
    conn.commit()

    v004_up(conn)
    conn.commit()

    v004_up(conn)
    conn.commit()

    cursor = conn.execute("PRAGMA table_info(memory_meta)")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()

    assert "hit_count" in columns
    assert "last_accessed_at" in columns
