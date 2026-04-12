# Cognition Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform MemPalace into a proactive cognitive engine with async REM cycles, semantic wormholes, evolution tracking, ambient awareness, and topological self-reflection, maintaining local-first and zero-dependency principles.

**Architecture:** 
1. `rem_cycle.py` runs asynchronously via `hooks_cli.py` to find semantic wormholes (>0.92 similarity) and log them in SQLite.
2. `knowledge_graph.py` and `palace_graph.py` are extended to support and traverse these new meta-edges.
3. `topology.py` implements pure-Python PageRank and Betweenness Centrality to find Eigen-Thoughts and Structural Holes.
4. `ambient.py` exposes fast, single-shot context retrieval for IDE integrations.

**Tech Stack:** Python 3, SQLite (built-in), ChromaDB. No new dependencies.

---

### Task 1: Knowledge Graph Extensions for Meta-Triples

**Files:**
- Modify: `mempalace/knowledge_graph.py`
- Modify: `tests/test_knowledge_graph.py`

- [ ] **Step 1: Write the failing test for `add_bridge` and `evolve_fact`**

```python
def test_meta_triples(tmp_path):
    from mempalace.knowledge_graph import KnowledgeGraph
    kg = KnowledgeGraph(db_path=str(tmp_path / "kg.db"))
    
    # Test wormhole bridge
    bid = kg.add_bridge("room_a", "room_b", score=0.95, reason="similar text")
    assert bid is not None
    res = kg.query_relationship("semantically_bridges")
    assert len(res) == 1
    assert res[0]["subject"] == "room_a"
    assert res[0]["object"] == "room_b"

    # Test evolution
    t1 = kg.add_triple("Max", "loves", "apples")
    t2 = kg.add_triple("Max", "hates", "apples")
    kg.evolve_fact(t1, t2, reason="taste changed")
    
    # t1 should be invalid, evolved_into should exist
    timeline = kg.timeline("Max")
    evolutions = [t for t in timeline if t["predicate"] == "evolved_into"]
    assert len(evolutions) == 1
    kg.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_knowledge_graph.py -k test_meta_triples -v`
Expected: FAIL with `AttributeError: 'KnowledgeGraph' object has no attribute 'add_bridge'`

- [ ] **Step 3: Implement `add_bridge` and `evolve_fact`**

In `mempalace/knowledge_graph.py`, add to `KnowledgeGraph` class:

```python
    def add_bridge(self, room_a: str, room_b: str, score: float, reason: str = ""):
        """Create a semantic wormhole between two rooms."""
        props = {"score": score, "reason": reason}
        self.add_entity(room_a, "room")
        self.add_entity(room_b, "room")
        # Store score as confidence
        return self.add_triple(room_a, "semantically_bridges", room_b, confidence=score)

    def evolve_fact(self, old_triple_id: str, new_triple_id: str, reason: str = ""):
        """Mark an old fact as evolved into a new fact."""
        conn = self._conn()
        with conn:
            # Invalidate old triple
            ended = datetime.now().isoformat()
            conn.execute("UPDATE triples SET valid_to=? WHERE id=?", (ended, old_triple_id))
            
            # Create meta-entity for triples to link them
            self.add_entity(old_triple_id, "fact")
            self.add_entity(new_triple_id, "fact")
            self.add_triple(old_triple_id, "evolved_into", new_triple_id, source_file=reason)
```
*(Make sure to import `datetime` if not already imported).*

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_knowledge_graph.py -k test_meta_triples -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mempalace/knowledge_graph.py tests/test_knowledge_graph.py
git commit -m "feat(kg): add support for semantic bridges and fact evolution"
```

### Task 2: The REM Cycle Engine

**Files:**
- Create: `mempalace/rem_cycle.py`
- Create: `tests/test_rem_cycle.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from unittest.mock import MagicMock, patch

def test_rem_cycle_wormholes():
    from mempalace.rem_cycle import run_rem_cycle
    
    # Mock ChromaDB and KG
    mock_col = MagicMock()
    mock_kg = MagicMock()
    
    # Simulate 2 recent drawers
    mock_col.get.return_value = {
        "ids": ["d1", "d2"],
        "documents": ["doc1", "doc2"],
        "metadatas": [{"room": "room_a", "wing": "w1"}, {"room": "room_c", "wing": "w2"}]
    }
    
    # Simulate query results (finding a wormhole for d1)
    mock_col.query.side_effect = [
        {
            "documents": [["similar_doc"]],
            "metadatas": [[{"room": "room_b", "wing": "w3"}]],
            "distances": [[0.05]] # highly similar!
        },
        {
            "documents": [["unrelated_doc"]],
            "metadatas": [[{"room": "room_d", "wing": "w4"}]],
            "distances": [[0.8]] # not similar
        }
    ]
    
    run_rem_cycle(mock_col, mock_kg, limit=2, threshold=0.08)
    
    # Should have added one bridge between room_a and room_b
    mock_kg.add_bridge.assert_called_once_with("room_a", "room_b", score=0.95, reason="doc1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_rem_cycle.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mempalace.rem_cycle'`

- [ ] **Step 3: Implement `run_rem_cycle`**

Create `mempalace/rem_cycle.py`:

```python
"""
rem_cycle.py — Proactive memory consolidation for MemPalace.
Finds semantic wormholes and structural holes in the background.
"""
import logging
from .palace import get_collection
from .knowledge_graph import KnowledgeGraph
from .config import MempalaceConfig

logger = logging.getLogger("mempalace_rem")

def run_rem_cycle(col=None, kg=None, limit=50, threshold=0.08):
    """Scan recent entries and find deep semantic connections."""
    if col is None:
        config = MempalaceConfig()
        col = get_collection(config.palace_path, config.collection_name)
    if kg is None:
        kg = KnowledgeGraph()
        
    try:
        # Get latest N drawers (ChromaDB doesn't sort by time natively without metadata, 
        # but we can get the tail or just sample. For now, get last N items)
        total = col.count()
        if total == 0:
            return
            
        offset = max(0, total - limit)
        recent = col.get(limit=limit, offset=offset, include=["documents", "metadatas"])
        
        for i, doc in enumerate(recent["documents"]):
            meta = recent["metadatas"][i]
            room_a = meta.get("room")
            if not room_a or room_a == "general":
                continue
                
            # Query for similar items
            results = col.query(
                query_texts=[doc],
                n_results=3,
                include=["documents", "metadatas", "distances"]
            )
            
            for j, dist in enumerate(results["distances"][0]):
                if dist < threshold: # Distance < 0.08 means highly similar
                    match_meta = results["metadatas"][0][j]
                    room_b = match_meta.get("room")
                    if room_b and room_b != room_a and room_b != "general":
                        score = round(1 - dist, 3)
                        kg.add_bridge(room_a, room_b, score=score, reason=doc)
                        logger.info(f"WORMHOLE OPENED: {room_a} <-> {room_b} ({score})")
                        
    except Exception as e:
        logger.error(f"REM Cycle failed: {e}")
    finally:
        if hasattr(kg, 'close'):
            kg.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_rem_cycle()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_rem_cycle.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mempalace/rem_cycle.py tests/test_rem_cycle.py
git commit -m "feat(rem): add background REM cycle for wormhole detection"
```

### Task 3: Async Hook Integration

**Files:**
- Modify: `mempalace/hooks_cli.py`

- [ ] **Step 1: Write the failing test**

(Integration test for subprocess is tricky, we'll test the trigger method). Add to `tests/test_hooks_cli.py` (create if needed):

```python
from unittest.mock import patch
from mempalace.hooks_cli import trigger_rem_cycle_async

@patch("subprocess.Popen")
def test_trigger_rem_cycle(mock_popen):
    trigger_rem_cycle_async()
    mock_popen.assert_called_once()
    args = mock_popen.call_args[0][0]
    assert "rem_cycle" in " ".join(args)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_hooks_cli.py -v`
Expected: FAIL `ImportError: cannot import name 'trigger_rem_cycle_async'`

- [ ] **Step 3: Implement Async Trigger**

In `mempalace/hooks_cli.py`, add imports and the function:

```python
import sys
import subprocess

def trigger_rem_cycle_async():
    """Spawn the REM cycle in the background without blocking."""
    try:
        # Run module as script in detached process
        subprocess.Popen(
            [sys.executable, "-m", "mempalace.rem_cycle"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True # Detach from parent (Unix) or use creationflags (Windows)
        )
    except Exception:
        pass # Fail silently, it's a background optimization
```

Then, hook it into the end of the `post_save` or `install` hook wherever mining is completed. Find the `run_hooks` or `execute_post_save` function in `mempalace/hooks_cli.py` and call `trigger_rem_cycle_async()` at the very end of successful runs.

*(Note: If `hooks_cli.py` structure varies, just append it to the main CLI success paths in `cli.py` for `mine` command as well).*

Modify `mempalace/cli.py` under the `mine` command to call it:
```python
from .hooks_cli import trigger_rem_cycle_async
# inside mine() after successful mining:
trigger_rem_cycle_async()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_hooks_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mempalace/hooks_cli.py mempalace/cli.py tests/test_hooks_cli.py
git commit -m "feat(rem): trigger REM cycle asynchronously after mining"
```

### Task 4: Topology & Eigen-Thoughts

**Files:**
- Create: `mempalace/topology.py`
- Create: `tests/test_topology.py`

- [ ] **Step 1: Write the failing test**

```python
def test_eigen_thoughts():
    from mempalace.topology import calculate_pagerank, find_structural_holes
    
    # Simple graph: A-B, B-C, C-A (triangle), and D connected only to C
    nodes = ["A", "B", "C", "D"]
    edges = [("A", "B"), ("B", "C"), ("C", "A"), ("C", "D")]
    
    pr = calculate_pagerank(nodes, edges, iterations=10)
    # C should have highest rank
    assert pr["C"] > pr["D"]
    assert pr["C"] > pr["A"]
    
    holes = find_structural_holes(nodes, edges)
    # C is the broker (structural hole filler)
    assert holes[0] == "C"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_topology.py -v`
Expected: FAIL `ModuleNotFoundError: No module named 'mempalace.topology'`

- [ ] **Step 3: Implement Graph Algorithms (Zero Deps)**

Create `mempalace/topology.py`:

```python
"""
topology.py — Graph analysis for Eigen-Thoughts and Structural Holes.
Pure Python implementations (no NetworkX required).
"""
from collections import defaultdict

def calculate_pagerank(nodes, edges, iterations=20, damping=0.85):
    """Calculate Eigen-Thoughts (PageRank) of nodes."""
    if not nodes:
        return {}
        
    adj = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u) # undirected for our use case
        
    n = len(nodes)
    pr = {node: 1.0 / n for node in nodes}
    
    for _ in range(iterations):
        new_pr = {}
        for node in nodes:
            rank_sum = 0
            for neighbor in adj[node]:
                if len(adj[neighbor]) > 0:
                    rank_sum += pr[neighbor] / len(adj[neighbor])
            new_pr[node] = (1 - damping) / n + damping * rank_sum
        pr = new_pr
        
    return pr

def find_structural_holes(nodes, edges):
    """Find brokers (nodes that bridge otherwise disconnected clusters).
    Using a simplified betweenness centrality approximation."""
    adj = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)
        
    betweenness = {node: 0.0 for node in nodes}
    
    # Very simplified: count shortest paths of length 2 that pass through node
    # A node is a broker if it connects two nodes that aren't connected to each other
    for node in nodes:
        neighbors = adj[node]
        for i in range(len(neighbors)):
            for j in range(i+1, len(neighbors)):
                n1, n2 = neighbors[i], neighbors[j]
                if n2 not in adj[n1]: # hole found!
                    betweenness[node] += 1.0
                    
    # Sort by score descending
    sorted_nodes = sorted(betweenness.items(), key=lambda x: -x[1])
    return [n for n, score in sorted_nodes if score > 0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_topology.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mempalace/topology.py tests/test_topology.py
git commit -m "feat(cognition): pure python topology algorithms for eigen-thoughts"
```

### Task 5: Ambient RAG & CLI Integration

**Files:**
- Modify: `mempalace/cli.py`
- Create: `mempalace/ambient.py`
- Modify: `mempalace/mcp_server.py`

- [ ] **Step 1: Write the failing test**

```python
from mempalace.ambient import get_whisper, get_socratic_question
from unittest.mock import patch, MagicMock

@patch("mempalace.ambient.get_collection")
def test_ambient_whisper(mock_get_col):
    mock_col = MagicMock()
    mock_get_col.return_value = mock_col
    
    mock_col.query.return_value = {
        "documents": [["Historical wisdom"]],
        "metadatas": [[{"room": "wisdom", "wing": "past"}]],
        "distances": [[0.05]]
    }
    
    res = get_whisper("I am coding something")
    assert "Historical wisdom" in res
    assert "wisdom" in res

def test_socratic_question():
    mock_kg = MagicMock()
    # Mock some triples to form a graph
    mock_kg._conn().execute().fetchall.return_value = [
        {"subject": "A", "object": "B"},
        {"subject": "B", "object": "C"}
    ]
    with patch("mempalace.ambient.KnowledgeGraph", return_value=mock_kg):
        with patch("mempalace.topology.find_structural_holes", return_value=["B"]):
            q = get_socratic_question()
            assert "B" in q
```
*(Add to `tests/test_ambient.py`)*

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ambient.py -v`
Expected: FAIL `ModuleNotFoundError: No module named 'mempalace.ambient'`

- [ ] **Step 3: Implement `ambient.py` and update CLI**

Create `mempalace/ambient.py`:

```python
"""ambient.py — Onnipervasività for MemPalace."""
from .palace import get_collection
from .config import MempalaceConfig
from .knowledge_graph import KnowledgeGraph
from .topology import find_structural_holes, calculate_pagerank

def get_whisper(context: str, threshold: float = 0.15) -> str:
    """Get a highly relevant historical context whisper based on current text."""
    config = MempalaceConfig()
    col = get_collection(config.palace_path, config.collection_name)
    if not col:
        return ""
        
    try:
        res = col.query(query_texts=[context], n_results=1, include=["documents", "metadatas", "distances"])
        if res["distances"][0] and res["distances"][0][0] < threshold:
            doc = res["documents"][0][0]
            room = res["metadatas"][0][0].get("room", "unknown")
            return f"[Whisper from {room}]: {doc[:200]}..."
    except Exception:
        pass
    return ""

def get_socratic_question() -> str:
    """Generate a question based on structural holes in the knowledge graph."""
    kg = KnowledgeGraph()
    conn = kg._conn()
    
    # Get all room edges from graph and wormholes
    edges = []
    nodes = set()
    rows = conn.execute("SELECT subject, object FROM triples WHERE predicate = 'semantically_bridges'").fetchall()
    for r in rows:
        edges.append((r["subject"], r["object"]))
        nodes.add(r["subject"])
        nodes.add(r["object"])
        
    if not nodes:
        return "Not enough data to ask a socratic question yet. Keep building your palace."
        
    holes = find_structural_holes(list(nodes), edges)
    if holes:
        broker = holes[0]
        return f"Socratic Question: You often bridge ideas through '{broker}'. Have you considered exploring what connects its disparate neighbors directly?"
        
    return "Your palace is highly interconnected. What new domain can you explore today?"
    
def get_eigen_thoughts() -> list:
    """Return top 5 core pillars of the user's mind."""
    kg = KnowledgeGraph()
    conn = kg._conn()
    edges = [(r["subject"], r["object"]) for r in conn.execute("SELECT subject, object FROM triples").fetchall()]
    nodes = list(set([u for u,v in edges] + [v for u,v in edges]))
    
    pr = calculate_pagerank(nodes, edges)
    sorted_pr = sorted(pr.items(), key=lambda x: -x[1])
    return [n for n, score in sorted_pr[:5]]
```

In `mempalace/cli.py`, add new commands:
```python
from .ambient import get_whisper, get_socratic_question, get_eigen_thoughts

# inside cli main parser logic:
if args.command == "whisper":
    print(get_whisper(" ".join(args.text)))
elif args.command == "socratic":
    print(get_socratic_question())
elif args.command == "pillars":
    print("\nYour Eigen-Thoughts (Core Pillars):")
    for i, t in enumerate(get_eigen_thoughts(), 1):
        print(f"  {i}. {t}")
```

Add to `mempalace/mcp_server.py`:
Expose `get_socratic_question` and `get_eigen_thoughts` as new MCP tools.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ambient.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mempalace/ambient.py mempalace/cli.py mempalace/mcp_server.py tests/test_ambient.py
git commit -m "feat(ambient): add ambient whispers, socratic questions, and eigen-thoughts"
```
