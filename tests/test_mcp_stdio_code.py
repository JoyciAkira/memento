"""End-to-end MCP stdio test for the code index and grounding tool."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from memento.code_index import CodeIndex
from memento.ledger import FileLedger

pytest.importorskip("tree_sitter")

ROOT = Path(__file__).resolve().parents[1]
_EXPECTED_TOOL_COUNT = 16


def _index(workspace: Path) -> None:
    ledger = FileLedger(str(workspace))
    ledger.sync()
    report = CodeIndex(str(workspace), ledger=ledger).update()
    assert report["indexed"] == 1


def _prepare_workspace(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "a.py").write_text(
        "def helper(x):\n    return x\n\ndef caller():\n    return helper(1)\n",
        encoding="utf-8",
    )
    _index(tmp_path)

    # Keep the temporary server from starting the autonomous daemon or
    # attempting network-backed embeddings.
    (tmp_path / ".memento" / "settings.json").write_text(
        json.dumps({"autonomy": {"level": "off"}}, indent=2),
        encoding="utf-8",
    )
    return tmp_path


def _text(result) -> str:
    assert not getattr(result, "isError", False), result
    return "\n".join(
        item.text for item in result.content if getattr(item, "type", None) == "text"
    )


def _json_result(result) -> dict:
    return json.loads(_text(result))


async def _exercise_server(workspace: Path) -> None:
    env = os.environ.copy()
    env["MEMENTO_DIR"] = str(workspace)
    env["MEMENTO_EMBEDDING_BACKEND"] = "none"
    env["MEMENTO_UI"] = "0"
    env["PYTHONPATH"] = str(ROOT) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    env.pop("OPENAI_API_KEY", None)

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "memento.mcp_server"],
        cwd=str(workspace),
        env=env,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert len(names) == _EXPECTED_TOOL_COUNT
            assert "memento_code" in names

            async def call(name: str, arguments: dict):
                return await session.call_tool(
                    name,
                    {"workspace_root": str(workspace), **arguments},
                    read_timeout_seconds=timedelta(seconds=30),
                )

            graph = _json_result(
                await call("memento_code", {"action": "graph", "symbol": "helper"})
            )
            assert graph["action"] == "graph"
            assert any(node["name"] == "helper" for node in graph["result"]["nodes"])

            all_graph = _json_result(await call("memento_code", {"action": "graph"}))
            assert len(all_graph["result"]["nodes"]) == 2

            limited_graph = _json_result(
                await call("memento_code", {"action": "graph", "limit": 1})
            )
            assert len(limited_graph["result"]["nodes"]) == 1

            clamped_graph = _json_result(
                await call("memento_code", {"action": "graph", "limit": -5})
            )
            assert len(clamped_graph["result"]["nodes"]) == 1

            missing_links = _json_result(
                await call("memento_code", {"action": "links"})
            )
            assert missing_links["result"] == {
                "error": "memory_id or query is required for links"
            }

            for text in (
                "helper is used in a.py",
                "helper is also used in a.py",
            ):
                saved = await call(
                    "memento_remember",
                    {"action": "add", "text": text},
                )
                assert "Memory saved" in _text(saved)

            stats = _json_result(await call("memento_code", {"action": "stats"}))
            assert stats["action"] == "stats"
            assert stats["result"]["files"] == 1
            assert stats["result"]["symbols"] >= 2
            assert stats["result"]["memory_links"] >= 2

            links = _json_result(
                await call(
                    "memento_code",
                    {"action": "links", "query": "helper"},
                )
            )
            assert links["action"] == "links"
            memories = links["result"]["memories"]
            assert len(memories) == 2
            helper_links = [
                link
                for memory in memories
                for link in memory["links"]
                if link["symbol"] == "helper"
            ]
            assert helper_links
            assert all(link["current"] and not link["stale"] for link in helper_links)
            assert all(link["confidence"] >= 0.9 for link in helper_links)

            limited_links = _json_result(
                await call(
                    "memento_code",
                    {"action": "links", "query": "helper", "limit": 1},
                )
            )
            assert len(limited_links["result"]["memories"]) == 1

            clamped_links = _json_result(
                await call(
                    "memento_code",
                    {"action": "links", "query": "helper", "limit": -5},
                )
            )
            assert len(clamped_links["result"]["memories"]) == 1

            target_memory = memories[0]["memory_id"]
            unknown_memory = _json_result(
                await call(
                    "memento_code",
                    {"action": "links", "memory_id": "missing-memory"},
                )
            )
            assert unknown_memory["result"]["links"] == []

            (workspace / "a.py").write_text(
                "def helper(x):\n"
                "    return x + 1\n"
                "\n"
                "def caller():\n"
                "    return helper(2)\n",
                encoding="utf-8",
            )
            _index(workspace)

            stale = _json_result(
                await call(
                    "memento_code",
                    {"action": "links", "memory_id": target_memory},
                )
            )
            assert stale["result"]["links"]
            assert all(
                link["stale"] and not link["current"]
                for link in stale["result"]["links"]
            )

            no_matches = _json_result(
                await call(
                    "memento_code",
                    {"action": "links", "query": "helper"},
                )
            )
            assert no_matches["result"]["memories"] == []

            stale_stats = _json_result(await call("memento_code", {"action": "stats"}))
            assert stale_stats["result"]["memory_links"] == 0

            locked = await call(
                "memento_configure",
                {"action": "access", "state": "lockdown"},
            )
            assert "lockdown" in _text(locked)
            denied = await call("memento_code", {"action": "stats"})
            assert "Permission denied" in _text(denied)
            await call(
                "memento_configure",
                {"action": "access", "state": "read-write"},
            )

            settings = json.loads(
                (workspace / ".memento" / "settings.json").read_text(encoding="utf-8")
            )
            assert settings["autonomy"]["level"] == "off"


@pytest.mark.asyncio
async def test_memento_code_over_mcp_stdio(tmp_path):
    workspace = _prepare_workspace(tmp_path)
    await asyncio.wait_for(_exercise_server(workspace), timeout=60)
