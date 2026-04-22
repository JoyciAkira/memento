import pytest
import os
import tempfile
from memento.memory.vsa_index import VSAIndex
from memento.memory.hdc import HDCEncoder

def test_extract_entities():
    idx = VSAIndex(":memory:")
    entities = idx.extract_entities("Python is a great programming language")
    assert "python" in entities
    assert len(entities) <= 10

def test_index_and_query_by_entity():
    idx = VSAIndex(":memory:")
    idx.index_memory("mem1", "Python is a programming language")
    idx.index_memory("mem2", "JavaScript is a scripting language")
    idx.index_memory("mem3", "Python FastAPI web framework")

    results = idx.query_by_entity("python")
    assert "mem1" in results or "mem3" in results

def test_query_relation():
    idx = VSAIndex(":memory:")
    idx.index_memory("mem1", "User prefers FastAPI")
    idx.index_memory("mem2", "FastAPI is a web framework")

    results = idx.query_relation("fastapi", "web framework")
    assert "mem2" in results

def test_unindex_memory():
    idx = VSAIndex(":memory:")
    idx.index_memory("mem1", "Test memory")
    assert "mem1" in idx._entity_cache

    idx.unindex_memory("mem1")
    assert "mem1" not in idx._entity_cache

def test_index_stats():
    idx = VSAIndex(":memory:")
    idx.index_memory("mem1", "Python programming")
    idx.index_memory("mem2", "JavaScript programming")

    stats = idx.get_index_stats()
    assert stats["indexed_memories"] == 2
    assert stats["total_entities"] >= 2
