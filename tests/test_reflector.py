import pytest
from memento.memory.reflector import MetacognitiveReflector, RetrievalResult

@pytest.mark.asyncio
async def test_evaluate_confidence_high():
    reflector = MetacognitiveReflector()
    results = [
        RetrievalResult(id="1", memory="Python is great for AI", score=0.95, tier="semantic"),
        RetrievalResult(id="2", memory="Python is great for web", score=0.93, tier="semantic"),
    ]
    conf = await reflector.evaluate_confidence(results, "python")
    assert conf >= 0.8

@pytest.mark.asyncio
async def test_evaluate_confidence_low():
    reflector = MetacognitiveReflector()
    conf = await reflector.evaluate_confidence([], "nonexistent query")
    assert conf == 0.0

@pytest.mark.asyncio
async def test_reflect_high_confidence():
    reflector = MetacognitiveReflector()
    results = [
        RetrievalResult(id="1", memory="FastAPI is a web framework", score=0.95, tier="semantic"),
    ]
    report = await reflector.reflect("FastAPI", results, confidence=0.9)
    assert report.self_healed is False
    assert report.strategy == "standard"

@pytest.mark.asyncio
async def test_reflect_low_confidence_triggers_self_healing():
    reflector = MetacognitiveReflector()
    results = [
        RetrievalResult(id="1", memory="Some vague result", score=0.3, tier="semantic"),
    ]
    report = await reflector.reflect("vague query", results, confidence=0.2)
    assert report.self_healed is True
    assert report.strategy == "self_healed"

@pytest.mark.asyncio
async def test_reflect_with_hdc_expansion():
    from memento.memory.hdc import HDCEncoder
    hdc = HDCEncoder(d=1000)
    reflector = MetacognitiveReflector(hdc_encoder=hdc)

    results = [
        RetrievalResult(id="1", memory="Python programming language", score=0.5, tier="semantic"),
    ]
    report = await reflector.reflect("python", results, confidence=0.3)
    assert report.self_healed is True
    assert "expanded" in report.strategy or report.recommendation != ""

def test_reflector_stats():
    reflector = MetacognitiveReflector()
    stats = reflector.get_stats()
    assert "total_reflections" in stats
    assert "self_healed_count" in stats
    assert "current_strategy" in stats
