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
        return "ALLINEAMENTO GOAL"
    monkeypatch.setattr(engine, "_generate_response", mock_gen)
    
    result = await engine.check_goal_alignment("def simple_function(): pass")
    assert "ALLINEAMENTO GOAL" in result

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
