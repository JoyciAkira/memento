"""Model inheritance for cognitive features.

MCP does not expose the host agent's model, so Memento reads it from the
environment shared with the agent: an explicit Memento override wins, then the
agent-wide model, then the legacy Mem0 variable, then the default.
"""


def _clear_model_env(monkeypatch):
    for var in ("MEMENTO_MODEL", "OPENAI_MODEL", "MEM0_MODEL"):
        monkeypatch.delenv(var, raising=False)


def test_model_precedence(monkeypatch):
    _clear_model_env(monkeypatch)

    from memento.llm_client import DEFAULT_MODEL, get_model_name

    assert get_model_name() == DEFAULT_MODEL == "openai/gpt-4o-mini"

    monkeypatch.setenv("MEM0_MODEL", "legacy/model")
    assert get_model_name() == "legacy/model"

    monkeypatch.setenv("OPENAI_MODEL", "agent/model")
    assert get_model_name() == "agent/model"

    monkeypatch.setenv("MEMENTO_MODEL", "memento/model")
    assert get_model_name() == "memento/model"


def test_llm_predictor_and_consolidator_inherit_model(monkeypatch):
    _clear_model_env(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", "agent/model")

    from memento.memory.consolidator import CognitiveConsolidator, LLMPredictor

    assert LLMPredictor()._model == "agent/model"

    consolidator = CognitiveConsolidator(object())
    assert consolidator._llm_predictor._model == "agent/model"

    consolidator.set_llm_client(None, model="explicit/model")
    assert consolidator._llm_predictor._model == "explicit/model"


def test_engine_passes_its_model_to_consolidator(monkeypatch):
    _clear_model_env(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", "agent/model")

    from memento.cognitive_engine import CognitiveEngine

    engine = CognitiveEngine(provider=object())
    consolidator = engine.get_consolidator(object())
    assert consolidator._llm_predictor._model == "agent/model"
