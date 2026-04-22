import pytest
from memento.memory.consolidator import CognitiveConsolidator, ConsolidationResult
from memento.migrations.runner import MigrationRunner
from memento.migrations.versions import get_all_migrations

@pytest.fixture
def initialized_orch(tmp_path):
    import sqlite3, os
    from memento.memory.orchestrator import MemoryOrchestrator

    db_path = str(tmp_path / "consolidate.db")
    runner = MigrationRunner(db_path)
    for version, name, fn in get_all_migrations():
        runner.register(version, name, fn)
    runner.run()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    orch = MemoryOrchestrator(conn)
    yield orch
    conn.close()


@pytest.mark.asyncio
async def test_consolidator_predict_only(initialized_orch):
    consolidator = CognitiveConsolidator(initialized_orch)
    result = await consolidator.process_event("git commit -m 'fix bug'")
    assert result.was_surprising is False
    assert result.memory_id == ""


@pytest.mark.asyncio
async def test_consolidator_evaluates_and_consolidates_on_surprise(initialized_orch):
    consolidator = CognitiveConsolidator(initialized_orch)
    result = await consolidator.process_event(
        event="build succeeds",
        actual_outcome="build fails completely"
    )
    assert result.was_surprising is True
    assert result.tier == "semantic"
    assert result.memory_id != ""
    assert result.prediction_error > 0.5


@pytest.mark.asyncio
async def test_consolidator_batch_process(initialized_orch):
    consolidator = CognitiveConsolidator(initialized_orch)
    events = [
        {"event": "git status", "actual": "git status"},
        {"event": "python is great for AI", "actual": "rust is systems programming"},
    ]
    results = await consolidator.batch_process(events)
    assert len(results) == 2
    assert results[0].was_surprising is False
    assert results[1].was_surprising is True


def test_consolidator_stats(initialized_orch):
    consolidator = CognitiveConsolidator(initialized_orch)
    stats = consolidator.get_consolidation_stats()
    assert "total_processed" in stats
    assert "stored_to_semantic" in stats
    assert "recent_events" in stats
