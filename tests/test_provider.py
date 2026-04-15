import os
import tempfile
from unittest.mock import patch
from memento.provider import MementoGraphProvider

def test_provider_initialization(tmp_path):
    os.environ["MEMENTO_DIR"] = str(tmp_path)
    provider = MementoGraphProvider()
    assert provider.kg is not None
    assert os.path.exists(provider.kg.db_path)

def test_provider_add_and_get_all(tmp_path):
    os.environ["MEMENTO_DIR"] = str(tmp_path)
    provider = MementoGraphProvider()
    
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
    os.environ["MEMENTO_DIR"] = str(tmp_path)
    provider = MementoGraphProvider()
    
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


import pytest

@pytest.mark.asyncio
async def test_neurograph_search_with_filters():
    from memento.provider import NeuroGraphProvider
    with tempfile.TemporaryDirectory() as ws:
        with patch.dict(os.environ, {"MEMENTO_DIR": ws}):
            p = NeuroGraphProvider()
            await p.add("Test memory 1", metadata={"module": "backend", "type": "config"})
            await p.add("Test memory 2", metadata={"module": "frontend"})
            
            # Search without filters
            res = await p.search("Test")
            assert len(res) == 2
            
            # Search with filters
            res_backend = await p.search("Test", filters={"module": "backend"})
            assert len(res_backend) == 1
            assert "memory 1" in res_backend[0]["memory"]
            
            res_frontend = await p.search("Test", filters={"module": "frontend"})
            assert len(res_frontend) == 1
            assert "memory 2" in res_frontend[0]["memory"]

@pytest.mark.asyncio
async def test_neurograph_add_injects_workspace_metadata():
    from memento.provider import NeuroGraphProvider

    with tempfile.TemporaryDirectory() as ws:
        with patch.dict(os.environ, {"MEMENTO_DIR": ws}):
            p = NeuroGraphProvider()
            await p.add("hello", metadata={})

            import sqlite3

            conn = sqlite3.connect(p.db_path)
            row = conn.execute(
                "SELECT metadata FROM memories ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            conn.close()

            assert row is not None
            assert "workspace_root" in row[0]
            assert os.path.basename(ws) in row[0]
