import pytest
from memento.cognitive_engine import CognitiveEngine

class MockProvider:
    async def search(self, query):
        return {"results": [
            {"memory": "BUG: Using SQLite for high-concurrency caused deadlocks.", "score": 0.9}
        ]}

def test_engine_independent_llm():
    from memento.provider import NeuroGraphProvider
    from memento.cognitive_engine import CognitiveEngine
    import os
    os.environ["OPENAI_API_KEY"] = "sk-dummy"
    
    provider = NeuroGraphProvider(db_path=":memory:")
    engine = CognitiveEngine(provider)
    
    assert engine.llm is not None

@pytest.mark.asyncio
async def test_evaluate_code_for_warnings():
    provider = MockProvider()
    engine = CognitiveEngine(provider)
    
    code_snippet = "import sqlite3\ndef write_data(): db.execute('INSERT...')"
    warning = await engine.evaluate_raw_context(code_snippet)
    
    assert "BUG: Using SQLite" in warning
    assert "SPIDER-SENSE" in warning

class MockLLM:
    def generate_response(self, messages, **kwargs):
        return "Synthetic Insight: Consider using Redis based on memory X and Y."

class MockProviderWithLLM(MockProvider):
    def __init__(self):
        class MockMem0:
            llm = MockLLM()
        self.memory = MockMem0()
        
    async def search(self, query, limit=10):
        return {"results": [
            {"id": "A", "memory": "Used SQLite for project X"},
            {"id": "B", "memory": "Project X needs faster caching"}
        ]}

@pytest.mark.asyncio
async def test_synthesize_dreams(monkeypatch):
    provider = MockProviderWithLLM()
    engine = CognitiveEngine(provider)
    
    async def mock_gen(msgs):
        return "Synthetic Insight"
    monkeypatch.setattr(engine, "_generate_response", mock_gen)
    
    result = await engine.synthesize_dreams("caching")
    assert "[DRAFT_INSIGHT]" in result
    assert "Synthetic Insight" in result

@pytest.mark.asyncio
async def test_check_goal_alignment(monkeypatch):
    provider = MockProviderWithLLM()
    engine = CognitiveEngine(provider)
    
    async def mock_gen(msgs):
        return "GOAL ALIGNMENT CHECK"
    monkeypatch.setattr(engine, "_generate_response", mock_gen)
    
    result = await engine.check_goal_alignment("def simple_function(): pass")
    assert "GOAL ALIGNMENT CHECK" in result

@pytest.mark.asyncio
async def test_parse_natural_language_intent(monkeypatch):
    provider = MockProviderWithLLM()
    from memento.cognitive_engine import CognitiveEngine
    engine = CognitiveEngine(provider)
    
    async def mock_gen(msgs):
        return '{"action": "ADD", "payload": {"text": "Il server usa Nginx"}}'
    monkeypatch.setattr(engine, "_generate_response", mock_gen)
    
    result = await engine.parse_natural_language_intent("memento ricordati che il server usa Nginx")
    
    assert isinstance(result, dict)
    assert result["action"] == "ADD"
    assert result["payload"]["text"] == "Il server usa Nginx"

@pytest.mark.asyncio
async def test_parse_natural_language_intent_with_focus_area(monkeypatch):
    provider = MockProviderWithLLM()
    from memento.cognitive_engine import CognitiveEngine
    engine = CognitiveEngine(provider)
    
    async def mock_gen(msgs):
        return '{"action": "SEARCH", "payload": {"query": "bug"}, "focus_area": "frontend"}'
    monkeypatch.setattr(engine, "_generate_response", mock_gen)
    
    result = await engine.parse_natural_language_intent("memento cerca bug nel frontend")
    
    assert isinstance(result, dict)
    assert result["action"] == "SEARCH"
    assert result["payload"]["query"] == "bug"
    assert result.get("focus_area") == "frontend"


def test_prompt_registry_loads_all_prompts():
    from memento.prompts.registry import load_prompt
    for name in ["detect_latent_features", "synthesize_dreams", "check_goal_alignment", "parse_natural_language_intent"]:
        data = load_prompt(name)
        assert "system_prompt" in data
        assert "user_prompt_template" in data


def test_prompt_registry_caches():
    from memento.prompts.registry import load_prompt, clear_cache
    clear_cache()
    a = load_prompt("synthesize_dreams")
    b = load_prompt("synthesize_dreams")
    assert a is b


def test_prompt_registry_raises_on_missing():
    from memento.prompts.registry import load_prompt
    with pytest.raises(FileNotFoundError):
        load_prompt("nonexistent_prompt")
