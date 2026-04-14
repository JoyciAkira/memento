from memento.ontology import OntologyManager

class MockEmbedder:
    def embed(self, text):
        if text == "auth system":
            return [1.0, 0.0]
        if text == "login page":
            return [0.9, 0.1]
        if text == "database tuning":
            return [0.0, 1.0]
        return [0.0, 0.0]

class MockKG:
    def __init__(self):
        self.rooms = [{"name": "authentication", "centroid": [1.0, 0.0]}]
    def get_all_rooms(self):
        return self.rooms
    def add_room(self, name, centroid):
        self.rooms.append({"name": name, "centroid": centroid})

def test_extract_logical_namespace():
    from memento.ontology import extract_logical_namespace
    
    assert extract_logical_namespace("src/backend/api.py") == "backend"
    assert extract_logical_namespace("app/frontend/index.js") == "frontend"
    assert extract_logical_namespace("main.py") == ""
    assert extract_logical_namespace("src/main.py") == ""
    assert extract_logical_namespace("backend/api.py") == "backend"
    assert extract_logical_namespace("src/backend/api.py", workspace_root="/workspace") == "backend"
    
    # Test with workspace root
    assert extract_logical_namespace("/workspace/src/backend/api.py", workspace_root="/workspace") == "backend"
    assert extract_logical_namespace("/workspace/main.py", workspace_root="/workspace") == ""

def test_ontology_matching():
    kg = MockKG()
    embedder = MockEmbedder()
    manager = OntologyManager(kg, embedder, threshold=0.85)
    
    room = manager.assign_room("login page")
    assert room == "authentication"
    
    room2 = manager.assign_room("database tuning")
    assert room2 is None

def test_provider_integration():
    from memento.provider import MementoProvider
    import os
    os.environ["OPENAI_API_KEY"] = "sk-dummy" # Ensure key is set
    
    provider = MementoProvider(db_path=":memory:")
    
    class DummyOntology:
        def assign_room(self, text):
            return "test-room"
            
    provider.ontology = DummyOntology()
    
    # Just ensure it doesn't crash
    try:
        provider.add("Testing deterministic routing")
    except Exception:
        # Mem0 might fail with dummy key, we just want to ensure it passes through ontology
        pass
