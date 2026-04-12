# Organic Archive Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the soft-archiving module to preserve `original_wing` and `original_room` metadata during apoptosis, enabling future restoration ("uncrystallize").

**Architecture:** 
1. Update `archive_noise` in `mempalace/archive.py` to copy the current `wing` and `room` into `original_wing` and `original_room` fields before overwriting the `wing` to "archive".

**Tech Stack:** Python 3, ChromaDB.

---

### Task 1: Preserve original metadata in archive

**Files:**
- Modify: `mempalace/archive.py`
- Modify: `tests/test_archive.py`

- [x] **Step 1: Write the failing test**

In `tests/test_archive.py`:
```python
def test_archive_preserves_original_metadata():
    from mempalace.archive import archive_noise
    from unittest.mock import MagicMock
    
    mock_col = MagicMock()
    mock_kg = MagicMock()
    
    mock_col.get.return_value = {
        "ids": ["doc_1"],
        "metadatas": [{"wing": "work", "room": "ideas", "extra": "data"}]
    }
    
    archive_noise(mock_col, mock_kg, "ideas", ["doc_1"])
    
    update_kwargs = mock_col.update.call_args[1]
    meta = update_kwargs["metadatas"][0]
    
    assert meta["wing"] == "archive"
    assert meta["original_wing"] == "work"
    assert meta["original_room"] == "ideas"
    assert meta["extra"] == "data"
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_archive.py -k test_archive_preserves_original_metadata -v`
Expected: FAIL (KeyError 'original_wing')

- [x] **Step 3: Write minimal implementation**

In `mempalace/archive.py`, modify `archive_noise`:

```python
        new_metadatas = []
        for meta in result["metadatas"]:
            new_meta = meta.copy()
            # Preserve original metadata for round-trip (uncrystallize) restoration
            if "wing" in new_meta:
                new_meta["original_wing"] = new_meta["wing"]
            if "room" in new_meta:
                new_meta["original_room"] = new_meta["room"]
                
            new_meta["wing"] = "archive"
            new_metadatas.append(new_meta)
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_archive.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add mempalace/archive.py tests/test_archive.py
git commit -m "feat(archive): preserve original_wing and original_room metadata during apoptosis"
```
