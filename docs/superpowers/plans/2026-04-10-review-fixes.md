# Code Review Fixes (Cognition Engine) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Address code review feedback on the Cognition Engine PR, fixing ChromaDB self-matching, whisper thresholds, edge deduplication, and fact evolution metadata.

**Architecture:** 
1. Fix `rem_cycle.py` to filter out self-matches by ID and document random sampling.
2. Adjust `ambient.py` whisper threshold to `0.3` and move imports to top level.
3. Enhance `knowledge_graph.py` `evolve_fact` to store human-readable metadata.
4. Update `topology.py` to deduplicate edges before processing.

**Tech Stack:** Python 3, SQLite, ChromaDB.

---

### Task 1: Fix Topology Edge Deduplication

**Files:**
- Modify: `mempalace/topology.py`
- Modify: `tests/test_topology.py`

- [ ] **Step 1: Write the failing test**

Modify `tests/test_topology.py` to include duplicate edges:

```python
def test_find_structural_holes_with_duplicates():
    from mempalace.topology import find_structural_holes
    # B is the broker. We add duplicate A-B and B-C edges to simulate multiple wormholes.
    nodes = ["A", "B", "C", "D"]
    edges = [("A", "B"), ("A", "B"), ("B", "C"), ("B", "C"), ("C", "D")]
    
    holes = find_structural_holes(nodes, edges)
    
    # If not deduplicated, B's score inflates incorrectly. 
    # With deduplication, B is still the top broker but calculation doesn't crash or skew.
    assert holes[0] == "B"
    # Also verify that it doesn't fail on deduplication
    assert len(holes) >= 1
```

- [ ] **Step 2: Run test to verify it fails/passes (ensure it catches the bug if possible, or just tests the new behavior)**

Run: `python -m pytest tests/test_topology.py -k test_find_structural_holes_with_duplicates -v`

- [ ] **Step 3: Write minimal implementation**

In `mempalace/topology.py`, update `find_structural_holes` and `calculate_pagerank` to deduplicate edges:

```python
from collections import defaultdict
from typing import List, Tuple, Dict, Any

def calculate_pagerank(
    nodes: List[str], edges: List[Tuple[str, str]], iterations: int = 20, damping: float = 0.85
) -> Dict[str, float]:
    """Calculate Eigen-Thoughts (PageRank) of nodes."""
    if not nodes:
        return {}

    # Deduplicate edges
    edges = list(set(edges))

    adj = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)  # undirected for our use case
# ... rest of the function remains the same

def find_structural_holes(nodes: List[str], edges: List[Tuple[str, str]]) -> List[str]:
    """Find brokers (nodes that bridge otherwise disconnected clusters).
    Using a simplified betweenness centrality approximation."""
    
    # Deduplicate edges
    edges = list(set(edges))
    
    adj = defaultdict(list)
# ... rest of the function remains the same
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_topology.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mempalace/topology.py tests/test_topology.py
git commit -m "fix(topology): deduplicate edges before graph traversal"
```

### Task 2: Fix Ambient Whisper Threshold and Imports

**Files:**
- Modify: `mempalace/ambient.py`
- Modify: `tests/test_ambient.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_ambient.py`:
```python
@patch("mempalace.ambient.get_collection")
def test_ambient_whisper_threshold(mock_get_col):
    mock_col = MagicMock()
    mock_get_col.return_value = mock_col
    
    # Distance 0.5 is > 0.3 threshold, should be ignored
    mock_col.query.return_value = {
        "documents": [["Historical wisdom"]],
        "metadatas": [[{"room": "wisdom", "wing": "past"}]],
        "distances": [[0.5]]
    }
    
    res = get_whisper("I am coding something")
    assert "Historical wisdom" not in res
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ambient.py -k test_ambient_whisper_threshold -v`
Expected: FAIL (because default is 1.5, so 0.5 passes)

- [ ] **Step 3: Write minimal implementation**

In `mempalace/ambient.py`:
1. Move `import logging` to the top of the file.
2. Change default threshold in `get_whisper` to `0.3`.

```python
"""ambient.py — Onnipervasività for MemPalace."""
import logging
from .palace import get_collection
from .config import MempalaceConfig
from .knowledge_graph import KnowledgeGraph
from .topology import find_structural_holes, calculate_pagerank

def get_whisper(context: str, palace_path: str = None, threshold: float = 0.3) -> str:
    """Get a highly relevant historical context whisper based on current text."""
# ...
    except Exception as e:
        logging.error(f"Whisper error: {e}")
        pass
    return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ambient.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mempalace/ambient.py tests/test_ambient.py
git commit -m "fix(ambient): adjust whisper threshold to 0.3 and move imports"
```

### Task 3: Fix REM Cycle Self-Matches and Docs

**Files:**
- Modify: `mempalace/rem_cycle.py`
- Modify: `tests/test_rem_cycle.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_rem_cycle.py`:
```python
def test_rem_cycle_ignores_self_match():
    from mempalace.rem_cycle import run_rem_cycle
    
    mock_col = MagicMock()
    mock_kg = MagicMock()
    mock_col.count.return_value = 1
    
    mock_col.get.return_value = {
        "ids": ["doc_123"],
        "documents": ["My brilliant idea"],
        "metadatas": [{"room": "room_a", "wing": "w1"}]
    }
    
    # Query returns the exact same document as the best match (distance 0.0)
    # and another document as the second match
    mock_col.query.return_value = {
        "ids": [["doc_123", "doc_456"]],
        "documents": [["My brilliant idea", "Another idea"]],
        "metadatas": [[{"room": "room_a", "wing": "w1"}, {"room": "room_b", "wing": "w2"}]],
        "distances": [[0.0, 0.05]]
    }
    
    run_rem_cycle(mock_col, mock_kg, limit=1, threshold=0.08)
    
    # Should only add bridge for doc_456, NOT doc_123 (self)
    mock_kg.add_bridge.assert_called_once_with("room_a", "room_b", score=0.95, reason="My brilliant idea")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_rem_cycle.py -k test_rem_cycle_ignores_self_match -v`
Expected: FAIL (because it tries to add bridge for self)

- [ ] **Step 3: Write minimal implementation**

In `mempalace/rem_cycle.py`:

```python
def run_rem_cycle(col=None, kg=None, limit: int = 50, threshold: float = 0.08) -> None:
    """
    Scan recent entries and find deep semantic connections.
    Note: col.get() does not guarantee chronological insertion order. 
    This acts as a random/approximate sample of the collection for background processing.
    """
# ...
        offset = max(0, total - limit)
        # Fetch IDs to prevent self-matching
        recent = col.get(limit=limit, offset=offset, include=["documents", "metadatas"])
        recent_ids = recent.get("ids", [])
        
        for i, doc in enumerate(recent["documents"]):
            source_id = recent_ids[i] if i < len(recent_ids) else None
            meta = recent["metadatas"][i]
# ...
            # Request n_results=4 to account for self-match
            results = col.query(
                query_texts=[doc],
                n_results=4,
                include=["documents", "metadatas", "distances"]
            )
            
            for j, dist in enumerate(results["distances"][0]):
                match_id = results.get("ids", [[]])[0][j]
                # Skip self-match
                if source_id and match_id == source_id:
                    continue
                    
                if dist < threshold: # Distance < 0.08 means highly similar
# ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_rem_cycle.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mempalace/rem_cycle.py tests/test_rem_cycle.py
git commit -m "fix(rem): prevent wormholes to self and clarify sampling behavior"
```

### Task 4: Improve Fact Evolution Metadata

**Files:**
- Modify: `mempalace/knowledge_graph.py`
- Modify: `tests/test_knowledge_graph.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_knowledge_graph.py`:
```python
def test_evolve_fact_stores_metadata(tmp_path):
    from mempalace.knowledge_graph import KnowledgeGraph
    kg = KnowledgeGraph(db_path=str(tmp_path / "kg.db"))
    
    t1 = kg.add_triple("Max", "loves", "apples")
    t2 = kg.add_triple("Max", "hates", "apples")
    
    # Reason should be passed down
    kg.evolve_fact(t1, t2, reason="taste changed")
    
    evolutions = kg.query_relationship("evolved_into")
    assert len(evolutions) == 1
    # Check that metadata was saved
    assert "source_file" in evolutions[0]
    assert evolutions[0]["source_file"] == "taste changed"
    kg.close()
```

- [ ] **Step 2: Run test to verify it fails/passes**

Run: `python -m pytest tests/test_knowledge_graph.py -k test_evolve_fact_stores_metadata -v`

- [ ] **Step 3: Write minimal implementation**

In `mempalace/knowledge_graph.py`, update `evolve_fact` to pass the reason:

```python
    def evolve_fact(self, old_triple_id: str, new_triple_id: str, reason: str = "") -> None:
        """Mark an old fact as evolved into a new fact."""
        conn = self._conn()
        with conn:
            # Invalidate old triple
            ended = datetime.now().isoformat()
            conn.execute("UPDATE triples SET valid_to=? WHERE id=?", (ended, old_triple_id))
            
            # Create meta-entity for triples to link them
            self.add_entity(old_triple_id, "fact")
            self.add_entity(new_triple_id, "fact")
            # Store reason as source_file or metadata to make it traceable
            self.add_triple(old_triple_id, "evolved_into", new_triple_id, source_file=reason)
```
*(This actually might already be correct from the previous implementation, just confirming via test).*

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_knowledge_graph.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mempalace/knowledge_graph.py tests/test_knowledge_graph.py
git commit -m "fix(kg): ensure evolution metadata is queryable"
```
