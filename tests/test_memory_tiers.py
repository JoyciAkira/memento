import pytest
import sqlite3
import uuid
from memento.memory.l2_episodic import L2EpisodicMemory
from memento.memory.l3_semantic import L3SemanticMemory
from memento.migrations.runner import MigrationRunner
from memento.migrations.versions import get_all_migrations
from memento.migrations.versions.v001_initial_schema import up as up_001

@pytest.fixture
def initialized_db(tmp_path):
    db_path = str(tmp_path / "test_memory.db")
    runner = MigrationRunner(db_path)
    for version, name, fn in get_all_migrations():
        runner.register(version, name, fn)
    runner.run()

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    yield db
    db.close()


def test_l2_episodic_add_and_retrieve(initialized_db):
    l2 = L2EpisodicMemory(initialized_db)

    mem_id = str(uuid.uuid4())
    l2.add(mem_id, "User ran git status", {"action": "run_command"})

    results = l2.search("git status")
    assert len(results) == 1
    assert results[0]["memory_tier"] == "episodic"
    assert results[0]["memory"] == "User ran git status"


def test_l3_semantic_add_and_retrieve(initialized_db):
    l3 = L3SemanticMemory(initialized_db)

    mem_id = str(uuid.uuid4())
    l3.add(mem_id, "Project uses Python 3.10", {"category": "rule"})

    results = l3.search("Python")
    assert len(results) == 1
    assert results[0]["memory_tier"] == "semantic"
    assert results[0]["memory"] == "Project uses Python 3.10"


def test_l2_does_not_find_l3_memories(initialized_db):
    l2 = L2EpisodicMemory(initialized_db)
    l3 = L3SemanticMemory(initialized_db)

    l3.add(str(uuid.uuid4()), "A semantic fact", {"category": "rule"})

    results = l2.search("semantic fact")
    assert len(results) == 0


def test_l3_does_not_find_l2_memories(initialized_db):
    l2 = L2EpisodicMemory(initialized_db)
    l3 = L3SemanticMemory(initialized_db)

    l2.add(str(uuid.uuid4()), "An episodic event", {"action": "test"})

    results = l3.search("episodic event")
    assert len(results) == 0
