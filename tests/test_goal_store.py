import pytest
from memento.migrations.runner import MigrationRunner
from memento.migrations.versions import get_all_migrations
from memento.goal_store import GoalStore


def _run_migration(db_path):
    runner = MigrationRunner(db_path)
    for version, name, fn in get_all_migrations():
        runner.register(version, name, fn)
    runner.run()


class TestGoalStore:
    @pytest.mark.asyncio
    async def test_set_and_list_goals(self, tmp_workspace):
        _run_migration(tmp_workspace)
        store = GoalStore(tmp_workspace)
        result = await store.set_goals(["Goal A", "Goal B"])
        assert len(result["inserted_ids"]) == 2
        goals = await store.list_goals()
        assert len(goals) == 2
        assert any(g["goal"] == "Goal A" for g in goals)

    @pytest.mark.asyncio
    async def test_empty_goals_raises(self, tmp_workspace):
        _run_migration(tmp_workspace)
        store = GoalStore(tmp_workspace)
        with pytest.raises(ValueError, match="non-empty"):
            await store.set_goals([])

    @pytest.mark.asyncio
    async def test_replace_mode(self, tmp_workspace):
        _run_migration(tmp_workspace)
        store = GoalStore(tmp_workspace)
        await store.set_goals(["Old Goal"])
        await store.set_goals(["New Goal"], mode="replace")
        goals = await store.list_goals(active_only=False)
        active = [g for g in goals if g["is_active"]]
        deleted = [g for g in goals if not g["is_active"]]
        assert len(active) == 1
        assert active[0]["goal"] == "New Goal"
        assert len(deleted) == 1

    @pytest.mark.asyncio
    async def test_append_mode(self, tmp_workspace):
        _run_migration(tmp_workspace)
        store = GoalStore(tmp_workspace)
        await store.set_goals(["Goal 1"])
        await store.set_goals(["Goal 2"], mode="append")
        goals = await store.list_goals()
        assert len(goals) == 2

    @pytest.mark.asyncio
    async def test_invalid_mode_raises(self, tmp_workspace):
        _run_migration(tmp_workspace)
        store = GoalStore(tmp_workspace)
        with pytest.raises(ValueError, match="replace.*append"):
            await store.set_goals(["test"], mode="invalid")
