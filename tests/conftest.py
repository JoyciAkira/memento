import os
import tempfile

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


@pytest.fixture(autouse=True)
def _windows_safe_tempdirs(monkeypatch):
    """Windows cannot remove SQLite files still held by a provider."""
    if os.name != "nt":
        return

    class SafeTemporaryDirectory(tempfile.TemporaryDirectory):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("ignore_cleanup_errors", True)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(tempfile, "TemporaryDirectory", SafeTemporaryDirectory)


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
        try:
            await ctx.provider.close()
        except Exception:
            pass
    _contexts.clear()
