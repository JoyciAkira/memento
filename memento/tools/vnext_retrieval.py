import json
import logging

from mcp.types import Tool, TextContent

from memento.registry import registry

logger = logging.getLogger("memento-mcp")


@registry.register(
    Tool(
        name="memento_search_vnext",
        description="Search memories using the vNext retrieval pipeline and return a structured bundle.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
                "filters": {"type": "object", "additionalProperties": True},
                "trace": {"type": "boolean", "default": False},
            },
            "required": ["query"],
        },
    )
)
async def memento_search_vnext(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot search memory. Current access state is: {access_manager.state}")

    query = arguments.get("query")
    if not query:
        raise ValueError("Query is required")

    limit = int(arguments.get("limit") or 50)
    filters = arguments.get("filters")
    trace = bool(arguments.get("trace") or False)

    try:
        bundle = await ctx.provider.search_vnext_bundle(
            query=query,
            user_id="default",
            limit=limit,
            filters=filters,
            trace=trace,
        )
        return [TextContent(type="text", text=json.dumps(bundle, indent=2, ensure_ascii=False))]
    except Exception as e:
        logger.error(f"Error searching vNext memory: {e}")
        return [TextContent(type="text", text=f"Error searching vNext memory: {str(e)}")]


@registry.register(
    Tool(
        name="memento_explain_retrieval",
        description="Explain vNext retrieval routing and lane traces for a query.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "filters": {"type": "object", "additionalProperties": True},
            },
            "required": ["query"],
        },
    )
)
async def memento_explain_retrieval(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot search memory. Current access state is: {access_manager.state}")

    query = arguments.get("query")
    if not query:
        raise ValueError("Query is required")

    filters = arguments.get("filters")
    bundle = await ctx.provider.search_vnext_bundle(query=query, user_id="default", limit=10, filters=filters, trace=True)
    payload = {"query": bundle.get("query"), "routing": bundle.get("routing"), "traces": bundle.get("traces")}
    return [TextContent(type="text", text=json.dumps(payload, indent=2, ensure_ascii=False))]
