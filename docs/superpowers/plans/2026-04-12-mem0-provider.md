# Mem0 Integration: MemPalace Graph Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a world-class, official `mempalace` Graph Provider for the `mem0ai/mem0` framework, allowing any AI agent in the world to use MemPalace's local, free, PageRank-optimized SQLite knowledge graph instead of expensive cloud solutions like Neo4j.

**Architecture:** We will build a bridge module `mempalace.integrations.mem0_provider`. It will implement the standard `GraphStore` interface expected by Mem0 (`add`, `search`, `delete`, `get_all`), translating Mem0's generic graph queries into our highly optimized temporal SQLite backend.

**Tech Stack:** Python, SQLite, Mem0 (`mem0ai` package interface), M**Tech Stack:** Python, SQLite, Mem0 (`mem0ai`etup Integration Module and Dependencies

**Files:**
- Create: `mempalace/integrations/__init__.py`
- Create: `mempalace/integrations/mem0_provider.py`
- Test: `tests/integrations/test_mem0_provider.py`

- [ ] **Step 1: Write the failing test for initialization**
Create `tests/integrations/test_mem0_provider.py`:
```python
import pytest
import os
from mempalace.integrations.mem0_provider import MemPalaceGraphProvider

def test_provider_initialization(tmp_path):
    os.environ["MEMPALACE_CONFIG_DIR"] = str(tmp_path)
    provider = MemPalaceGraphProvider()
    assert provider.kg is not None
    assert os.path.exists(provider.kg.db_path)
```

- [ ] **Step 2: Run test to verify it fails**
Run: `python3 -m pytest tests/integrations/test_mem0_provider.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**
Create `mempalace/integrations/__init__.py`:
```python
"""Integrations with external frameworks like Mem0."""
```

Create `mempalace/integrations/mem0_provider.py`:
```python
import logging
from typing import List, Dict, Any, Optional
from mempalace.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

class MemPalaceGraphProvider:
    """
    A GraphStore provider for mem0ai that uses MemPalace's local SQLite KnowledgeGraph.
    This allows Mem0 to use a local, zero-cost, PageRank-optimized graph database.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        db_path = self.config.get("db_path")
        self.kg = KnowledgeGraph(db_path=db_path)
        logger.info(f"Initialized MemPalaceGraphProvider at {self.kg.db_path}")
```

- [ ] **Step 4: Run test to verify it passes**
Run: `python3 -m pytest tests/integrations/test_mem0_provider.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add mempalace/integrations/ tests/integrations/
git commit -m "feat(mem0): initialize MemPalaceGraphProvider module"
```

---

### Task 2: Implement Mem0 `add` and `get_all` Interfaces

**Files:**
- Modify: `mempalace/integrations/mem0_provider.py`
- Modify: `tests/integrations/test_mem0_provider.py`

- [ ] **Step 1: Write failing tests for add and get_all**
Append to `tests/integrations/test_mem0_provider.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**
Run: `python3 -m pytest tests/integrations/test_mem0_provider.py::test_provider_add_and_get_all -v`
Expected: FAIL (AttributeError: 'MemPalaceGraphProvider' object has no attribute 'add')

- [ ] **Step 3: Implement add and get_all**
Append to `MemPalaceGraphProvider` in `mempalace/integrations/mem0_provider.py`:
```python
    def add(self, edges: List[Dict[str, Any]], **kwargs) -> None:
        """Add edges to the graph. Expected Mem0 format: [{'source': 'A', 'target': 'B', 'relationship': 'R'}]"""
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            relationship = edge.get("relationship")
            
            if not all([source, target, relationship]):
                logger.warning(f"Skipping invalid edge: {edge}")
                continue
                
            self.kg.add_triple(
                subject=source,
                predicate=relationship,
                obj=target,
                source_file="mem0_integration"
            )
            
    def get_all(self, **kwargs) -> List[Dict[str, Any]]:
        """Get all edges in Mem0 format."""
        triples = self.kg.timeline()
        # Convert back to Mem0 format
        mem0_edges = []
        for t in triples:
            if t["current"]: # Only return currently valid facts
                mem0_edges.append({
                    "source": t["subject"],
                    "relationship": t["predicate"],
                    "target": t["object"]
                })
        return mem0_edges
```

- [ ] **Step 4: Run test to verify it passes**
Run: `python3 -m pytest tests/integrations/test_mem0_provider.py::test_provider_add_and_get_all -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add mempalace/integrations/mem0_provider.py tests/integrations/test_mem0_provider.py
git commit -m "feat(mem0): implement add and get_all interfaces"
```

---

### Task 3: Implement Mem0 `search` and `delete` Interfaces

**Files:**
- Modify: `mempalace/integrations/mem0_provider.py`
- Modify: `tests/integrations/test_mem0_provider.py`

- [ ] **Step 1: Write failing tests for search and delete**
Append to `tests/integrations/test_mem0_provider.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**
Run: `python3 -m pytest tests/integrations/test_mem0_provider.py::test_provider_search_and_delete -v`
Expected: FAIL (AttributeError)

- [ ] **Step 3: Implement search and delete**
Append to `MemPalaceGraphProvider` in `mempalace/integrations/mem0_provider.py`:
```python
    def search(self, query: str, limit: int = 100, **kwargs) -> List[Dict[str, Any]]:
        """Search for edges related to a node (query string)."""
        # MemPalace's query_entity gets all relationships for a node
        results = self.kg.query_entity(query, direction="both")
        
        mem0_edges = []
        for r in results:
            if not r["current"]:
                continue
                
            # Convert MemPalace direction format to Mem0 source/target
            if r["direction"] == "outgoing":
                mem0_edges.append({
                    "source": r["subject"],
                    "relationship": r["predicate"],
                    "target": r["object"]
                })
            else: # incoming
                mem0_edges.append({
                    "source": r["subject"],
                    "relationship": r["predicate"],
                    "target": r["object"]
                })
                
        return mem0_edges[:limit]

    def delete(self, edges: List[Dict[str, Any]], **kwargs) -> None:
        """Delete specific edges (in MemPalace this means invalidating them)."""
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            relationship = edge.get("relationship")
            
            if source and target and relationship:
                self.kg.invalidate(subject=source, predicate=relationship, obj=target)
```

- [ ] **Step 4: Run test to verify it passes**
Run: `python3 -m pytest tests/integrations/test_mem0_provider.py::test_provider_search_and_delete -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add mempalace/integrations/mem0_provider.py tests/integrations/test_mem0_provider.py
git commit -m "feat(mem0): implement search and delete interfaces"
```

