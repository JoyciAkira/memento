import asyncio
import json
import sqlite3

import pytest

from memento.kg_extraction import KGExtractionEngine
from memento.kg_extraction_scheduler import KGExtractionScheduler
from memento.knowledge_graph import KnowledgeGraph
from memento.provider import NeuroGraphProvider


def test_text_hash_deterministic():
    assert KGExtractionEngine._text_hash("hello") == KGExtractionEngine._text_hash("hello")
    assert KGExtractionEngine._text_hash("hello") != KGExtractionEngine._text_hash("world")


@pytest.mark.asyncio
async def test_get_unprocessed_memories_excludes_processed(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    db_path = str(tmp_path / "test.db")
    provider = NeuroGraphProvider(db_path=db_path)
    await provider.initialize()

    r1 = await provider.add("Memory one", user_id="default")
    r2 = await provider.add("Memory two", user_id="default")

    kg = KnowledgeGraph(db_path=str(tmp_path / "kg.db"))
    engine = KGExtractionEngine(db_path=db_path, kg=kg)

    unprocessed = await engine.get_unprocessed_memories()
    ids = [m["id"] for m in unprocessed]
    assert r1["id"] in ids
    assert r2["id"] in ids

    await engine._mark_processed(r1["id"], "Memory one", 1, 1)

    unprocessed2 = await engine.get_unprocessed_memories()
    ids2 = [m["id"] for m in unprocessed2]
    assert r1["id"] not in ids2
    assert r2["id"] in ids2

    kg.close()


@pytest.mark.asyncio
async def test_get_unprocessed_memories_excludes_deleted(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    db_path = str(tmp_path / "test.db")
    provider = NeuroGraphProvider(db_path=db_path)
    await provider.initialize()

    r1 = await provider.add("Active memory", user_id="default")
    r2 = await provider.add("Deleted memory", user_id="default")

    await provider.soft_delete_memory(r2["id"], delete_reason="test cleanup")

    kg = KnowledgeGraph(db_path=str(tmp_path / "kg.db"))
    engine = KGExtractionEngine(db_path=db_path, kg=kg)

    unprocessed = await engine.get_unprocessed_memories()
    ids = [m["id"] for m in unprocessed]
    assert r1["id"] in ids
    assert r2["id"] not in ids

    kg.close()


def test_parse_llm_response_valid_json():
    engine = KGExtractionEngine(db_path=":memory:", kg=None)
    raw = json.dumps({
        "extractions": [
            {
                "memory_id": "abc",
                "entities": [{"name": "Alice", "type": "person"}],
                "relations": [{"subject": "Alice", "predicate": "works_on", "object": "Project X", "confidence": 0.95}],
            }
        ]
    })
    result = engine._parse_llm_response(raw)
    assert len(result["extractions"]) == 1
    assert result["extractions"][0]["memory_id"] == "abc"


def test_parse_llm_response_with_markdown_fences():
    engine = KGExtractionEngine(db_path=":memory:", kg=None)
    raw = '```json\n{"extractions": []}\n```'
    result = engine._parse_llm_response(raw)
    assert result == {"extractions": []}


def test_parse_llm_response_invalid_json():
    engine = KGExtractionEngine(db_path=":memory:", kg=None)
    result = engine._parse_llm_response("not json at all {{{")
    assert result == {"extractions": []}


def test_apply_extraction_creates_entities_and_triples():
    kg = KnowledgeGraph(db_path=":memory:")
    engine = KGExtractionEngine(db_path=":memory:", kg=kg)

    extraction = {
        "extractions": [
            {
                "memory_id": "mem1",
                "entities": [
                    {"name": "Alice", "type": "person"},
                    {"name": "React", "type": "technology"},
                ],
                "relations": [
                    {"subject": "Alice", "predicate": "uses", "object": "React", "confidence": 0.95},
                ],
            }
        ]
    }
    counts = engine._apply_extraction(extraction)
    assert counts["entities"] == 2
    assert counts["triples"] == 1

    kg.close()


def test_apply_extraction_empty_extractions():
    kg = KnowledgeGraph(db_path=":memory:")
    engine = KGExtractionEngine(db_path=":memory:", kg=kg)

    counts = engine._apply_extraction({"extractions": []})
    assert counts["entities"] == 0
    assert counts["triples"] == 0

    kg.close()


@pytest.mark.asyncio
async def test_mark_processed_records_stats(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    db_path = str(tmp_path / "test.db")
    provider = NeuroGraphProvider(db_path=db_path)
    await provider.initialize()

    r = await provider.add("Test memory", user_id="default")

    kg = KnowledgeGraph(db_path=str(tmp_path / "kg.db"))
    engine = KGExtractionEngine(db_path=db_path, kg=kg)
    await engine._mark_processed(r["id"], "Test memory", 3, 2)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM kg_extraction_log WHERE memory_id = ?", (r["id"],)).fetchone()
    assert row is not None
    assert row["entities_found"] == 3
    assert row["triples_found"] == 2
    assert row["extraction_error"] is None
    conn.close()
    kg.close()


@pytest.mark.asyncio
async def test_scheduler_start_stop():
    call_count = 0

    async def mock_extract():
        nonlocal call_count
        call_count += 1
        return {"processed": 0, "entities": 0, "triples": 0, "batches": 0}

    scheduler = KGExtractionScheduler(
        extraction_fn=mock_extract,
        interval_minutes=0.001,
        initial_delay_minutes=0.001,
    )
    assert not scheduler.is_running

    scheduler.start()
    assert scheduler.is_running

    await asyncio.sleep(0.3)
    assert call_count > 0

    scheduler.stop()
    assert not scheduler.is_running


@pytest.mark.asyncio
async def test_scheduler_no_double_start():
    async def noop():
        return {}

    scheduler = KGExtractionScheduler(extraction_fn=noop)
    scheduler.start()
    assert scheduler.is_running

    scheduler.start()
    assert scheduler.is_running

    scheduler.stop()


@pytest.mark.asyncio
async def test_extraction_log_table_created(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    db_path = str(tmp_path / "mig.db")
    provider = NeuroGraphProvider(db_path=db_path)
    await provider.initialize()

    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='kg_extraction_log'"
    )
    assert cursor.fetchone() is not None
    conn.close()
