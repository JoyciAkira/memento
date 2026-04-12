import pytest
import os
from mempalace.integrations.mem0_provider import MemPalaceGraphProvider

def test_provider_initialization(tmp_path):
    os.environ["MEMPALACE_CONFIG_DIR"] = str(tmp_path)
    provider = MemPalaceGraphProvider()
    assert provider.kg is not None
    assert os.path.exists(provider.kg.db_path)

def test_provider_add_and_get_all(tmp_path):
    os.environ["MEMPALACE_CONFIG_DIR"] = str(tmp_path)
    provider = MemPalaceGraphProvider()
    
    # Mem0 format: edges are dicts with source, target, relationship
    edges = [
        {"source": "user", "target": "python", "relationship": "loves"},
        {"source": "user", "target": "mempalace", "relationship": "builds"}
    ]
    
    provider.add(edges)
    
    # get_all should return the exact edges
    all_edges = provider.get_all()
    assert len(all_edges) == 2
    assert any(e["source"] == "user" and e["target"] == "python" for e in all_edges)

def test_provider_search_and_delete(tmp_path):
    os.environ["MEMPALACE_CONFIG_DIR"] = str(tmp_path)
    provider = MemPalaceGraphProvider()
    
    edges = [
        {"source": "alice", "target": "bob", "relationship": "knows"},
        {"source": "alice", "target": "charlie", "relationship": "likes"}
    ]
    provider.add(edges)
    
    # Search by node
    results = provider.search("alice")
    assert len(results) == 2
    
    # Delete specific edges
    provider.delete(edges=[edges[0]])
    
    # Verify deletion (MemPalace invalidates, so it shouldn't show up in search)
    results_after = provider.search("alice")
    assert len(results_after) == 1
    assert results_after[0]["target"] == "charlie"
