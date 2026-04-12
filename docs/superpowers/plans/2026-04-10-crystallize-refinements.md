# Crystallization Refinements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine the crystallization lifecycle by adding `crystallized_at` timestamps, enabling flexible diamond counts (integers or percentages), and writing a test to prove idempotency on repeated cycles.

**Architecture:** 
1. Update `archive.py` to inject `crystallized_at = datetime.now().isoformat()` into metadata.
2. Update `crystallize.py` to accept `top_k` as either `int` or `float` (percentage of total room size).
3. Update `cli.py` to add `--diamonds` argument.
4. Add idempotency tests in `tests/test_crystallize.py`.

**Tech Stack:** Python 3, ChromaDB.

---

### Task 1: Add `crystallized_at` timestamp

**Files:**
- Modify: `mempalace/archive.py`
- Modify: `tests/test_archive.py`

- [x] **Step 1: Write the failing test**

In `tests/test_archive.py`:
```python
def test_archive_adds_crystallized_at():
    from mempalace.archive import archive_noise
    from unittest.mock import MagicMock
    
    mock_col = MagicMock()
    mock_kg = MagicMock()
    
    mock_col.get.return_value = {
        "ids": ["doc_1"],
        "metadatas": [{"wing": "work", "room": "ideas"}]
    }
    
    archive_noise(mock_col, mock_kg, "ideas", ["doc_1"])
    
    update_kwargs = mock_col.update.call_args[1]
    meta = update_kwargs["metadatas"][0]
    
    assert "crystallized_at" in meta
    assert meta["crystallized_at"].startswith("20") # Basic ISO format check
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_archive.py -k test_archive_adds_crystallized_at -v`

- [x] **Step 3: Write minimal implementation**

In `mempalace/archive.py`:
```python
from datetime import datetime
# ... inside archive_noise ...
        new_metadatas = []
        for meta in result["metadatas"]:
            new_meta = meta.copy()
            # Preserve original metadata for round-trip (uncrystallize) restoration
            if "wing" in new_meta:
                new_meta["original_wing"] = new_meta["wing"]
            if "room" in new_meta:
                new_meta["original_room"] = new_meta["room"]
                
            new_meta["wing"] = "archive"
            new_meta["crystallized_at"] = datetime.now().isoformat()
            new_metadatas.append(new_meta)
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_archive.py -v`

- [x] **Step 5: Commit**

```bash
git add mempalace/archive.py tests/test_archive.py
git commit -m "feat(archive): add crystallized_at timestamp to archived metadatas"
```

### Task 2: Flexible Diamond Count

**Files:**
- Modify: `mempalace/crystallize.py`
- Modify: `mempalace/cli.py`
- Modify: `tests/test_crystallize.py`

- [x] **Step 1: Write the failing test**

In `tests/test_crystallize.py`:
```python
def test_find_room_diamonds_percentage():
    from mempalace.crystallize import find_room_diamonds
    mock_col = MagicMock()
    
    # 10 documents
    ids = [f"doc{i}" for i in range(10)]
    mock_col.get.return_value = {
        "ids": ids,
        "documents": [f"Idea {i}" for i in range(10)],
        "metadatas": [{"room": "ideas"}] * 10
    }
    
    mock_col.query.return_value = {
        "ids": [["doc0"] for _ in range(10)],
        "distances": [[0.5] for _ in range(10)]
    }
    
    # Request top 20% (should be 2 items out of 10)
    diamonds, noise = find_room_diamonds(mock_col, "ideas", top_k=0.2)
    assert len(diamonds) == 2
    assert len(noise) == 8
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_crystallize.py -k test_find_room_diamonds_percentage -v`

- [x] **Step 3: Write minimal implementation**

In `mempalace/crystallize.py`:
```python
def find_room_diamonds(col: Any, room_name: str, top_k: int | float = 5) -> Tuple[List[str], List[str]]:
# ...
        if isinstance(top_k, float) and 0.0 < top_k < 1.0:
            k = max(1, int(len(ids) * top_k))
        else:
            k = int(top_k)
            
        if len(ids) <= k:
            return ids, []
# ...
        diamonds = [node_id for node_id, score in sorted_ids[:k]]
        noise = [node_id for node_id, score in sorted_ids[k:]]
```

In `mempalace/cli.py`:
```python
p_cryst.add_argument("--diamonds", type=str, default="10", help="Number of diamonds to keep, or percentage (e.g. 0.1 for 10%)")
# ...
    # Parse diamonds argument
    try:
        if "." in args.diamonds:
            diamonds_val = float(args.diamonds)
        else:
            diamonds_val = int(args.diamonds)
    except ValueError:
        diamonds_val = 10
        
    for room in dense_rooms:
        print(f"Crystallizing '{room}'...")
        diamonds, noise = find_room_diamonds(col, room, top_k=diamonds_val)
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_crystallize.py -v`

- [x] **Step 5: Commit**

```bash
git add mempalace/crystallize.py mempalace/cli.py tests/test_crystallize.py
git commit -m "feat(crystallize): support percentage-based diamond count"
```

### Task 3: Idempotency & Re-crystallization test

- [x] Write test `test_crystallize_idempotency` in `tests/test_crystallize.py`
- [x] Run `pytest tests/test_crystallize.py -v`
