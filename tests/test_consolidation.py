import asyncio
import json
import os
import tempfile

import pytest

from memento.consolidation import (
    ConsolidationEngine,
    UnionFind,
    _cosine_similarity,
    fuse_texts,
    merge_metadatas,
)
from memento.consolidation_scheduler import ConsolidationScheduler
from memento.provider import NeuroGraphProvider


def test_cosine_similarity_identical_vectors():
    v = [1.0, 2.0, 3.0]
    assert _cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal():
    assert _cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)


def test_cosine_similarity_empty():
    assert _cosine_similarity([], []) == 0.0
    assert _cosine_similarity([1], []) == 0.0
    assert _cosine_similarity([], [1]) == 0.0


def test_cosine_similarity_different_lengths():
    assert _cosine_similarity([1, 2], [1, 2, 3]) == 0.0


def test_cosine_similarity_zero_vector():
    assert _cosine_similarity([0, 0], [1, 1]) == 0.0


def test_union_find_single_element():
    uf = UnionFind()
    assert uf.find("a") == "a"


def test_union_find_merge():
    uf = UnionFind()
    uf.union("a", "b")
    assert uf.find("a") == uf.find("b")


def test_union_find_transitive():
    uf = UnionFind()
    uf.union("a", "b")
    uf.union("b", "c")
    assert uf.find("a") == uf.find("c")
    assert uf.find("b") == uf.find("c")


def test_union_find_disjoint_sets():
    uf = UnionFind()
    uf.union("a", "b")
    uf.union("c", "d")
    assert uf.find("a") == uf.find("b")
    assert uf.find("c") == uf.find("d")
    assert uf.find("a") != uf.find("c")


def test_fuse_texts_deduplicates_sentences():
    texts = [
        "The project uses React. It has a component-based architecture.",
        "The project uses React. State is managed with Redux.",
    ]
    result = fuse_texts(texts)
    assert "React" in result
    assert result.count("The project uses React") <= 1


def test_fuse_texts_empty_input():
    assert fuse_texts([]) == ""


def test_fuse_texts_single_text():
    assert fuse_texts(["Hello world"]) == "Hello world"


def test_merge_metadatas_empty():
    assert merge_metadatas([]) == {}


def test_merge_metadatas_single():
    meta = {"key": "value"}
    assert merge_metadatas([meta]) == meta


def test_merge_metadatas_combines_keys():
    m1 = {"a": 1}
    m2 = {"b": 2}
    result = merge_metadatas([m1, m2])
    assert result["a"] == 1
    assert result["b"] == 2


def test_merge_metadatas_deep_merges_dicts():
    m1 = {"nested": {"x": 1}}
    m2 = {"nested": {"y": 2}}
    result = merge_metadatas([m1, m2])
    assert result["nested"]["x"] == 1
    assert result["nested"]["y"] == 2


def test_merge_metadatas_unions_lists():
    m1 = {"tags": ["a", "b"]}
    m2 = {"tags": ["b", "c"]}
    result = merge_metadatas([m1, m2])
    assert set(result["tags"]) == {"a", "b", "c"}


@pytest.fixture
async def populated_db(tmp_path):
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    db_path = str(tmp_path / "consol.db")
    provider = NeuroGraphProvider(db_path=db_path)
    await provider.initialize()

    await provider.add("Memory alpha about React components.", user_id="default")
    await provider.add("Memory beta about React components.", user_id="default")
    await provider.add("Memory gamma about something completely different.", user_id="default")

    monkeypatch.undo()
    return db_path, provider


@pytest.mark.asyncio
async def test_consolidate_no_embeddings_returns_early(tmp_path):
    db_path = str(tmp_path / "consol.db")
    provider = NeuroGraphProvider(db_path=db_path)
    await provider.initialize()

    await provider.add("Memory one about testing.", user_id="default")
    await provider.add("Memory two about testing.", user_id="default")

    engine = ConsolidationEngine(db_path=db_path)
    result = await engine.consolidate()
    assert result["consolidated"] == 0


@pytest.mark.asyncio
async def test_consolidate_with_forced_embeddings(tmp_path):
    import sqlite3

    db_path = str(tmp_path / "consol.db")
    provider = NeuroGraphProvider(db_path=db_path)
    await provider.initialize()

    r1 = await provider.add("The project uses React for the frontend.", user_id="default")
    r2 = await provider.add("The project uses React for the UI layer.", user_id="default")
    r3 = await provider.add("Python backend handles the API.", user_id="default")

    shared_emb = json.dumps([0.1, 0.2, 0.3, 0.4, 0.5])
    different_emb = json.dumps([0.9, 0.8, 0.7, 0.6, 0.5])

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE memory_embeddings SET embedding = ? WHERE id = ?", (shared_emb, r1["id"]))
    conn.execute("UPDATE memory_embeddings SET embedding = ? WHERE id = ?", (shared_emb, r2["id"]))
    conn.execute("UPDATE memory_embeddings SET embedding = ? WHERE id = ?", (different_emb, r3["id"]))
    conn.commit()
    conn.close()

    engine = ConsolidationEngine(db_path=db_path, min_age_hours=0)
    result = await engine.consolidate()

    assert result["consolidated"] >= 1
    assert result["pairs_found"] >= 1


@pytest.mark.asyncio
async def test_cluster_pairs_groups_transitively():
    engine = ConsolidationEngine(db_path=":memory:")
    pairs = [("a", "b", 0.95), ("b", "c", 0.93)]
    clusters = engine.cluster_pairs(pairs)
    assert len(clusters) == 1
    members = list(clusters.values())[0]
    assert set(members) == {"a", "b", "c"}


@pytest.mark.asyncio
async def test_cluster_pairs_disjoint():
    engine = ConsolidationEngine(db_path=":memory:")
    pairs = [("a", "b", 0.95), ("c", "d", 0.94)]
    clusters = engine.cluster_pairs(pairs)
    assert len(clusters) == 2


@pytest.mark.asyncio
async def test_scheduler_start_stop():
    call_count = 0

    async def mock_consolidate():
        nonlocal call_count
        call_count += 1
        return {"consolidated": 0}

    scheduler = ConsolidationScheduler(
        consolidate_fn=mock_consolidate,
        interval_minutes=0.001,
        initial_delay_minutes=0.001,
    )
    assert not scheduler.is_running

    scheduler.start()
    assert scheduler.is_running

    await asyncio.sleep(0.3)
    assert call_count > 0

    scheduler.stop()
    assert not scheduler.is_running


@pytest.mark.asyncio
async def test_scheduler_no_double_start():
    async def noop():
        return {}

    scheduler = ConsolidationScheduler(consolidate_fn=noop)
    scheduler.start()
    assert scheduler.is_running

    scheduler.start()
    assert scheduler.is_running

    scheduler.stop()


@pytest.mark.asyncio
async def test_provider_consolidate_method(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    db_path = str(tmp_path / "prov_consol.db")
    provider = NeuroGraphProvider(db_path=db_path)
    await provider.initialize()

    await provider.add("Solo memory with no duplicates.", user_id="default")

    result = await provider.consolidate()
    assert isinstance(result, dict)
    assert "consolidated" in result


@pytest.mark.asyncio
async def test_consolidation_log_table_created(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    db_path = str(tmp_path / "mig.db")
    provider = NeuroGraphProvider(db_path=db_path)
    await provider.initialize()

    import sqlite3

    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='consolidation_log'"
    )
    assert cursor.fetchone() is not None
    conn.close()
