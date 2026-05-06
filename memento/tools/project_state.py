import json
import logging

from mcp.types import Tool, TextContent

from memento.registry import registry

logger = logging.getLogger("memento-mcp")


@registry.register(
    Tool(
        name="memento_set_project_state",
        description=(
            "Set a project state field. Use for vision, milestones, blockers, tech_debt, decisions, current_sprint. "
            "Values can be strings, dicts, or lists of dicts with 'title' and 'status' fields."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "State key (e.g. vision, milestones, blockers, tech_debt, decisions, current_sprint)",
                },
                "value": {
                    "type": "string",
                    "description": "JSON string or plain text value for the state field",
                },
                "workspace_root": {"type": "string"},
            },
            "required": ["key", "value"],
        },
    )
)
async def memento_set_project_state(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_write():
        raise PermissionError(f"Cannot set project state. Access: {access_manager.state}")
    key = arguments.get("key")
    raw = arguments.get("value", "")
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        value = raw
    await ctx.project_state.set(key, value)
    return [TextContent(type="text", text=f"Project state '{key}' updated.")]


@registry.register(
    Tool(
        name="memento_get_project_state",
        description="Get the full project state (vision, milestones, blockers, tech_debt, decisions, sprint).",
        inputSchema={"type": "object", "properties": {"workspace_root": {"type": "string"}}},
    )
)
async def memento_get_project_state(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot read project state. Access: {access_manager.state}")
    state = await ctx.project_state.list_all()
    return [TextContent(type="text", text=json.dumps(state, indent=2, ensure_ascii=False))]


@registry.register(
    Tool(
        name="memento_delete_project_state",
        description="Delete a project state field by key.",
        inputSchema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "State key to delete"},
                "workspace_root": {"type": "string"},
            },
            "required": ["key"],
        },
    )
)
async def memento_delete_project_state(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_write():
        raise PermissionError(f"Cannot delete project state. Access: {access_manager.state}")
    key = arguments.get("key")
    deleted = await ctx.project_state.delete(key)
    return [TextContent(type="text", text=f"Project state '{key}' {'deleted' if deleted else 'not found'}.")]


@registry.register(
    Tool(
        name="memento_project_state_summary",
        description="Get a human-readable summary of the project state for context injection into prompts.",
        inputSchema={"type": "object", "properties": {"workspace_root": {"type": "string"}}},
    )
)
async def memento_project_state_summary(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot read project state. Access: {access_manager.state}")
    summary = await ctx.project_state.get_summary()
    return [TextContent(type="text", text=summary or "No project state defined. Use memento_set_project_state to set vision, milestones, etc.")]
