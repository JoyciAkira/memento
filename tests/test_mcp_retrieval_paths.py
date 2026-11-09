import pytest

from benchmarks.mcp_memory_accuracy import evaluate_paths


@pytest.mark.asyncio
async def test_actual_agent_retrieval_paths_are_measured():
    report = await evaluate_paths()

    assert report["benchmark"] == "mcp_memory_accuracy"
    assert report["n_queries"] == 15
    for name in ("basic", "advanced"):
        metrics = report["paths"][name]
        assert metrics["n_queries"] == 15
        assert metrics["result_limits_ok"] is True
        assert 0.8 <= metrics["score"] <= 1.0
        assert metrics["components"]["recall_at_5"] >= 0.8
