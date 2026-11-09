import json
import os
import sqlite3
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
async def test_provider_metadata_uses_workspace_not_memento_dir(monkeypatch):
    from memento.workspace_context import WorkspaceContext

    with (
        tempfile.TemporaryDirectory() as workspace_a,
        tempfile.TemporaryDirectory() as workspace_b,
    ):
        monkeypatch.setenv("MEMENTO_DIR", workspace_b)
        ctx = WorkspaceContext(workspace_a)
        try:
            await ctx.provider.initialize()
            result = await ctx.provider.add(
                "workspace isolation probe", user_id="default"
            )

            conn = sqlite3.connect(ctx.provider.db_path)
            try:
                row = conn.execute(
                    "SELECT metadata FROM memories WHERE id = ?", (result["id"],)
                ).fetchone()
            finally:
                conn.close()

            metadata = json.loads(row[0])
            assert metadata["workspace_root"] == os.path.realpath(workspace_a)
        finally:
            await ctx.provider.close()


@pytest.mark.asyncio
async def test_mcp_server_workspace_prefers_memento_dir(monkeypatch):
    import importlib

    with tempfile.TemporaryDirectory() as ws:
        monkeypatch.setenv("MEMENTO_DIR", ws)
        import memento.mcp_server as ms

        importlib.reload(ms)
        res = await ms.call_tool("memento_status", {})
        assert ws in res[0].text

        from memento.workspace_context import get_workspace_context

        await get_workspace_context(ws).provider.close()


def _search_memories(result) -> list[str]:
    payload = result[0].text.rsplit("Results:\n", 1)[1]
    return [r.get("memory", "") for r in json.loads(payload)]


def _metadata_workspace_roots(workspace: str) -> set[str]:
    db_path = os.path.join(workspace, ".memento", "neurograph_memory.db")
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT text, metadata FROM memories").fetchall()
    finally:
        conn.close()
    roots = set()
    for _text, raw in rows:
        metadata = json.loads(raw or "{}")
        if metadata.get("workspace_root"):
            roots.add(metadata["workspace_root"])
    return roots


@pytest.mark.asyncio
async def test_mcp_two_workspaces_isolated_via_memento_dir(monkeypatch):
    """MEMENTO_DIR must select the workspace: no memory or metadata leakage.

    No ``workspace_root`` argument is passed, so the server resolves each call
    from the environment exactly as a real MCP client would.
    """
    from memento.mcp_server import call_tool

    with (
        tempfile.TemporaryDirectory() as workspace_a,
        tempfile.TemporaryDirectory() as workspace_b,
    ):
        monkeypatch.setenv("MEMENTO_DIR", workspace_a)
        await call_tool(
            "memento_remember",
            {"action": "add", "text": "alpha probe written in workspace A"},
        )

        monkeypatch.setenv("MEMENTO_DIR", workspace_b)
        await call_tool(
            "memento_remember",
            {"action": "add", "text": "beta probe written in workspace B"},
        )

        monkeypatch.setenv("MEMENTO_DIR", workspace_a)
        memories_a = _search_memories(
            await call_tool("memento_search", {"query": "probe", "limit": 20})
        )
        monkeypatch.setenv("MEMENTO_DIR", workspace_b)
        memories_b = _search_memories(
            await call_tool("memento_search", {"query": "probe", "limit": 20})
        )

        assert any("workspace A" in m for m in memories_a)
        assert not any("workspace B" in m for m in memories_a)
        assert any("workspace B" in m for m in memories_b)
        assert not any("workspace A" in m for m in memories_b)

        assert _metadata_workspace_roots(workspace_a) == {os.path.realpath(workspace_a)}
        assert _metadata_workspace_roots(workspace_b) == {os.path.realpath(workspace_b)}
