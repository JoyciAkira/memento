"""MCP tools for KG auto-extraction."""

import json
import logging

from mcp.types import Tool, TextContent
from memento.registry import registry

logger = logging.getLogger("memento-mcp")


@registry.register(
    Tool(
        name="memento_extract_kg",
        description="Extract entities and relationships from unprocessed memories and populate the knowledge graph using LLM.",
        inputSchema={
            "type": "object",
            "properties": {
                "max_memories": {
                    "type": "integer",
                    "description": "Maximum memories to process. Default: 50.",
                },
            },
        },
    )
)
async def memento_extract_kg(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_write():
        raise PermissionError(f"Cannot extract KG. Current access state is: {access_manager.state}")

    if not ctx.provider._initialized:
        await ctx.provider.initialize()

    max_memories = int(arguments.get("max_memories", 50))

    try:
        result = await ctx.provider.extract_kg(max_memories=max_memories)
        formatted = json.dumps(result, indent=2, ensure_ascii=False)
        return [TextContent(type="text", text=f"KG extraction complete:\n{formatted}")]
    except Exception as e:
        logger.error(f"KG extraction error: {e}")
        return [TextContent(type="text", text=f"KG extraction error: {str(e)}")]


@registry.register(
    Tool(
        name="memento_toggle_kg_extraction_scheduler",
        description="Start or stop the background KG auto-extraction scheduler.",
        inputSchema={
            "type": "object",
            "properties": {
                "enabled": {
                    "type": "boolean",
                    "description": "True to start, False to stop.",
                },
                "interval_minutes": {
                    "type": "number",
                    "description": "Run interval in minutes. Default: 60.",
                },
            },
            "required": ["enabled"],
        },
    )
)
async def memento_toggle_kg_extraction_scheduler(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_write():
        raise PermissionError(f"Cannot modify scheduler. Current access state is: {access_manager.state}")

    enabled = arguments.get("enabled", False)
    interval_minutes = float(arguments.get("interval_minutes", 60.0))

    if enabled:
        if ctx.kg_extraction_scheduler and ctx.kg_extraction_scheduler.is_running:
            return [TextContent(type="text", text="KG extraction scheduler already running.")]

        if not ctx.provider._initialized:
            await ctx.provider.initialize()

        from memento.kg_extraction_scheduler import KGExtractionScheduler

        async def do_extract():
            return await ctx.provider.extract_kg(max_memories=50)

        scheduler = KGExtractionScheduler(
            extraction_fn=do_extract,
            interval_minutes=interval_minutes,
            initial_delay_minutes=10.0,
        )
        scheduler.start()
        ctx.kg_extraction_scheduler = scheduler
        return [TextContent(type="text", text=f"KG extraction scheduler started. Interval: {interval_minutes}m.")]
    else:
        if ctx.kg_extraction_scheduler and ctx.kg_extraction_scheduler.is_running:
            ctx.kg_extraction_scheduler.stop()
            return [TextContent(type="text", text="KG extraction scheduler stopped.")]
        return [TextContent(type="text", text="KG extraction scheduler is not running.")]
