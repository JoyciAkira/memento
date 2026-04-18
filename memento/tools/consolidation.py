"""
consolidation.py — MCP tools for memory consolidation.
"""

import json
import logging

from mcp.types import Tool, TextContent

from memento.registry import registry

logger = logging.getLogger("memento-mcp")


@registry.register(
    Tool(
        name="memento_consolidate_memories",
        description="Detect semantically similar memories and merge them into enriched, deduplicated memories. Runs a full consolidation cycle.",
        inputSchema={
            "type": "object",
            "properties": {
                "threshold": {
                    "type": "number",
                    "description": "Similarity threshold (0.0-1.0). Memories above this cosine similarity will be merged. Default: 0.92.",
                },
                "min_age_hours": {
                    "type": "number",
                    "description": "Minimum age in hours for memories to be eligible for consolidation. Default: 1.",
                },
                "batch_size": {
                    "type": "integer",
                    "description": "Maximum number of memories to analyze in one consolidation run. Default: 200.",
                },
            },
        },
    )
)
async def memento_consolidate_memories(
    arguments: dict, ctx, access_manager
) -> list[TextContent]:
    if not access_manager.can_write():
        raise PermissionError(
            f"Cannot consolidate. Current access state is: {access_manager.state}"
        )

    from memento.consolidation import ConsolidationEngine

    threshold = float(arguments.get("threshold", 0.92))
    min_age_hours = float(arguments.get("min_age_hours", 1))
    batch_size = int(arguments.get("batch_size", 200))

    try:
        engine = ConsolidationEngine(
            db_path=ctx.provider.db_path,
            threshold=threshold,
            min_age_hours=min_age_hours,
            batch_size=batch_size,
        )
        result = await engine.consolidate()
        formatted = json.dumps(result, indent=2, ensure_ascii=False)
        return [TextContent(type="text", text=f"Consolidation complete:\n{formatted}")]
    except Exception as e:
        logger.error(f"Error during consolidation: {e}")
        return [
            TextContent(type="text", text=f"Error during consolidation: {str(e)}")
        ]


@registry.register(
    Tool(
        name="memento_toggle_consolidation_scheduler",
        description="Start or stop the automatic background memory consolidation scheduler.",
        inputSchema={
            "type": "object",
            "properties": {
                "enabled": {
                    "type": "boolean",
                    "description": "True to start, False to stop.",
                },
                "interval_minutes": {
                    "type": "number",
                    "description": "How often to run consolidation (in minutes). Default: 30.",
                },
            },
            "required": ["enabled"],
        },
    )
)
async def memento_toggle_consolidation_scheduler(
    arguments: dict, ctx, access_manager
) -> list[TextContent]:
    if not access_manager.can_write():
        raise PermissionError(
            f"Cannot modify scheduler. Current access state is: {access_manager.state}"
        )

    enabled = arguments.get("enabled", False)
    interval_minutes = float(arguments.get("interval_minutes", 30.0))

    if enabled:
        if (
            ctx.consolidation_scheduler
            and ctx.consolidation_scheduler.is_running
        ):
            return [
                TextContent(
                    type="text",
                    text=f"Consolidation scheduler already running (interval: {interval_minutes}m).",
                )
            ]

        from memento.consolidation_scheduler import ConsolidationScheduler

        async def do_consolidate():
            return await ctx.provider.consolidate()

        scheduler = ConsolidationScheduler(
            consolidate_fn=do_consolidate,
            interval_minutes=interval_minutes,
            initial_delay_minutes=5.0,
        )
        scheduler.start()
        ctx.consolidation_scheduler = scheduler
        return [
            TextContent(
                type="text",
                text=f"Consolidation scheduler started. Interval: {interval_minutes}m, initial delay: 5m.",
            )
        ]
    else:
        if ctx.consolidation_scheduler and ctx.consolidation_scheduler.is_running:
            ctx.consolidation_scheduler.stop()
            return [TextContent(type="text", text="Consolidation scheduler stopped.")]
        return [
            TextContent(type="text", text="Consolidation scheduler is not running.")
        ]
