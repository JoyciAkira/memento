import pytest


@pytest.mark.asyncio
async def test_goals_first_class_replace_history(tmp_path, monkeypatch):
    from memento.provider import NeuroGraphProvider

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    p = NeuroGraphProvider(db_path=str(tmp_path / "mem.db"))

    out1 = await p.set_goals(goals=["g1", "g2"], context="proj", mode="replace", delete_reason="init")
    assert out1["inserted_ids"]
    active1 = await p.list_goals(context="proj", active_only=True)
    assert [g["goal"] for g in active1] == ["g2", "g1"]

    out2 = await p.set_goals(goals=["g3"], context="proj", mode="replace", delete_reason="update")
    assert out2["inserted_ids"]
    active2 = await p.list_goals(context="proj", active_only=True)
    assert [g["goal"] for g in active2] == ["g3"]

    all_goals = await p.list_goals(context="proj", active_only=False)
    assert any(g["goal"] == "g1" and g["is_deleted"] and g["delete_reason"] == "update" for g in all_goals)
    assert any(g["goal"] == "g2" and g["is_deleted"] and g["delete_reason"] == "update" for g in all_goals)


@pytest.mark.asyncio
async def test_get_active_goals_uses_goals_storage(tmp_path, monkeypatch):
    from memento.provider import NeuroGraphProvider
    from memento.tools.utils import get_active_goals

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    p = NeuroGraphProvider(db_path=str(tmp_path / "mem.db"))
    await p.set_goals(goals=["ship v1"], context=None, mode="replace", delete_reason="init")

    class Ctx:
        def __init__(self, provider):
            self.provider = provider

    injection = await get_active_goals(Ctx(p), max_goals=3, context=None)
    assert "ship v1" in injection

