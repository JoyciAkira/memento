import pytest
import asyncio
import sqlite3
from memento.provider import NeuroGraphProvider

@pytest.mark.asyncio
async def test_orchestrator_initialized_after_init():
    from memento.migrations.runner import MigrationRunner
    from memento.migrations.versions import get_all_migrations
    import tempfile, os

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_orch.db")
        runner = MigrationRunner(db_path)
        for version, name, fn in get_all_migrations():
            runner.register(version, name, fn)
        runner.run()

        provider = NeuroGraphProvider(db_path=db_path)
        await provider.initialize()

        assert provider.orchestrator is not None
        assert hasattr(provider.orchestrator, "l1")
        assert hasattr(provider.orchestrator, "l2")
        assert hasattr(provider.orchestrator, "l3")


@pytest.mark.asyncio
async def test_orchestrator_add_to_different_tiers():
    from memento.migrations.runner import MigrationRunner
    from memento.migrations.versions import get_all_migrations
    import tempfile, os

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_orch.db")
        runner = MigrationRunner(db_path)
        for version, name, fn in get_all_migrations():
            runner.register(version, name, fn)
        runner.run()

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
    from memento.migrations.runner import MigrationRunner
    from memento.migrations.versions import get_all_migrations
    import tempfile, os

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_orch.db")
        runner = MigrationRunner(db_path)
        for version, name, fn in get_all_migrations():
            runner.register(version, name, fn)
        runner.run()

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


@pytest.mark.asyncio
async def test_orchestrator_vsa_index_integration():
    from memento.migrations.runner import MigrationRunner
    from memento.migrations.versions import get_all_migrations
    import tempfile, os

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_vsa_orch.db")
        runner = MigrationRunner(db_path)
        for version, name, fn in get_all_migrations():
            runner.register(version, name, fn)
        runner.run()

        provider = NeuroGraphProvider(db_path=db_path)
        await provider.initialize()
        orch = provider.orchestrator

        orch.enable_vsa_index(db_path)
        assert orch._vsa_index is not None

        orch.add("Python is a great language", tier="semantic")
        orch.add("FastAPI is a Python web framework", tier="semantic")

        results = orch.search("python", tier="semantic")
        assert len(results) >= 1

        vsa_stats = orch.get_vsa_stats()
        assert vsa_stats is not None
        assert vsa_stats["indexed_memories"] >= 2

        orch.disable_vsa_index()
        assert orch._vsa_index is None


@pytest.mark.asyncio
async def test_orchestrator_vsa_search_relation():
    from memento.migrations.runner import MigrationRunner
    from memento.migrations.versions import get_all_migrations
    import tempfile, os

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_vsa_rel.db")
        runner = MigrationRunner(db_path)
        for version, name, fn in get_all_migrations():
            runner.register(version, name, fn)
        runner.run()

        provider = NeuroGraphProvider(db_path=db_path)
        await provider.initialize()
        orch = provider.orchestrator

        orch.enable_vsa_index(db_path)
        orch.add("User prefers FastAPI", tier="semantic")
        orch.add("FastAPI is a web framework", tier="semantic")

        results = orch.search_relation("fastapi", "web framework")
        assert len(results) >= 1
