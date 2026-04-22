import pytest
import asyncio
from memento.memory.consolidator import LLMPredictor, CognitiveConsolidator, ConsolidationResult
from memento.memory.orchestrator import MemoryOrchestrator
from memento.memory.active_inference import Prediction
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


def test_llm_predictor_dummy():
    predictor = LLMPredictor()
    pred = asyncio.run(predictor.predict("build succeeds"))
    assert isinstance(pred, Prediction)
    assert pred.confidence == 0.5
    assert pred.expected_outcome == "build succeeds"


def test_llm_predictor_fallback_on_no_client():
    predictor = LLMPredictor(llm_client=None)
    pred = asyncio.run(predictor.predict("git commit"))
    assert pred.confidence == 0.5


@pytest.mark.asyncio
async def test_consolidator_with_streaming_queue(initialized_orch):
    consolidator = CognitiveConsolidator(initialized_orch)

    await consolidator.enqueue_event("python is great", actual_outcome="python is great")
    await consolidator.enqueue_event("build succeeds", actual_outcome="build fails")

    stats_before = consolidator.get_consolidation_stats()
    assert stats_before["queue_depth"] == 2
    assert stats_before["streaming_active"] is False


@pytest.mark.asyncio
async def test_consolidator_streaming_start_stop(initialized_orch):
    consolidator = CognitiveConsolidator(initialized_orch)

    await consolidator.start_streaming()
    assert consolidator._running is True

    await consolidator.enqueue_event("test event", actual_outcome="test result")

    await asyncio.sleep(0.1)

    await consolidator.stop_streaming()
    assert consolidator._running is False


def test_consolidator_stats_include_queue_depth(initialized_orch):
    consolidator = CognitiveConsolidator(initialized_orch)
    stats = consolidator.get_consolidation_stats()
    assert "queue_depth" in stats
    assert "streaming_active" in stats


@pytest.mark.asyncio
async def test_consolidator_llm_predictor_set_client(initialized_orch):
    consolidator = CognitiveConsolidator(initialized_orch)
    assert consolidator._llm_predictor._llm is None

    consolidator.set_llm_client(None)
    assert consolidator._llm_predictor._llm is None
