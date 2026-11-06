import pytest
import pytest_asyncio


@pytest.fixture(autouse=True)
def _disable_openai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")
    from memento.settings import settings

    settings.reload()
    yield
    settings.reload()


@pytest.fixture
def tmp_workspace(tmp_path):
    db_path = str(tmp_path / "test_memory.db")
    return db_path


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_workspace_contexts():
    """Clear cached WorkspaceContext instances between tests to prevent state leakage."""
    yield
    from memento.workspace_context import _contexts

    for ctx in list(_contexts.values()):
        # A running watchdog can read coverage's temporary data file while
        # pytest-cov tries to rename it, which fails on Windows.
        if ctx.daemon and ctx.daemon.is_running:
            try:
                ctx.daemon.stop()
            except Exception:
                pass
        try:
            ctx.stop_autonomous_agent()
        except Exception:
            pass
        try:
            await ctx.provider.close()
        except Exception:
            pass
    _contexts.clear()
