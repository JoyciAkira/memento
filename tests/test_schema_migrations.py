import sqlite3
from memento.migrations.runner import MigrationRunner
from memento.migrations.versions import get_all_migrations
from memento.migrations.versions.v001_initial_schema import up as up_001


def test_migration_runner_creates_tables(tmp_path):
    db_path = str(tmp_path / "test.db")
    runner = MigrationRunner(db_path)
    runner.register(1, "initial_schema", up_001)
    runner.run()

    conn = sqlite3.connect(db_path)
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()

    assert "memories" in tables
    assert "memory_embeddings" in tables
    assert "memory_meta" in tables
    assert "goals" in tables
    assert "_schema_migrations" in tables


def test_migration_idempotent(tmp_path):
    db_path = str(tmp_path / "test.db")
    runner = MigrationRunner(db_path)
    runner.register(1, "initial_schema", up_001)

    runner.run()
    runner.run()

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM _schema_migrations").fetchone()[0]
    conn.close()
    assert count == 1


def test_current_version(tmp_path):
    db_path = str(tmp_path / "test.db")
    runner = MigrationRunner(db_path)
    runner.register(1, "initial_schema", up_001)
    assert runner.current_version() == 0
    runner.run()
    assert runner.current_version() == 1


def test_get_all_migrations_includes_initial():
    migrations = get_all_migrations()
    assert len(migrations) >= 1
    assert migrations[0][0] == 1
    assert migrations[0][1] == "initial_schema"


def test_migration_tracks_applied_at(tmp_path):
    db_path = str(tmp_path / "test.db")
    runner = MigrationRunner(db_path)
    runner.register(1, "initial_schema", up_001)
    runner.run()

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT applied_at FROM _schema_migrations WHERE version=1"
    ).fetchone()
    conn.close()
    assert row is not None
    assert len(row[0]) > 0


def test_v009_memory_tiers_migration(tmp_path):
    db_path = str(tmp_path / "test_tiers.db")
    runner = MigrationRunner(db_path)
    runner.register(1, "initial_schema", up_001)
    runner.run()

    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO memories (id, text) VALUES ('test1', 'test content')")
    conn.commit()
    conn.close()

    from memento.migrations.versions.v009_memory_tiers import up as up_009

    runner2 = MigrationRunner(db_path)
    runner2.register(1, "initial_schema", up_001)
    runner2.register(9, "memory_tiers", up_009)
    runner2.run()

    conn2 = sqlite3.connect(db_path)
    cursor = conn2.execute("SELECT id, text, memory_tier FROM memories")
    row = cursor.fetchone()
    conn2.close()

    assert row is not None, "Row should be preserved after migration"
    assert row[0] == "test1"
    assert row[1] == "test content"
    assert row[2] == "semantic", "Default tier should be 'semantic'"


def test_get_all_migrations_includes_v009():
    migrations = get_all_migrations()
    version_map = {v: n for v, n, _ in migrations}
    assert 9 in version_map
    assert version_map[9] == "memory_tiers"


def test_get_all_migrations_includes_v012():
    migrations = get_all_migrations()
    version_map = {v: n for v, n, _ in migrations}
    assert 12 in version_map
    assert version_map[12] == "backfill_memory_tiers"


def test_v012_backfills_memory_tiers(tmp_path):
    db_path = str(tmp_path / "backfill.db")
    runner = MigrationRunner(db_path)
    for version, name, fn in get_all_migrations():
        if version == 12:
            continue
        runner.register(version, name, fn)
    runner.run()

    conn = sqlite3.connect(db_path)
    rows = [
        ("explicit", '{"memory_tier": "Episodic"}'),
        ("test-failure", '{"type": "test_failure"}'),
        ("health", '{"type": "autonomous_health_report", "level": "observe"}'),
        ("commit", '{"type": "git_commit"}'),
        ("empty-meta", "{}"),
        ("invalid-json", "not-json"),
        ("null-meta", None),
    ]
    for mem_id, metadata in rows:
        conn.execute(
            "INSERT INTO memories (id, user_id, text, created_at, metadata, memory_tier) "
            "VALUES (?, 'default', 'content', '2026-01-01T00:00:00', ?, NULL)",
            (mem_id, metadata),
        )
    conn.execute(
        "INSERT INTO memories (id, user_id, text, created_at, metadata, memory_tier) "
        "VALUES ('already-set', 'default', 'content', '2026-01-01T00:00:00', '{}', 'working')"
    )
    conn.commit()

    from memento.migrations.versions.v012_backfill_memory_tiers import up as up_012

    up_012(conn)
    up_012(conn)  # idempotent

    tiers = dict(conn.execute("SELECT id, memory_tier FROM memories").fetchall())
    conn.close()

    assert tiers["explicit"] == "episodic"
    assert tiers["test-failure"] == "episodic"
    assert tiers["health"] == "episodic"
    assert tiers["commit"] == "semantic"
    assert tiers["empty-meta"] == "semantic"
    assert tiers["invalid-json"] == "semantic"
    assert tiers["null-meta"] == "semantic"
    assert tiers["already-set"] == "working"
