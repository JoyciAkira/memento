"""Contratti MCP offline: roundtrip memoria + traccia explain, senza replicare lo smoke completo."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

import memento.tools  # noqa: F401 — registra i tool
from memento.mcp_server import call_tool

_tests_dir = str(pathlib.Path(__file__).resolve().parent)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)
import mcp_contract_helpers as _mcp_contract  # noqa: E402


@pytest.mark.asyncio
async def test_offline_explain_search_reads_last_trace(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    ws = tmp_path
    subprocess.run(
        ["git", "init"],
        cwd=str(ws),
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    await call_tool("memento_toggle_access", {"workspace_root": str(ws), "state": "read-write"})
    await call_tool(
        "memento_add_memory",
        {"workspace_root": str(ws), "text": "contract trace anchor C7K", "metadata": {}},
    )
    await call_tool(
        "memento_search_memory",
        {"workspace_root": str(ws), "query": "C7K"},
    )
    out = await call_tool(
        "memento_explain_search",
        {"workspace_root": str(ws), "query": "C7K"},
    )
    _mcp_contract.validate_tool_response_contract("memento_explain_search", out)
    data = json.loads(out[0].text)
    assert data.get("error") != "no trace", "last_search.json deve esistere dopo search_memory"
    assert "lanes" in data, "traccia provider attesa con chiave lanes"


@pytest.mark.asyncio
async def test_offline_vnext_roundtrip_json_keys(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    ws = tmp_path
    subprocess.run(
        ["git", "init"],
        cwd=str(ws),
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    await call_tool("memento_toggle_access", {"workspace_root": str(ws), "state": "read-write"})
    await call_tool(
        "memento_add_memory",
        {"workspace_root": str(ws), "text": "vnext contract token VN99", "metadata": {}},
    )
    out_v = await call_tool(
        "memento_search_vnext",
        {"workspace_root": str(ws), "query": "VN99", "limit": 5, "trace": False},
    )
    _mcp_contract.validate_tool_response_contract("memento_search_vnext", out_v)
    out_e = await call_tool(
        "memento_explain_retrieval",
        {"workspace_root": str(ws), "query": "VN99"},
    )
    _mcp_contract.validate_tool_response_contract("memento_explain_retrieval", out_e)
