import asyncio
import os
import tempfile
import pytest
from memento.provider import NeuroGraphProvider

@pytest.mark.asyncio
async def test_orchestrator_initialized_after_init():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_orch.db")
        provider = NeuroGraphProvider(db_path=db_path)
        await provider.initialize()

        assert provider.orchestrator is not None
        assert hasattr(provider.orchestrator, "l1")
        assert hasattr(provider.orchestrator, "l2")
        assert hasattr(provider.orchestrator, "l3")


@pytest.mark.asyncio
async def test_orchestrator_add_to_different_tiers():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_orch.db")
        provider = NeuroGraphProvider(db_path=db_path)
        await provider.initialize()
        orch = provider.orchestrator

        id1 = orch.add("L1 content", tier="working")
        id2 = orch.add("L2 episodic content", tier="episodic")
        id3 = orch.add("L3 semantic content", tier="semantic")

        l1_items = orch.l1.get_all()
        assert len(l1_items) == 1
        assert l1_items[0]["content"] == "L1 content"

        l2_results = orch.search("episodic", tier="episodic")
        assert len(l2_results) == 1
        assert l2_results[0]["memory"] == "L2 episodic content"

        l3_results = orch.search("semantic", tier="semantic")
        assert len(l3_results) == 1
        assert l3_results[0]["memory"] == "L3 semantic content"


@pytest.mark.asyncio
async def test_orchestrator_search_all_tiers():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_orch.db")
        provider = NeuroGraphProvider(db_path=db_path)
        await provider.initialize()
        orch = provider.orchestrator

        orch.add("Unique L1 item", tier="working")
        orch.add("Unique L2 item", tier="episodic")
        orch.add("Unique L3 item", tier="semantic")

        results = orch.search("Unique")
        assert len(results) == 3
        tiers = {r["memory_tier"] for r in results}
        assert tiers == {"working", "episodic", "semantic"}
