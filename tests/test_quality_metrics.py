import sqlite3
import uuid
from datetime import datetime, timedelta

import pytest

from memento.quality_metrics import QualityMetrics
from memento.knowledge_graph import KnowledgeGraph
from memento.migrations.versions.v001_initial_schema import up as v001_up
from memento.migrations.versions.v004_relevance_tracking import up as v004_up


@pytest.mark.asyncio
async def test_memory_stats_basic(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    from memento.provider import NeuroGraphProvider

    db_path = str(tmp_path / "basic.db")
    provider = NeuroGraphProvider(db_path=db_path)
    await provider.initialize()

    await provider.add("Memory about Python testing.", user_id="alice")
    await provider.add("Memory about Rust systems.", user_id="bob")

    monkeypatch.undo()

    metrics = QualityMetrics(db_path=db_path)
    stats = await metrics.memory_stats()

    assert stats["total_memories"] == 2
    assert stats["active_memories"] == 2
    assert stats["deleted_memories"] == 0


@pytest.mark.asyncio
async def test_memory_stats_age_distribution(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    from memento.provider import NeuroGraphProvider

    db_path = str(tmp_path / "age.db")
    provider = NeuroGraphProvider(db_path=db_path)
    await provider.initialize()

    now = datetime.now()
    old_ts = (now - timedelta(days=10)).isoformat()
    recent_ts = now.isoformat()

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO memories (id, user_id, text, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), "default", "Old memory", old_ts, "{}"),
    )
    conn.execute(
        "INSERT INTO memories (id, user_id, text, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), "default", "Recent memory", recent_ts, "{}"),
    )
    conn.commit()
    conn.close()

    monkeypatch.undo()

    metrics = QualityMetrics(db_path=db_path)
    stats = await metrics.memory_stats()

    assert "age_distribution" in stats
    ad = stats["age_distribution"]
    assert ad["max_days"] >= ad["min_days"]
    assert ad["avg_days"] > 0


@pytest.mark.asyncio
async def test_memory_stats_excludes_deleted(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    from memento.provider import NeuroGraphProvider

    db_path = str(tmp_path / "del.db")
    provider = NeuroGraphProvider(db_path=db_path)
    await provider.initialize()

    r1 = await provider.add("Active memory", user_id="default")
    r2 = await provider.add("To be deleted", user_id="default")

    await provider.soft_delete_memory(r2["id"], delete_reason="test cleanup")

    monkeypatch.undo()

    metrics = QualityMetrics(db_path=db_path)
    stats = await metrics.memory_stats()

    assert stats["total_memories"] == 2
    assert stats["active_memories"] == 1
    assert stats["deleted_memories"] == 1


@pytest.mark.asyncio
async def test_kg_health_basic(tmp_path):
    kg_db_path = str(tmp_path / "kg_basic.db")
    kg = KnowledgeGraph(db_path=kg_db_path)

    kg.add_entity("Alice", "person")
    kg.add_entity("React", "technology")
    kg.add_triple("Alice", "uses", "React")

    kg.close()

    metrics = QualityMetrics(db_path=":memory:", kg_db_path=kg_db_path)
    health = await metrics.kg_health()

    assert health["entities"] == 2
    assert health["total_triples"] == 1
    assert health["current_triples"] == 1
    assert health["expired_triples"] == 0


@pytest.mark.asyncio
async def test_kg_health_predicates(tmp_path):
    kg_db_path = str(tmp_path / "kg_pred.db")
    kg = KnowledgeGraph(db_path=kg_db_path)

    kg.add_triple("Alice", "uses", "React")
    kg.add_triple("Bob", "loves", "Python")
    kg.add_triple("Carol", "uses", "TypeScript")

    kg.close()

    metrics = QualityMetrics(db_path=":memory:", kg_db_path=kg_db_path)
    health = await metrics.kg_health()

    preds = {p["predicate"]: p["count"] for p in health["top_predicates"]}
    assert "uses" in preds
    assert preds["uses"] == 2
    assert "loves" in preds
    assert preds["loves"] == 1


@pytest.mark.asyncio
async def test_kg_health_entity_types(tmp_path):
    kg_db_path = str(tmp_path / "kg_types.db")
    kg = KnowledgeGraph(db_path=kg_db_path)

    kg.add_entity("Alice", "person")
    kg.add_entity("React", "technology")
    kg.add_entity("Python", "technology")

    kg.close()

    metrics = QualityMetrics(db_path=":memory:", kg_db_path=kg_db_path)
    health = await metrics.kg_health()

    types = {t["type"]: t["count"] for t in health["entity_types"]}
    assert types.get("technology", 0) == 2
    assert types.get("person", 0) == 1


@pytest.mark.asyncio
async def test_consolidation_effectiveness(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    from memento.provider import NeuroGraphProvider

    db_path = str(tmp_path / "consol.db")
    provider = NeuroGraphProvider(db_path=db_path)
    await provider.initialize()

    now = datetime.now().isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO consolidation_log (id, consolidated_into_id, source_ids, source_count, fused_text_preview, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), str(uuid.uuid4()), "[]", 3, "fused text", now),
    )
    conn.execute(
        "INSERT INTO consolidation_log (id, consolidated_into_id, source_ids, source_count, fused_text_preview, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), str(uuid.uuid4()), "[]", 5, "fused text 2", now),
    )
    conn.commit()
    conn.close()

    monkeypatch.undo()

    metrics = QualityMetrics(db_path=db_path)
    result = await metrics.consolidation_effectiveness()

    assert result["consolidation_runs"] == 2
    assert result["total_memories_fused"] == 8
    assert result["avg_sources_per_run"] == 4.0


@pytest.mark.asyncio
async def test_extraction_coverage(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    from memento.provider import NeuroGraphProvider

    db_path = str(tmp_path / "ext.db")
    provider = NeuroGraphProvider(db_path=db_path)
    await provider.initialize()

    await provider.add("Memory one", user_id="default")
    await provider.add("Memory two", user_id="default")
    await provider.add("Memory three", user_id="default")

    now = datetime.now().isoformat()
    conn = sqlite3.connect(db_path)

    from memento.kg_extraction import KGExtractionEngine

    mem_ids = conn.execute("SELECT id FROM memories LIMIT 2").fetchall()
    for row in mem_ids:
        conn.execute(
            "INSERT INTO kg_extraction_log (memory_id, memory_text_hash, extracted_at, entities_found, triples_found) VALUES (?, ?, ?, ?, ?)",
            (row[0], "hash", now, 2, 1),
        )
    conn.commit()
    conn.close()

    monkeypatch.undo()

    metrics = QualityMetrics(db_path=db_path)
    result = await metrics.extraction_coverage()

    assert result["total_memories"] == 3
    assert result["extracted_memories"] == 2
    assert result["with_entities"] == 2
    assert result["with_triples"] == 2
    assert result["with_errors"] == 0
    assert result["coverage_percent"] == pytest.approx(66.7, abs=0.1)


@pytest.mark.asyncio
async def test_system_health_combined(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    from memento.provider import NeuroGraphProvider

    db_path = str(tmp_path / "health.db")
    provider = NeuroGraphProvider(db_path=db_path)
    await provider.initialize()

    await provider.add("Test memory for health check", user_id="default")

    kg_db_path = str(tmp_path / "kg_health.db")
    kg = KnowledgeGraph(db_path=kg_db_path)
    kg.add_entity("TestEntity", "concept")
    kg.add_triple("TestEntity", "relates_to", "Other")
    kg.close()

    monkeypatch.undo()

    metrics = QualityMetrics(db_path=db_path, kg_db_path=kg_db_path)
    report = await metrics.system_health()

    assert "health_score" in report
    assert "memory" in report
    assert "knowledge_graph" in report
    assert "consolidation" in report
    assert "extraction" in report
    assert report["memory"]["total_memories"] == 1
    assert report["knowledge_graph"]["entities"] >= 1


@pytest.mark.asyncio
async def test_system_health_score_range(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    from memento.provider import NeuroGraphProvider

    db_path = str(tmp_path / "score.db")
    provider = NeuroGraphProvider(db_path=db_path)
    await provider.initialize()

    await provider.add("Some memory", user_id="default")

    kg_db_path = str(tmp_path / "kg_score.db")
    kg = KnowledgeGraph(db_path=kg_db_path)
    kg.add_entity("E1", "person")
    kg.close()

    monkeypatch.undo()

    metrics = QualityMetrics(db_path=db_path, kg_db_path=kg_db_path)
    report = await metrics.system_health()

    assert 0 <= report["health_score"] <= 100


@pytest.fixture
def quality_db(tmp_path):
    db_path = str(tmp_path / "test_self_eval.db")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    v001_up(conn)
    v004_up(conn)
    conn.commit()
    conn.close()
    return db_path


def _insert_memory(
    conn,
    memory_id,
    text="test memory",
    created_at=None,
    hit_count=0,
    last_accessed_at=None,
):
    now = created_at or datetime.now().isoformat()
    conn.execute(
        "INSERT INTO memories (id, user_id, text, created_at, metadata) VALUES (?, 'default', ?, ?, '{}')",
        (memory_id, text, now),
    )
    conn.execute(
        "INSERT INTO memory_meta (id, created_at, updated_at, is_deleted, hit_count, last_accessed_at) VALUES (?, ?, ?, 0, ?, ?)",
        (memory_id, now, now, hit_count, last_accessed_at),
    )
    conn.commit()


@pytest.mark.asyncio
async def test_compute_health_empty_db(quality_db):
    metrics = QualityMetrics(db_path=quality_db)
    health = await metrics.compute_memory_health()
    assert health["health_score"] == 0
    assert health["total_memories"] == 0


@pytest.mark.asyncio
async def test_compute_health_with_memories(quality_db):
    metrics = QualityMetrics(db_path=quality_db)
    conn = sqlite3.connect(quality_db)
    _insert_memory(
        conn,
        "mem-1",
        "Python API authentication flow",
        hit_count=5,
        last_accessed_at=datetime.now().isoformat(),
    )
    _insert_memory(
        conn,
        "mem-2",
        "Database migration strategy for PostgreSQL",
        hit_count=3,
        last_accessed_at=datetime.now().isoformat(),
    )
    _insert_memory(conn, "mem-3", "React component state management", hit_count=1)
    conn.close()

    health = await metrics.compute_memory_health()
    assert health["health_score"] > 0
    assert health["total_memories"] == 3
    assert health["factors"]["freshness"] > 0


@pytest.mark.asyncio
async def test_identify_stale_memories(quality_db):
    metrics = QualityMetrics(db_path=quality_db)
    old_date = (datetime.now() - timedelta(days=90)).isoformat()

    conn = sqlite3.connect(quality_db)
    _insert_memory(
        conn,
        "stale-1",
        "Old unused memory",
        created_at=old_date,
        last_accessed_at=old_date,
    )
    _insert_memory(
        conn, "fresh-1", "Fresh memory", last_accessed_at=datetime.now().isoformat()
    )
    conn.close()

    stale = await metrics.identify_stale_memories(days=60)
    stale_ids = [s["id"] for s in stale]
    assert "stale-1" in stale_ids
    assert "fresh-1" not in stale_ids


@pytest.mark.asyncio
async def test_identify_orphan_memories(quality_db):
    metrics = QualityMetrics(db_path=quality_db)

    conn = sqlite3.connect(quality_db)
    _insert_memory(conn, "orphan-1", "Never accessed memory", hit_count=0)
    _insert_memory(conn, "active-1", "Frequently accessed", hit_count=10)
    conn.close()

    orphans = await metrics.identify_orphan_memories()
    orphan_ids = [o["id"] for o in orphans]
    assert "orphan-1" in orphan_ids
    assert "active-1" not in orphan_ids


@pytest.mark.asyncio
async def test_record_evaluation(quality_db):
    metrics = QualityMetrics(db_path=quality_db)

    conn = sqlite3.connect(quality_db)
    _insert_memory(conn, "mem-eval", "Memory to evaluate")
    conn.close()

    await metrics.record_evaluation("mem-eval", 0.85, "High quality")

    conn = sqlite3.connect(quality_db)
    row = conn.execute(
        "SELECT memory_id, score, reason FROM quality_evaluations WHERE memory_id = 'mem-eval'"
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "mem-eval"
    assert abs(row[1] - 0.85) < 0.01
    assert row[2] == "High quality"


@pytest.mark.asyncio
async def test_get_quality_report_structure(quality_db):
    metrics = QualityMetrics(db_path=quality_db)

    conn = sqlite3.connect(quality_db)
    _insert_memory(conn, "mem-1", "Test memory one", hit_count=2)
    _insert_memory(conn, "mem-2", "Test memory two", hit_count=0)
    conn.close()

    report = await metrics.get_quality_report()

    assert "health_score" in report
    assert "health_factors" in report
    assert "coverage" in report
    assert "stale_memories" in report
    assert "orphan_memories" in report
    assert "total_memories" in report
    assert isinstance(report["health_score"], (int, float))
    assert isinstance(report["stale_memories"], list)
    assert isinstance(report["orphan_memories"], list)


@pytest.mark.asyncio
async def test_compute_coverage(quality_db):
    metrics = QualityMetrics(db_path=quality_db)

    conn = sqlite3.connect(quality_db)
    _insert_memory(conn, "cov-1", "Python web framework authentication patterns")
    _insert_memory(conn, "cov-2", "Database schema migration strategies")
    _insert_memory(conn, "cov-3", "Machine learning model training pipeline")
    _insert_memory(conn, "cov-4", "REST API endpoint versioning practices")
    _insert_memory(conn, "cov-5", "Container orchestration with Kubernetes")
    conn.close()

    coverage = await metrics.compute_coverage()
    assert coverage["coverage_score"] > 0
    assert coverage["total_memories"] == 5
    assert coverage["estimated_topics"] > 0
    assert len(coverage["top_terms"]) > 0
