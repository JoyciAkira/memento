import os
import tempfile

import pytest


def test_find_project_root_does_not_use_memento_marker(monkeypatch):
    import memento.mcp_server as ms

    with tempfile.TemporaryDirectory() as repo:
        os.makedirs(os.path.join(repo, ".git"), exist_ok=True)

        memento_dir = os.path.join(repo, "subdir", ".memento")
        os.makedirs(memento_dir, exist_ok=True)

        nested = os.path.join(repo, "subdir", "deep")
        os.makedirs(nested, exist_ok=True)

        root = ms.find_project_root(nested)
        assert root == os.path.abspath(repo)


@pytest.mark.asyncio
async def test_mcp_server_workspace_prefers_memento_dir(monkeypatch):
    import importlib

    with tempfile.TemporaryDirectory() as ws:
        monkeypatch.setenv("MEMENTO_DIR", ws)
        import memento.mcp_server as ms
        importlib.reload(ms)
        res = await ms.call_tool("memento_status", {})
        assert ws in res[0].text
