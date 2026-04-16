import os
import tempfile

import pytest

from memento.retrieval.pipeline import rrf_fuse


def test_rrf_fuse_prefers_consensus():
    lane_a = [("a", 10.0), ("b", 9.0), ("c", 8.0)]
    lane_b = [("b", 1.0), ("a", 0.9), ("d", 0.8)]

    ranked = rrf_fuse(
        lanes={"fts": lane_a, "dense": lane_b},
        k=60,
        lane_weights={"fts": 1.0, "dense": 1.0},
        limit=10,
    )

    assert ranked[0][0] in {"a", "b"}
    assert {ranked[0][0], ranked[1][0]} == {"a", "b"}


def test_rrf_fuse_weighted_lane():
    lane_a = [("x", 10.0)]
    lane_b = [("y", 1.0)]

    ranked = rrf_fuse(
        lanes={"fts": lane_a, "dense": lane_b},
        k=60,
        lane_weights={"fts": 2.0, "dense": 0.5},
        limit=10,
    )

    assert ranked[0][0] == "x"


def test_rrf_fuse_empty_lanes():
    ranked = rrf_fuse(lanes={}, k=60, limit=10)
    assert ranked == []


@pytest.mark.asyncio
async def test_vnext_pipeline_returns_traces_and_results():
    from memento.provider import NeuroGraphProvider

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "mem.db")
        p = NeuroGraphProvider(db_path=db_path)

        await p.add("alpha memory about testing", user_id="default")
        await p.add("beta memory about coding", user_id="default")

        bundle = await p.search_vnext_bundle("alpha", user_id="default", limit=5, trace=True)
        assert bundle["query"] == "alpha"
        assert len(bundle["results"]) >= 1
        assert any(t["lane"] == "fts" for t in bundle["traces"])
        assert any(t["lane"] == "dense" for t in bundle["traces"])
        assert any(t["lane"] == "recency" for t in bundle["traces"])


@pytest.mark.asyncio
async def test_vnext_pipeline_no_trace():
    from memento.provider import NeuroGraphProvider

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "mem.db")
        p = NeuroGraphProvider(db_path=db_path)

        await p.add("hello world", user_id="default")

        bundle = await p.search_vnext_bundle("hello", user_id="default", limit=5, trace=False)
        assert bundle["query"] == "hello"
        assert len(bundle["results"]) >= 1
        assert bundle["traces"] == []


@pytest.mark.asyncio
async def test_vnext_pipeline_with_filters():
    from memento.provider import NeuroGraphProvider

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "mem.db")
        p = NeuroGraphProvider(db_path=db_path)

        await p.add("backend memory", metadata={"module": "backend"})
        await p.add("frontend memory", metadata={"module": "frontend"})

        bundle = await p.search_vnext_bundle(
            "memory", user_id="default", limit=10, filters={"module": "backend"}, trace=True
        )
        assert len(bundle["results"]) >= 1
        assert all("backend" in r["memory"] or r["memory"] == "" for r in bundle["results"])
