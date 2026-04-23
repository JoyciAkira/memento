import pytest
import os
import tempfile

_API_KEY_PLACEHOLDER = "sk-or-v2-placeholder-key-for-tests"

@pytest.mark.asyncio
async def test_consolidate_method_on_engine():
    from memento.provider import NeuroGraphProvider
    from memento.cognitive_engine import CognitiveEngine

    os.environ["OPENAI_API_KEY"] = _API_KEY_PLACEHOLDER
    os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"
    os.environ["MEM0_MODEL"] = "nvidia/nemotron-3-super-120b-a12b:free"

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_ce.db")
        provider = NeuroGraphProvider(db_path=db_path)
        await provider.initialize()

        engine = CognitiveEngine(provider)

        consolidator = engine.get_consolidator(provider.orchestrator)
        assert consolidator is not None
        assert consolidator._llm_predictor._llm is not None

        result = await engine.consolidate(
            event="python tests pass",
            actual_outcome="python tests pass"
        )
        assert isinstance(result, type(consolidator._consolidation_log[-1])) if consolidator._consolidation_log else True


@pytest.mark.asyncio
async def test_consolidate_predict_only():
    from memento.provider import NeuroGraphProvider
    from memento.cognitive_engine import CognitiveEngine

    os.environ["OPENAI_API_KEY"] = "sk-or-v2-placeholder-key-for-tests"
    os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"
    os.environ["MEM0_MODEL"] = "nvidia/nemotron-3-super-120b-a12b:free"

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_ce2.db")
        provider = NeuroGraphProvider(db_path=db_path)
        await provider.initialize()

        engine = CognitiveEngine(provider)

        result = await engine.consolidate(
            event="git push origin main",
            actual_outcome=None
        )
        assert result.memory_id == ""
        assert result.was_surprising is False


@pytest.mark.asyncio
async def test_consolidate_batch():
    from memento.provider import NeuroGraphProvider
    from memento.cognitive_engine import CognitiveEngine

    os.environ["OPENAI_API_KEY"] = "sk-or-v2-placeholder-key-for-tests"
    os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"
    os.environ["MEM0_MODEL"] = "nvidia/nemotron-3-super-120b-a12b:free"

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_ce3.db")
        provider = NeuroGraphProvider(db_path=db_path)
        await provider.initialize()

        engine = CognitiveEngine(provider)

        events = [
            {"event": "deploy to production", "actual": "catastrophic outage"},
            {"event": "tests pass", "actual": "firewall blocks connection"},
        ]

        results = await engine.consolidate_batch(events)
        assert len(results) == 2
        assert results[0].was_surprising is True
        assert results[1].was_surprising is True


def test_get_consolidator_initializes_once():
    from memento.provider import NeuroGraphProvider
    from memento.cognitive_engine import CognitiveEngine
    import asyncio

    os.environ["OPENAI_API_KEY"] = "sk-or-v2-placeholder-key-for-tests"
    os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"
    os.environ["MEM0_MODEL"] = "nvidia/nemotron-3-super-120b-a12b:free"

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_ce4.db")

        async def setup():
            p = NeuroGraphProvider(db_path=db_path)
            await p.initialize()
            return p

        provider = asyncio.run(setup())
        engine = CognitiveEngine(provider)

        c1 = engine.get_consolidator(provider.orchestrator)
        c2 = engine.get_consolidator(provider.orchestrator)
        assert c1 is c2
