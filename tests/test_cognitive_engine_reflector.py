import pytest
import os
import tempfile

@pytest.mark.asyncio
async def test_reflected_search_integration():
    from memento.provider import NeuroGraphProvider
    from memento.cognitive_engine import CognitiveEngine

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_reflect.db")
        provider = NeuroGraphProvider(db_path=db_path)
        await provider.initialize()

        await provider.add("Python is a great language for AI", user_id="default")
        await provider.add("FastAPI is a Python web framework", user_id="default")

        engine = CognitiveEngine(provider)

        result = await engine.reflected_search("python AI", limit=5)

        assert "results" in result
        assert "confidence" in result
        assert "self_healed" in result
        assert "strategy" in result
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0


def test_cognitive_engine_initializes_with_hdc():
    from memento.cognitive_engine import CognitiveEngine
    from memento.memory.hdc import HDCEncoder

    hdc = HDCEncoder(d=1000)
    engine = CognitiveEngine(provider=None, hdc_encoder=hdc)

    assert engine._hdc is not None
    assert engine._reflector is not None


def test_get_reflector_stats():
    from memento.cognitive_engine import CognitiveEngine

    engine = CognitiveEngine(provider=None)
    stats = engine.get_reflector_stats()

    assert "total_reflections" in stats
    assert "self_healed_count" in stats
    assert "current_strategy" in stats
