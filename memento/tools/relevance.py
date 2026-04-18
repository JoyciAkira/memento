"""MCP tools for relevance tracking."""

import json
import logging

from mcp.types import Tool, TextContent

from memento.registry import registry

logger = logging.getLogger("memento-mcp")


@registry.register(
    Tool(
        name="memento_get_relevance_stats",
        description="Get memory relevance statistics — hot/cold memory distribution, hit counts, and decay metrics.",
        inputSchema={"type": "object", "properties": {}},
    )
)
async def memento_get_relevance_stats(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot read stats. Current access state is: {access_manager.state}")

    from memento.relevance import RelevanceTracker

    tracker = RelevanceTracker(db_path=ctx.db_path)
    stats = await tracker.get_stats()
    return [TextContent(type="text", text=f"Relevance stats:\n{json.dumps(stats, indent=2)}")]


@registry.register(
    Tool(
        name="memento_record_memory_hit",
        description="Manually record that specific memories were accessed/used. Boosts their relevance.",
        inputSchema={
            "type": "object",
            "properties": {
                "memory_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of memory IDs to record hits for.",
                }
            },
            "required": ["memory_ids"],
        },
    )
)
async def memento_record_memory_hit(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_write():
        raise PermissionError(f"Cannot record hits. Current access state is: {access_manager.state}")

    from memento.relevance import RelevanceTracker

    memory_ids = arguments.get("memory_ids", [])
    tracker = RelevanceTracker(db_path=ctx.db_path)
    await tracker.record_hits(memory_ids)
    return [TextContent(type="text", text=f"Recorded hits for {len(memory_ids)} memories.")]
