# Organic Archive (Cognitive Crystallization) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Solve the "hubness problem" in dense rooms (>100 drawers) by implementing a Soft-Archive lifecycle that extracts core concepts (Diamonds) using PageRank, and fades the rest into an archive, improving retrieval accuracy.

**Architecture:** 
1. `entropy.py` identifies rooms with >100 drawers and high vector density.
2. `crystallize.py` applies PageRank to the room's internal network (based on vector similarity) to find the top 5 core drawers.
3. `archive.py` moves non-core drawers into a parallel `wing_archive` (soft-archive) to reduce neighborhood radius.
4. `cli.py` adds `mempalace crystallize` to trigger this lifecycle, and extends `search` with a `--deep` flag to query archives.

**Tech Stack:** Python 3, SQLite, ChromaDB. Zero new dependencies.

---

### Task 1: Room Entropy and Hubness Detection

**Files:**
- Create: `mempalace/entropy.py`
- Create: `tests/test_entropy.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from unittest.mock import MagicMock

def test_detect_dense_rooms():
    from mempalace.entropy import detect_dense_rooms
    mock_col = MagicMock()
    
    # Simulate a collection with 2 rooms: one dense (150 items), one sparse (20 items)
    # ChromaDB get() returns metadata
    metadatas = [{"room": "ideas", "wing": "work"}] * 150 + [{"room": "todos", "wing": "work"}] * 20
    mock_col.get.return_value = {"metadatas": metadatas}
    
    dense_rooms = detect_dense_rooms(mock_col, threshold=100)
    assert len(dense_rooms) == 1
    assert dense_rooms[0] == "ideas"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_entropy.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

Create `mempalace/entropy.py`:

```python
"""
entropy.py — Detects rooms that suffer from the hubness problem.
"""
from collections import Counter
from typing import List, Any

def detect_dense_rooms(col: Any, threshold: int = 100) -> List[str]:
    """Identify rooms that exceed the drawer threshold and need crystallization."""
    if not col:
        return []
        
    try:
        # Get all metadatas to count room frequencies
        # In a real huge DB this might need pagination, but Chroma handles 10k+ easily in memory
        result = col.get(include=["metadatas"])
        metadatas = result.get("metadatas") or []
        
        room_counts = Counter()
        for meta in metadatas:
            if meta and "room" in meta:
                room_counts[meta["room"]] += 1
                
        dense = [room for room, count in room_counts.items() if count >= threshold]
        return dense
    except Exception:
        return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_entropy.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mempalace/entropy.py tests/test_entropy.py
git commit -m "feat(entropy): add detection for rooms suffering from hubness"
```

### Task 2: Intra-Room PageRank (Crystallization)

**Files:**
- Create: `mempalace/crystallize.py`
- Create: `tests/test_crystallize.py`

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import MagicMock
import pytest

def test_find_room_diamonds():
    from mempalace.crystallize import find_room_diamonds
    
    mock_col = MagicMock()
    
    # 3 documents in the room
    mock_col.get.return_value = {
        "ids": ["doc1", "doc2", "doc3"],
        "documents": ["Core idea", "Related idea", "Tangent"],
        "metadatas": [{"room": "ideas"}] * 3
    }
    
    # Mock cross-query results to build the internal graph
    # doc1 is central, doc2 is close to doc1, doc3 is far
    mock_col.query.return_value = {
        "ids": [["doc2", "doc3"], ["doc1", "doc3"], ["doc1", "doc2"]],
        "distances": [[0.1, 0.8], [0.1, 0.9], [0.8, 0.9]]
    }
    
    diamonds, noise = find_room_diamonds(mock_col, "ideas", top_k=1)
    
    assert len(diamonds) == 1
    # doc1 should be the diamond because it has the closest connections
    assert diamonds[0] == "doc1" or diamonds[0] == "doc2"
    assert len(noise) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_crystallize.py -v`

- [ ] **Step 3: Write minimal implementation**

Create `mempalace/crystallize.py`:

```python
"""
crystallize.py — Distills dense rooms into Core Pillars (Diamonds) and Noise.
"""
from typing import List, Tuple, Any
from .topology import calculate_pagerank

def find_room_diamonds(col: Any, room_name: str, top_k: int = 5) -> Tuple[List[str], List[str]]:
    """
    Find the most central documents in a room using PageRank on vector similarities.
    Returns (diamonds_ids, noise_ids).
    """
    try:
        # 1. Get all documents in the room
        result = col.get(where={"room": room_name}, include=["documents", "metadatas"])
        ids = result.get("ids", [])
        docs = result.get("documents", [])
        
        if len(ids) <= top_k:
            return ids, []
            
        # 2. Build internal similarity graph
        edges = []
        
        # Query the collection with the room's own documents
        # We query for n_results=4 (itself + top 3 neighbors)
        q_res = col.query(
            query_texts=docs,
            where={"room": room_name},
            n_results=min(4, len(ids)),
            include=["distances"]
        )
        
        for i, source_id in enumerate(ids):
            match_ids = q_res.get("ids", [])[i]
            distances = q_res.get("distances", [])[i]
            
            for j, match_id in enumerate(match_ids):
                if match_id != source_id and distances[j] < 0.3: # strong connection
                    edges.append((source_id, match_id))
                    
        # 3. Calculate PageRank
        pr = calculate_pagerank(ids, edges)
        
        # Sort by PageRank score descending
        sorted_ids = sorted(pr.items(), key=lambda x: -x[1])
        
        diamonds = [node_id for node_id, score in sorted_ids[:top_k]]
        noise = [node_id for node_id, score in sorted_ids[top_k:]]
        
        return diamonds, noise
        
    except Exception:
        return [], []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_crystallize.py -v`

- [ ] **Step 5: Commit**

```bash
git add mempalace/crystallize.py tests/test_crystallize.py
git commit -m "feat(archive): add intra-room pagerank for cognitive crystallization"
```

### Task 3: Soft-Archiving Engine

**Files:**
- Create: `mempalace/archive.py`
- Modify: `mempalace/knowledge_graph.py`
- Create: `tests/test_archive.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from unittest.mock import MagicMock

def test_soft_archive_noise():
    from mempalace.archive import archive_noise
    
    mock_col = MagicMock()
    mock_kg = MagicMock()
    
    # Mock fetching the noise documents
    mock_col.get.return_value = {
        "ids": ["doc_noise_1"],
        "documents": ["Useless detail"],
        "metadatas": [{"room": "ideas", "wing": "work"}]
    }
    
    archive_noise(mock_col, mock_kg, "ideas", ["doc_noise_1"])
    
    # Should have updated the metadata to move it to archive wing
    mock_col.update.assert_called_once()
    update_kwargs = mock_col.update.call_args[1]
    assert update_kwargs["ids"] == ["doc_noise_1"]
    assert update_kwargs["metadatas"][0]["wing"] == "archive"
    
    # Should have linked in KG
    mock_kg.add_triple.assert_called_once_with("ideas", "has_archive", "ideas_archive")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_archive.py -v`

- [ ] **Step 3: Write minimal implementation**

Modify `mempalace/knowledge_graph.py` to add a generic relation method if needed, or just use `add_triple`. 

Create `mempalace/archive.py`:

```python
"""
archive.py — Moves noise vectors to soft-archive wings to prevent hubness.
"""
from typing import List, Any
from .knowledge_graph import KnowledgeGraph

def archive_noise(col: Any, kg: KnowledgeGraph, room_name: str, noise_ids: List[str]) -> int:
    """Move noise IDs to the archive wing and link in the knowledge graph."""
    if not noise_ids:
        return 0
        
    try:
        # Fetch current data
        result = col.get(ids=noise_ids, include=["documents", "metadatas"])
        if not result or not result.get("ids"):
            return 0
            
        new_metadatas = []
        for meta in result["metadatas"]:
            new_meta = meta.copy()
            new_meta["wing"] = "archive"
            new_metadatas.append(new_meta)
            
        # Soft-archive by updating the wing metadata
        col.update(
            ids=result["ids"],
            metadatas=new_metadatas
        )
        
        # Link in KG
        kg.add_entity(room_name, "room")
        kg.add_entity(f"{room_name}_archive", "room")
        kg.add_triple(room_name, "has_archive", f"{room_name}_archive")
        
        return len(noise_ids)
    except Exception:
        return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_archive.py -v`

- [ ] **Step 5: Commit**

```bash
git add mempalace/archive.py tests/test_archive.py
git commit -m "feat(archive): implement soft-archiving to reduce neighborhood radius"
```

### Task 4: CLI Integration (`mempalace crystallize` and `search --deep`)

**Files:**
- Modify: `mempalace/cli.py`
- Modify: `mempalace/searcher.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_searcher.py`, modify `test_search_with_wing_filter` to ensure `--deep` ignores the archive exclusion. (Skip heavy CLI tests, just modify the implementation).

- [ ] **Step 2: Write minimal implementation**

In `mempalace/searcher.py`:
Update `search_memories` to accept `deep: bool = False`. If `not deep`, automatically filter out `wing == "archive"`.

```python
# In mempalace/searcher.py
def search_memories(
    palace_path: str,
    query: str,
    wing: str = None,
    room: str = None,
    n_results: int = 5,
    deep: bool = False, # NEW
):
    # ...
    where_clauses = []
    if wing:
        where_clauses.append({"wing": wing})
    elif not deep:
        # Exclude archive wing by default to prevent hubness
        where_clauses.append({"wing": {"$ne": "archive"}})
    # ... rest of where clause logic
```

In `mempalace/cli.py`:

```python
# Add deep flag to search parser
p_search.add_argument("--deep", action="store_true", help="Include soft-archived memories")

# Add new crystallize parser
p_cryst = sub.add_parser("crystallize", help="Crystallize dense rooms and soft-archive noise to improve retrieval")
p_cryst.add_argument("--threshold", type=int, default=100, help="Room size threshold (default: 100)")

# ... inside dispatch
def cmd_crystallize(args):
    from .palace import get_collection
    from .config import MempalaceConfig
    from .knowledge_graph import KnowledgeGraph
    from .entropy import detect_dense_rooms
    from .crystallize import find_room_diamonds
    from .archive import archive_noise
    
    config = MempalaceConfig()
    col = get_collection(config.palace_path, config.collection_name)
    kg = KnowledgeGraph()
    
    print(f"Scanning for dense rooms (>{args.threshold} drawers)...")
    dense_rooms = detect_dense_rooms(col, args.threshold)
    
    if not dense_rooms:
        print("Palace is well-optimized. No rooms suffer from hubness.")
        return
        
    for room in dense_rooms:
        print(f"Crystallizing '{room}'...")
        diamonds, noise = find_room_diamonds(col, room, top_k=10)
        archived = archive_noise(col, kg, room, noise)
        print(f"  → Preserved {len(diamonds)} core pillars (Diamonds)")
        print(f"  → Soft-archived {archived} noisy drawers to 'wing_archive'")
```

- [ ] **Step 3: Commit**

```bash
git add mempalace/cli.py mempalace/searcher.py
git commit -m "feat(cli): add crystallize command and deep search flag for organic archives"
```
