import weakref

import pytest
import pytest_asyncio


@pytest.fixture(autouse=True)
def _disable_openai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MEMENTO_DIR", raising=False)
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
async def _cleanup_provider_instances(monkeypatch):
    """Close providers created directly by tests, not just cached contexts.

    Aiosqlite starts a worker thread per connection.  A provider that is not
    closed leaves that worker waiting for its event loop, which then emits an
    ``Event loop is closed`` unhandled-thread warning after the test finishes.
    """
    from memento.provider import NeuroGraphProvider

    instances = weakref.WeakSet()
    original_initialize = NeuroGraphProvider.initialize

    async def tracked_initialize(self):
        instances.add(self)
        await original_initialize(self)

    monkeypatch.setattr(NeuroGraphProvider, "initialize", tracked_initialize)
    yield
    for provider in list(instances):
        try:
            await provider.close()
        except Exception:
            pass


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
