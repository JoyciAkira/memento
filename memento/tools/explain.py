import json
import os

from mcp.types import Tool, TextContent

from memento.registry import registry


@registry.register(
    Tool(
        name="memento_explain_search",
        description="Return the last retrieval trace for a given query (best-effort, local-only).",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    )
)
async def memento_explain_search(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot read memory. Current access state is: {access_manager.state}")

    query = arguments.get("query") or ""
    trace_path = os.path.join(ctx.workspace_root, ".memento", "traces", "last_search.json")
    if not os.path.exists(trace_path):
        return [
            TextContent(
                type="text",
                text=json.dumps({"query": query, "error": "no trace"}, indent=2, ensure_ascii=False),
            )
        ]

    with open(trace_path, "r") as f:
        payload = json.load(f)
    return [TextContent(type="text", text=json.dumps(payload, indent=2, ensure_ascii=False))]

