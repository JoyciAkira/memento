import pytest

from memento.migrations.runner import MigrationRunner
from memento.migrations.versions import get_all_migrations
from memento.provider import NeuroGraphProvider
from memento.session_manager import SessionManager


def _run_migrations(path: str) -> None:
    runner = MigrationRunner(path)
    for version, name, fn in get_all_migrations():
        runner.register(version, name, fn)
    runner.run()


@pytest.mark.asyncio
async def test_checkpoint_includes_goals_and_l1(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    db_path = str(tmp_path / "mem.db")
    _run_migrations(db_path)

    p = NeuroGraphProvider(db_path=db_path)
    try:
        await p.set_goals(goals=["ship v1"], context=None, mode="replace", delete_reason="init")
        await p.initialize()
        p.orchestrator.l1.add("l1a", "hot context", {"k": "v"})

        mgr = SessionManager(db_path=db_path, workspace_root=str(tmp_path), provider=p)
        session_id = await mgr.ensure_session()
        snap = await mgr.create_checkpoint(session_id=session_id, reason="manual")

        assert any(g.get("goal") == "ship v1" for g in snap.get("goals", []))
        assert any(i.get("id") == "l1a" for i in snap.get("l1", []))
    finally:
        if getattr(p, "_db", None) is not None:
            await p._db.close()
        if getattr(p, "_db_read", None) is not None:
            await p._db_read.close()
        if getattr(p, "_sync_db", None) is not None:
            p._sync_db.close()


@pytest.mark.asyncio
async def test_resume_restores_l1_into_new_active_session(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    db_path = str(tmp_path / "mem.db")
    _run_migrations(db_path)

    p = NeuroGraphProvider(db_path=db_path)
    try:
        await p.initialize()
        p.orchestrator.l1.add("l1a", "hot context", {})

        mgr = SessionManager(db_path=db_path, workspace_root=str(tmp_path), provider=p)
        session_id = await mgr.ensure_session()
        await mgr.create_checkpoint(session_id=session_id, reason="manual")

        p.orchestrator.l1.clear()
        out = await mgr.resume_from(session_id=session_id)
        assert out["resumed_from"] == session_id
        assert out["new_session_id"]
        assert any(i.get("id") == "l1a" for i in p.orchestrator.l1.dump())
    finally:
        if getattr(p, "_db", None) is not None:
            await p._db.close()
        if getattr(p, "_db_read", None) is not None:
            await p._db_read.close()
        if getattr(p, "_sync_db", None) is not None:
            p._sync_db.close()
