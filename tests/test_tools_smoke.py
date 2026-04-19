import pathlib
import sqlite3
import subprocess
import sys
from datetime import datetime

import pytest

from memento.mcp_server import call_tool, list_tools

_tests_dir = str(pathlib.Path(__file__).resolve().parent)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)
import mcp_contract_helpers as _mcp_contract  # noqa: E402

# ``last_search.json`` è sovrascritto a ogni ``search_*``; ``memento_explain_search`` è validato
# dopo il ciclo con sequenza fissa add → search_memory → explain (strict trace).
_SMOKE_EXPLAIN_ANCHOR = "SMOKE_EXPLAIN_ANCHOR_ZQ9"


def _init_source_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS memories USING fts5(id UNINDEXED, user_id UNINDEXED, text, created_at UNINDEXED, metadata UNINDEXED);"
    )
    conn.execute(
        "INSERT INTO memories (id, user_id, text, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
        ("m1", "default", "", datetime.now().isoformat(), "{}"),
    )
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_all_tools_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")

    ws = tmp_path
    subprocess.run(
        ["git", "init"],
        cwd=str(ws),
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    ws2 = tmp_path / "ws2"
    ws2.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init"],
        cwd=str(ws2),
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    source_db = ws / "source.db"
    _init_source_db(str(source_db))

    conn = sqlite3.connect(str(source_db))
    conn.execute(
        "UPDATE memories SET text=? WHERE id='m1'",
        (f"note about {ws.name} and migration",),
    )
    conn.commit()
    conn.close()

    tools = await list_tools()
    tool_names = [t.name for t in tools]

    payloads = {
        "memento_status": {"workspace_root": str(ws)},
        "memento_toggle_access": {"workspace_root": str(ws), "state": "read-only"},
        "memento_toggle_superpowers": {
            "workspace_root": str(ws),
            "warnings": True,
            "tasks": True,
        },
        "memento_configure_enforcement": {
            "workspace_root": str(ws),
            "level1": False,
            "level2": False,
            "level3": False,
        },
        "memento_add_memory": {
            "workspace_root": str(ws),
            "text": "hello memory",
            "metadata": {},
        },
        "memento_search_memory": {"workspace_root": str(ws), "query": "hello"},
        "memento_explain_search": {
            "workspace_root": str(ws),
            "query": _SMOKE_EXPLAIN_ANCHOR,
        },
        "memento_get_warnings": {"workspace_root": str(ws), "context": "Using sqlite and asyncio"},
        "memento_generate_tasks": {"workspace_root": str(ws)},
        "memento_toggle_dependency_tracker": {"workspace_root": str(ws), "enabled": True},
        "memento_audit_dependencies": {"workspace_root": str(ws)},
        "memento_toggle_active_coercion": {"workspace_root": str(ws), "enabled": True},
        "memento_list_active_coercion_presets": {"workspace_root": str(ws)},
        "memento_apply_active_coercion_preset": {
            "workspace_root": str(ws),
            "preset": "python-dev-basics",
        },
        "memento_list_active_coercion_rules": {"workspace_root": str(ws)},
        "memento_add_active_coercion_rule": {
            "workspace_root": str(ws),
            "id": "no_print",
            "path_globs": ["**/*.py"],
            "kind": "regex",
            "regex": "\\bprint\\(",
            "message": "no print",
        },
        "memento_remove_active_coercion_rule": {"workspace_root": str(ws), "rule_id": "no_print"},
        "memento_install_git_hooks": {"workspace_root": str(ws)},
        "memento_toggle_precognition": {"workspace_root": str(ws), "enabled": False},
        "memento_check_goal_alignment": {"workspace_root": str(ws), "content": "test"},
        "memento_synthesize_dreams": {"workspace_root": str(ws), "context": "test"},
        "memento_migrate_workspace_memories": {
            "workspace_root": str(ws),
            "source_db_path": str(source_db),
            "workspace_roots": [str(ws), str(ws2)],
        },
        "memento": {"workspace_root": str(ws), "query": "list"},
        "memento_consolidate_memories": {"workspace_root": str(ws)},
        "memento_toggle_consolidation_scheduler": {"workspace_root": str(ws), "enabled": False},
        "memento_extract_kg": {"workspace_root": str(ws)},
        "memento_toggle_kg_extraction_scheduler": {"workspace_root": str(ws), "enabled": False},
        "memento_get_relevance_stats": {"workspace_root": str(ws)},
        "memento_record_memory_hit": {"workspace_root": str(ws), "memory_ids": []},
        "memento_warm_predictive_cache": {"workspace_root": str(ws), "text": "test"},
        "memento_get_predictive_cache_stats": {"workspace_root": str(ws)},
        "memento_system_health": {"workspace_root": str(ws)},
        "memento_memory_stats": {"workspace_root": str(ws)},
        "memento_kg_health": {"workspace_root": str(ws)},
        "memento_get_quality_report": {"workspace_root": str(ws)},
        "memento_record_quality_evaluation": {"workspace_root": str(ws), "memory_id": "test", "score": 0.5},
        "memento_share_memory_to_workspace": {"workspace_root": str(ws), "memory_id": "nonexistent", "target_workspace": str(ws2)},
        "memento_get_cross_workspace_stats": {"workspace_root": str(ws)},
        "memento_configure_notifications": {"workspace_root": str(ws)},
        "memento_get_pending_notifications": {"workspace_root": str(ws)},
        "memento_dismiss_notification": {"workspace_root": str(ws), "notification_id": "nonexistent"},
        "memento_set_goals": {"workspace_root": str(ws), "goals": ["smoke: keep CI green"]},
        "memento_list_goals": {"workspace_root": str(ws)},
        "memento_search_vnext": {"workspace_root": str(ws), "query": "smoke"},
        "memento_explain_retrieval": {"workspace_root": str(ws), "query": "smoke"},
    }

    await call_tool("memento_toggle_access", {"workspace_root": str(ws), "state": "read-write"})

    failures: list[tuple[str, str]] = []
    for name in tool_names:
        if name == "memento_explain_search":
            # Il file ``.memento/traces/last_search.json`` è aggiornato ad ogni search;
            # invocare explain_search dentro il loop è non-deterministico rispetto all'ordine
            # dei tool registrati. Si valida in coda con sequenza fissa add → search → explain.
            continue
        args = payloads.get(name, {"workspace_root": str(ws)})
        if name == "memento_toggle_access":
            try:
                out = await call_tool(name, args)
                _mcp_contract.validate_tool_response_contract(name, out)
            except Exception as e:
                failures.append((name, str(e)))
            await call_tool("memento_toggle_access", {"workspace_root": str(ws), "state": "read-write"})
            continue

        try:
            out = await call_tool(name, args)
            _mcp_contract.validate_tool_response_contract(name, out)
        except Exception as e:
            failures.append((name, str(e)))

    try:
        await call_tool(
            "memento_add_memory",
            {
                "workspace_root": str(ws),
                "text": f"smoke explain-search seed {_SMOKE_EXPLAIN_ANCHOR} tail",
                "metadata": {},
            },
        )
        await call_tool(
            "memento_search_memory",
            {"workspace_root": str(ws), "query": _SMOKE_EXPLAIN_ANCHOR},
        )
        out_explain = await call_tool(
            "memento_explain_search",
            {"workspace_root": str(ws), "query": _SMOKE_EXPLAIN_ANCHOR},
        )
        _mcp_contract.validate_tool_response_contract(
            "memento_explain_search",
            out_explain,
            strict_search_trace=True,
        )
    except Exception as e:
        failures.append(("memento_explain_search (post-ciclo)", str(e)))

    assert failures == []

