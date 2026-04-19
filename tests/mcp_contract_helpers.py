"""Helper per assert contrattuali su risposte MCP (`list[TextContent]`)."""

from __future__ import annotations

import json
from typing import Any

from mcp.types import TextContent

# Tool il cui primo blocco è JSON object (success path negli smoke/bench offline).
_JSON_OBJECT_CONTRACTS: dict[str, frozenset[str]] = {
    "memento_search_vnext": frozenset({"query", "results"}),
    "memento_explain_retrieval": frozenset({"query", "traces"}),
    "memento_set_goals": frozenset({"batch_id", "inserted_ids", "mode", "context"}),
    "memento_migrate_workspace_memories": frozenset(
        {"seen_total", "copied_total", "unassigned_total", "ambiguous_total"}
    ),
}


def assert_mcp_text_response(out: Any) -> None:
    assert isinstance(out, list), "output MCP deve essere list[TextContent]"
    assert len(out) >= 1, "output MCP non vuoto"
    for block in out:
        assert isinstance(block, TextContent), type(block)
        assert isinstance(block.text, str)


def validate_tool_response_contract(
    tool_name: str,
    out: Any,
    *,
    strict_search_trace: bool = False,
) -> None:
    """Verifica forma MCP +, per tool noti, JSON con chiavi minime.

    Per ``memento_explain_search``, ``strict_search_trace=True`` impone che esista
    ``last_search.json`` (nessun ``error: no trace``) e che la traccia contenga ``lanes``
    come scritto da ``NeuroGraphProvider._write_search_trace_file``.
    """
    assert_mcp_text_response(out)
    raw = out[0].text.strip()
    if tool_name == "memento_list_goals":
        data = json.loads(raw)
        assert isinstance(data, list), "memento_list_goals deve serializzare una lista"
        return
    if tool_name == "memento_explain_search":
        data = json.loads(raw)
        assert isinstance(data, dict) and "query" in data
        if strict_search_trace:
            assert data.get("error") != "no trace", (
                "memento_explain_search: atteso last_search.json dopo search_memory; "
                f"payload={data!r}"
            )
            assert "lanes" in data, (
                "memento_explain_search: traccia provider priva di 'lanes' "
                f"(chiavi: {sorted(data.keys())})"
            )
        return
    required = _JSON_OBJECT_CONTRACTS.get(tool_name)
    if not required:
        return
    if tool_name == "memento_search_vnext" and raw.startswith("Error searching vNext"):
        raise AssertionError("memento_search_vnext non deve fallire nello smoke offline atteso")
    data = json.loads(raw)
    assert isinstance(data, dict), f"{tool_name}: atteso oggetto JSON, got {type(data)}"
    missing = required - data.keys()
    assert not missing, f"{tool_name}: chiavi mancanti {sorted(missing)}"
