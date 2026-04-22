import pytest
from memento.memory.active_inference import ActiveInferenceEngine, Prediction, PredictionResult

@pytest.mark.asyncio
async def test_no_surprise_when_expected():
    engine = ActiveInferenceEngine()
    result = await engine.evaluate(
        event="git commit -m 'fix bug'",
        actual_outcome="git commit -m 'fix bug'"
    )
    assert result.is_surprise is False
    assert result.prediction_error == 0.0

@pytest.mark.asyncio
async def test_surprise_when_different():
    engine = ActiveInferenceEngine()
    result = await engine.evaluate(
        event="build succeeds",
        actual_outcome="build fails with error"
    )
    assert result.is_surprise is True
    assert result.prediction_error > 0.5

@pytest.mark.asyncio
async def test_should_consolidate_only_on_surprise():
    engine = ActiveInferenceEngine()
    result1 = await engine.evaluate("expected", "expected")
    result2 = await engine.evaluate("expected", "different")

    assert engine.should_consolidate(result1) is False
    assert engine.should_consolidate(result2) is True

def test_prediction_error_computation():
    engine = ActiveInferenceEngine()
    error = engine._compute_prediction_error("python fastapi", "python django")
    assert 0.0 < error < 1.0

def test_stats():
    engine = ActiveInferenceEngine()
    stats = engine.get_stats()
    assert "total_events" in stats
    assert "surprise_rate" in stats
    assert "avg_prediction_error" in stats
