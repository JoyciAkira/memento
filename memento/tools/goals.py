import json
import logging

from mcp.types import Tool, TextContent

from memento.registry import registry

logger = logging.getLogger("memento-mcp")


@registry.register(
    Tool(
        name="memento_set_goals",
        description="Set active goals (first-class). Replaces existing goals by default and stores the reason.",
        inputSchema={
            "type": "object",
            "properties": {
                "goals": {"type": "array", "items": {"type": "string"}},
                "context": {"type": "string"},
                "mode": {"type": "string", "enum": ["replace", "append"], "default": "replace"},
                "delete_reason": {"type": "string"},
            },
            "required": ["goals"],
        },
    )
)
async def memento_set_goals(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_write():
        raise PermissionError(f"Cannot set goals. Current access state is: {access_manager.state}")

    goals = arguments.get("goals") or []
    context = arguments.get("context")
    mode = arguments.get("mode") or "replace"
    delete_reason = arguments.get("delete_reason") or "replaced"

    try:
        out = await ctx.provider.set_goals(
            goals=goals,
            context=context,
            mode=mode,
            delete_reason=delete_reason,
        )
        return [TextContent(type="text", text=json.dumps(out, indent=2, ensure_ascii=False))]
    except Exception as e:
        logger.error(f"Error setting goals: {e}")
        return [TextContent(type="text", text=f"Error setting goals: {str(e)}")]


@registry.register(
    Tool(
        name="memento_list_goals",
        description="List goals (first-class).",
        inputSchema={
            "type": "object",
            "properties": {
                "active_only": {"type": "boolean", "default": True},
                "context": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
                "offset": {"type": "integer", "default": 0},
            },
        },
    )
)
async def memento_list_goals(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot read goals. Current access state is: {access_manager.state}")

    active_only = bool(arguments.get("active_only", True))
    context = arguments.get("context")
    limit = int(arguments.get("limit") or 50)
    offset = int(arguments.get("offset") or 0)

    out = await ctx.provider.list_goals(context=context, active_only=active_only, limit=limit, offset=offset)
    return [TextContent(type="text", text=json.dumps(out, indent=2, ensure_ascii=False))]
