"""MCP tool for the tree-sitter code index and memory grounding."""

from __future__ import annotations

import json
import os
from typing import Any

from mcp.types import TextContent, Tool

from memento.registry import registry


def _project_root(ctx: Any) -> str:
    grounder = getattr(getattr(ctx, "provider", None), "code_grounder", None)
    if grounder is not None:
        return grounder.project_root
    db_path = str(getattr(getattr(ctx, "provider", None), "db_path", "") or "")
    if db_path and db_path != ":memory:":
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if os.path.basename(db_dir) == ".memento":
            return os.path.dirname(db_dir)
        return db_dir
    return os.getcwd()


@registry.register(
    Tool(
        name="memento_code",
        description=(
            "Inspect the code symbol index and memory grounding. Actions: "
            "graph, links, stats."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["graph", "links", "stats"],
                    "description": "Action to perform.",
                },
                "symbol": {
                    "type": "string",
                    "description": "Symbol name for graph.",
                },
                "file": {
                    "type": "string",
                    "description": "Workspace-relative file for graph.",
                },
                "memory_id": {
                    "type": "string",
                    "description": "Memory ID for links.",
                },
                "query": {
                    "type": "string",
                    "description": "Find grounded memories by symbol or path for links.",
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "description": "Max nodes, edges, or memories to return.",
                },
                "workspace_root": {"type": "string"},
            },
            "required": ["action"],
        },
    )
)
async def memento_code(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot read code index. Access: {access_manager.state}")

    action = arguments.get("action") or "stats"
    limit = max(1, min(int(arguments.get("limit") or 50), 500))
    project_root = _project_root(ctx)

    from memento.code_index import CodeIndex

    if action == "graph":
        result = CodeIndex(project_root).graph(
            symbol=arguments.get("symbol"),
            file=arguments.get("file"),
            limit=limit,
        )
    elif action == "links":
        from memento.code_grounding import MemoryGrounder

        grounder = MemoryGrounder(project_root)
        memory_id = arguments.get("memory_id")
        query = arguments.get("query")
        if memory_id:
            links = grounder.links_for_memories([str(memory_id)])
            result = {
                "memory_id": str(memory_id),
                "links": links.get(str(memory_id), []),
            }
        elif query:
            ids = grounder.memory_ids_for_query(str(query), limit=limit)
            grouped = grounder.links_for_memories(ids)
            result = {
                "query": str(query),
                "memories": [
                    {"memory_id": memory_id, "links": grouped.get(memory_id, [])}
                    for memory_id in ids
                ],
            }
        else:
            result = {"error": "memory_id or query is required for links"}
    else:
        result = CodeIndex(project_root).graph(limit=1)["stats"]

    return [
        TextContent(
            type="text",
            text=json.dumps(
                {"action": action, "result": result},
                indent=2,
                ensure_ascii=False,
            ),
        )
    ]
