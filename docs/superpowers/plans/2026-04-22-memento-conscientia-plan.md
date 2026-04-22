# Memento Conscientia Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the monolithic `NeuroGraphProvider` into a 3-tier memory architecture (L1 Fast, L2 Episodic, L3 Semantic) and update the database schema to support episodic/semantic memory isolation.

**Architecture:** We are moving from a single flat memory store to a "Nested Learning" 3-clock architecture. 
- L1 (Working Memory): In-memory only (cache), zero I/O.
- L2 (Episodic Memory): Appends agent trajectories/actions to SQLite.
- L3 (Semantic Memory): Consolidated facts, rules, and invariants.
The `NeuroGraphProvider` will become a Facade that orchestrates these three layers, maintaining backward compatibility while setting the stage for VSA and Active Inference in later phases.

**Tech Stack:** Python 3.10+, aiosqlite, pytest

---

### Task 1: Create DB Migration for Episodic/Semantic Split

**Files:**
- Create: `memento/migrations/versions/v009_memory_tiers.py`
- Modify: `memento/migrations/versions/__init__.py`
- Test: `tests/test_schema_migrations.py`

- [ ] **Step 1: Write the failing test**
Update `tests/test_schema_migrations.py` to check for the new `memory_tier` column.

```python
import pytest
import aiosqlite
from memento.migrations.runner import MigrationRunner
from memento.migrations.versions import get_all_migrations

@pytest.mark.asyncio
async def test_v009_memory_tiers_migration(tmp_path):
    db_path = tmp_path / "test_tiers.db"
    runner = MigrationRunner(str(db_path))
    
    for version, name, fn in get_all_migrations():
        runner.register(version, name, fn)
        
    await runner.run()
    
    async with aiosqlite.connect(db_path) as db:
        # Check if memory_tier column exists in memories table
        cursor = await db.execute("PRAGMA table_info(memories)")
        columns = [row[1] for row in await cursor.fetchall()]
        assert "memory_tier" in columns
        
        # Check default value is 'semantic' (L3) to preserve old behavior
        await db.execute("INSERT INTO memories (id, memory) VALUES ('test1', 'content')")
        cursor = await db.execute("SELECT memory_tier FROM memories WHERE id = 'test1'")
        row = await cursor.fetchone()
        assert row[0] == "semantic"
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_schema_migrations.py::test_v009_memory_tiers_migration -v`
Expected: FAIL (module not found or assertion failed)

- [ ] **Step 3: Write minimal implementation**
Create `memento/migrations/versions/v009_memory_tiers.py`:

```python
import aiosqlite

async def upgrade(db: aiosqlite.Connection) -> None:
    """Add memory_tier column to memories table."""
    # SQLite ALTER TABLE doesn't support adding columns with DEFAULT that are not constant,
    # but 'semantic' is a constant string so it's fine.
    try:
        await db.execute(
            "ALTER TABLE memories ADD COLUMN memory_tier TEXT DEFAULT 'semantic'"
        )
        # Add index for faster tier-based retrieval
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_tier ON memories(memory_tier)"
        )
    except aiosqlite.OperationalError as e:
        if "duplicate column name" not in str(e).lower():
            raise
```

Update `memento/migrations/versions/__init__.py` to include v009:

```python
from . import (
    v001_initial_schema,
    v002_consolidation_log,
    v003_kg_extraction,
    v004_relevance_tracking,
    v005_cross_workspace,
    v007_performance_indexes,
    v008_kg_schema,
    v009_memory_tiers,
)

def get_all_migrations():
    return [
        (1, "v001_initial_schema", v001_initial_schema.upgrade),
        (2, "v002_consolidation_log", v002_consolidation_log.upgrade),
        (3, "v003_kg_extraction", v003_kg_extraction.upgrade),
        (4, "v004_relevance_tracking", v004_relevance_tracking.upgrade),
        (5, "v005_cross_workspace", v005_cross_workspace.upgrade),
        (7, "v007_performance_indexes", v007_performance_indexes.upgrade),
        (8, "v008_kg_schema", v008_kg_schema.upgrade),
        (9, "v009_memory_tiers", v009_memory_tiers.upgrade),
    ]
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_schema_migrations.py::test_v009_memory_tiers_migration -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add tests/test_schema_migrations.py memento/migrations/versions/v009_memory_tiers.py memento/migrations/versions/__init__.py
git commit -m "feat(db): add memory_tier column to memories table for L2/L3 split"
```

---

### Task 2: Create L1 Working Memory Module

**Files:**
- Create: `memento/memory/l1_working.py`
- Create: `tests/test_l1_working.py`
- Modify: `memento/memory/__init__.py` (Create module)

- [ ] **Step 1: Write the failing test**
Create `tests/test_l1_working.py`:

```python
import pytest
from memento.memory.l1_working import L1WorkingMemory

def test_l1_working_memory_basic_ops():
    l1 = L1WorkingMemory(max_size=3)
    
    l1.add("ctx1", "Task: refactor code")
    l1.add("ctx2", "File: main.py")
    
    assert len(l1.get_all()) == 2
    assert l1.get_all()[0]["content"] == "Task: refactor code"
    
    # Test eviction
    l1.add("ctx3", "Line 10")
    l1.add("ctx4", "Error 500")
    
    assert len(l1.get_all()) == 3
    # ctx1 should be evicted
    assert not any(item["id"] == "ctx1" for item in l1.get_all())
    
    l1.clear()
    assert len(l1.get_all()) == 0
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_l1_working.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Write minimal implementation**
Create `memento/memory/__init__.py` (empty).
Create `memento/memory/l1_working.py`:

```python
import time
from collections import OrderedDict
from typing import List, Dict, Any

class L1WorkingMemory:
    """
    Fast, in-memory volatile cache (L1).
    Used for immediate context window (e.g. current task, active file).
    Evicts oldest entries automatically when max_size is reached.
    """
    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()

    def add(self, entry_id: str, content: str, metadata: Dict[str, Any] = None) -> None:
        if entry_id in self._cache:
            del self._cache[entry_id] # move to end
            
        self._cache[entry_id] = {
            "id": entry_id,
            "content": content,
            "metadata": metadata or {},
            "timestamp": time.time()
        }
        
        if len(self._cache) > self.max_size:
            self._cache.popitem(last=False) # FIFO eviction

    def get_all(self) -> List[Dict[str, Any]]:
        return list(self._cache.values())

    def remove(self, entry_id: str) -> None:
        self._cache.pop(entry_id, None)

    def clear(self) -> None:
        self._cache.clear()
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_l1_working.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add memento/memory/ tests/test_l1_working.py
git commit -m "feat(memory): implement L1 volatile working memory"
```

---

### Task 3: Create L2/L3 Memory Stores

**Files:**
- Create: `memento/memory/l2_episodic.py`
- Create: `memento/memory/l3_semantic.py`
- Create: `tests/test_memory_tiers.py`

- [ ] **Step 1: Write the failing test**
Create `tests/test_memory_tiers.py`:

```python
import pytest
import aiosqlite
import uuid
from memento.memory.l2_episodic import L2EpisodicMemory
from memento.memory.l3_semantic import L3SemanticMemory
from memento.migrations.runner import MigrationRunner
from memento.migrations.versions import get_all_migrations

@pytest.fixture
async def initialized_db(tmp_path):
    db_path = tmp_path / "test_memory.db"
    runner = MigrationRunner(str(db_path))
    for version, name, fn in get_all_migrations():
        runner.register(version, name, fn)
    await runner.run()
    
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    yield db
    await db.close()

@pytest.mark.asyncio
async def test_l2_episodic_add_and_retrieve(initialized_db):
    l2 = L2EpisodicMemory(initialized_db)
    
    mem_id = str(uuid.uuid4())
    await l2.add(mem_id, "User ran git status", {"action": "run_command"})
    
    results = await l2.search("git status")
    assert len(results) == 1
    assert results[0]["memory_tier"] == "episodic"
    assert results[0]["memory"] == "User ran git status"

@pytest.mark.asyncio
async def test_l3_semantic_add_and_retrieve(initialized_db):
    l3 = L3SemanticMemory(initialized_db)
    
    mem_id = str(uuid.uuid4())
    await l3.add(mem_id, "Project uses Python 3.10", {"category": "rule"})
    
    results = await l3.search("Python")
    assert len(results) == 1
    assert results[0]["memory_tier"] == "semantic"
    assert results[0]["memory"] == "Project uses Python 3.10"
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_memory_tiers.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**
Create `memento/memory/l2_episodic.py`:

```python
import aiosqlite
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

class L2EpisodicMemory:
    """
    Medium-term memory for agent trajectories, logs, and experiences.
    Saved to SQLite with memory_tier='episodic'.
    """
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def add(self, memory_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        now = datetime.now().isoformat()
        meta_str = json.dumps(metadata) if metadata else "{}"
        
        await self.db.execute(
            """
            INSERT INTO memories (id, memory, metadata, created_at, updated_at, memory_tier)
            VALUES (?, ?, ?, ?, ?, 'episodic')
            """,
            (memory_id, content, meta_str, now, now)
        )
        await self.db.commit()

    async def search(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        # For Phase 1, simple LIKE search. VSA/FTS will be added in later phases.
        cursor = await self.db.execute(
            """
            SELECT id, memory, metadata, created_at, memory_tier 
            FROM memories 
            WHERE memory_tier = 'episodic' AND memory LIKE ? AND (is_deleted = 0 OR is_deleted IS NULL)
            ORDER BY created_at DESC LIMIT ?
            """,
            (f"%{query}%", limit)
        )
        rows = await cursor.fetchall()
        
        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "memory": r["memory"],
                "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
                "created_at": r["created_at"],
                "memory_tier": r["memory_tier"]
            })
        return results
```

Create `memento/memory/l3_semantic.py`:

```python
import aiosqlite
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

class L3SemanticMemory:
    """
    Long-term crystallized memory for facts, rules, and invariants.
    Saved to SQLite with memory_tier='semantic'.
    """
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def add(self, memory_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        now = datetime.now().isoformat()
        meta_str = json.dumps(metadata) if metadata else "{}"
        
        await self.db.execute(
            """
            INSERT INTO memories (id, memory, metadata, created_at, updated_at, memory_tier)
            VALUES (?, ?, ?, ?, ?, 'semantic')
            """,
            (memory_id, content, meta_str, now, now)
        )
        await self.db.commit()

    async def search(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        # For Phase 1, simple LIKE search.
        cursor = await self.db.execute(
            """
            SELECT id, memory, metadata, created_at, memory_tier 
            FROM memories 
            WHERE memory_tier = 'semantic' AND memory LIKE ? AND (is_deleted = 0 OR is_deleted IS NULL)
            ORDER BY created_at DESC LIMIT ?
            """,
            (f"%{query}%", limit)
        )
        rows = await cursor.fetchall()
        
        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "memory": r["memory"],
                "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
                "created_at": r["created_at"],
                "memory_tier": r["memory_tier"]
            })
        return results
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_memory_tiers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add memento/memory/l2_episodic.py memento/memory/l3_semantic.py tests/test_memory_tiers.py
git commit -m "feat(memory): implement L2 episodic and L3 semantic storage modules"
```

---

### Task 4: Create Orchestrator and Refactor NeuroGraphProvider

**Files:**
- Create: `memento/memory/orchestrator.py`
- Modify: `memento/provider.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**
Create `tests/test_orchestrator.py`:

```python
import pytest
import aiosqlite
from memento.memory.orchestrator import MemoryOrchestrator
from memento.migrations.runner import MigrationRunner
from memento.migrations.versions import get_all_migrations

@pytest.fixture
async def initialized_db(tmp_path):
    db_path = tmp_path / "test_orch.db"
    runner = MigrationRunner(str(db_path))
    for version, name, fn in get_all_migrations():
        runner.register(version, name, fn)
    await runner.run()
    
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    yield db
    await db.close()

@pytest.mark.asyncio
async def test_orchestrator_routing(initialized_db):
    orch = MemoryOrchestrator(initialized_db)
    
    # L1
    await orch.add("l1_data", tier="working")
    # L2
    await orch.add("l2_data", tier="episodic")
    # L3
    await orch.add("l3_data", tier="semantic")
    
    assert len(orch.l1.get_all()) == 1
    
    l2_res = await orch.l2.search("l2_data")
    assert len(l2_res) == 1
    
    l3_res = await orch.l3.search("l3_data")
    assert len(l3_res) == 1
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_orchestrator.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**
Create `memento/memory/orchestrator.py`:

```python
import aiosqlite
import uuid
from typing import List, Dict, Any, Optional

from memento.memory.l1_working import L1WorkingMemory
from memento.memory.l2_episodic import L2EpisodicMemory
from memento.memory.l3_semantic import L3SemanticMemory

class MemoryOrchestrator:
    """
    Coordinates L1, L2, and L3 memory layers.
    """
    def __init__(self, db: aiosqlite.Connection):
        self.db = db
        self.l1 = L1WorkingMemory()
        self.l2 = L2EpisodicMemory(db)
        self.l3 = L3SemanticMemory(db)

    async def add(self, content: str, metadata: Optional[Dict[str, Any]] = None, tier: str = "semantic") -> str:
        mem_id = str(uuid.uuid4())
        
        if tier == "working":
            self.l1.add(mem_id, content, metadata)
        elif tier == "episodic":
            await self.l2.add(mem_id, content, metadata)
        elif tier == "semantic":
            await self.l3.add(mem_id, content, metadata)
        else:
            raise ValueError(f"Unknown memory tier: {tier}")
            
        return mem_id
```

Modify `memento/provider.py` to instantiate `MemoryOrchestrator` after DB initialization.
Add this at the end of `NeuroGraphProvider.initialize`:

```python
# memento/provider.py - modifications
# 1. Add imports at top
from memento.memory.orchestrator import MemoryOrchestrator

# 2. In NeuroGraphProvider.__init__, add:
# self.orchestrator = None

# 3. At the end of NeuroGraphProvider.initialize (inside the write_lock), add:
# self.orchestrator = MemoryOrchestrator(self._db)
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_orchestrator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add memento/memory/orchestrator.py memento/provider.py tests/test_orchestrator.py
git commit -m "feat(memory): create Orchestrator and integrate with NeuroGraphProvider"
```

---
