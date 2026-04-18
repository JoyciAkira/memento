"""MCP tools for cross-workspace memory sharing."""

import json
import logging

from mcp.types import Tool, TextContent

from memento.registry import registry

logger = logging.getLogger("memento-mcp")


@registry.register(
    Tool(
        name="memento_share_memory_to_workspace",
        description="Share a memory with another project workspace for cross-project context.",
        inputSchema={
            "type": "object",
            "properties": {
                "memory_id": {
                    "type": "string",
                    "description": "The memory ID to share.",
                },
                "target_workspace": {
                    "type": "string",
                    "description": "Absolute path to the target workspace root.",
                },
            },
            "required": ["memory_id", "target_workspace"],
        },
    )
)
async def memento_share_memory_to_workspace(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_write():
        raise PermissionError(
            f"Cannot share memory. Current access state is: {access_manager.state}"
        )

    from memento.cross_workspace import CrossWorkspaceManager

    manager = CrossWorkspaceManager(db_path=ctx.db_path)
    result = await manager.share_memory(
        memory_id=arguments["memory_id"],
        target_workspace_path=arguments["target_workspace"],
        source_workspace_path=ctx.workspace_root,
    )

    if "error" in result:
        return [TextContent(type="text", text=f"Error: {result['error']}")]

    return [
        TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False),
        )
    ]


@registry.register(
    Tool(
        name="memento_get_cross_workspace_stats",
        description="Get cross-workspace sync statistics — counts of shared, imported, and pending memories.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    )
)
async def memento_get_cross_workspace_stats(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(
            f"Cannot read stats. Current access state is: {access_manager.state}"
        )

    from memento.cross_workspace import CrossWorkspaceManager

    manager = CrossWorkspaceManager(db_path=ctx.db_path)
    result = await manager.get_sync_stats()

    return [
        TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False),
        )
    ]
