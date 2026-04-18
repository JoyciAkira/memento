"""MCP tools for quality metrics."""

import json
import logging
import os

from mcp.types import Tool, TextContent
from memento.registry import registry

logger = logging.getLogger("memento-mcp")


@registry.register(
    Tool(
        name="memento_system_health",
        description="Get a comprehensive health report for the Memento memory system — memory stats, KG health, consolidation and extraction metrics.",
        inputSchema={"type": "object", "properties": {}},
    )
)
async def memento_system_health(arguments: dict, ctx, access_manager) -> list[TextContent]:
    from memento.quality_metrics import QualityMetrics

    kg_db_path = None
    if hasattr(ctx, "provider") and hasattr(ctx.provider, "kg") and hasattr(ctx.provider.kg, "kg"):
        kg_db_path = ctx.provider.kg.kg.db_path

    metrics = QualityMetrics(db_path=ctx.db_path, kg_db_path=kg_db_path)
    report = await metrics.system_health()
    return [TextContent(type="text", text=f"System Health Report:\n{json.dumps(report, indent=2)}")]


@registry.register(
    Tool(
        name="memento_memory_stats",
        description="Get detailed memory statistics — counts, age distribution, user distribution.",
        inputSchema={"type": "object", "properties": {}},
    )
)
async def memento_memory_stats(arguments: dict, ctx, access_manager) -> list[TextContent]:
    from memento.quality_metrics import QualityMetrics
    metrics = QualityMetrics(db_path=ctx.db_path)
    stats = await metrics.memory_stats()
    return [TextContent(type="text", text=f"Memory stats:\n{json.dumps(stats, indent=2)}")]


@registry.register(
    Tool(
        name="memento_kg_health",
        description="Get knowledge graph health — entity/triple counts, predicate distribution, temporal coverage.",
        inputSchema={"type": "object", "properties": {}},
    )
)
async def memento_kg_health(arguments: dict, ctx, access_manager) -> list[TextContent]:
    from memento.quality_metrics import QualityMetrics

    kg_db_path = None
    if hasattr(ctx, "provider") and hasattr(ctx.provider, "kg") and hasattr(ctx.provider.kg, "kg"):
        kg_db_path = ctx.provider.kg.kg.db_path

    metrics = QualityMetrics(db_path=ctx.db_path, kg_db_path=kg_db_path)
    health = await metrics.kg_health()
    return [TextContent(type="text", text=f"KG health:\n{json.dumps(health, indent=2)}")]


@registry.register(
    Tool(
        name="memento_get_quality_report",
        description="Get a full quality report for the Memento memory system — health score, coverage analysis, stale and orphan memories.",
        inputSchema={"type": "object", "properties": {}},
    )
)
async def memento_get_quality_report(
    arguments: dict, ctx, access_manager
) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(
            f"Cannot read quality report. Current access state is: {access_manager.state}"
        )

    from memento.quality_metrics import QualityMetrics

    metrics = QualityMetrics(db_path=ctx.db_path)
    report = await metrics.get_quality_report()
    return [
        TextContent(
            type="text",
            text=f"Quality Report:\n{json.dumps(report, indent=2, ensure_ascii=False)}",
        )
    ]


@registry.register(
    Tool(
        name="memento_record_quality_evaluation",
        description="Record a quality evaluation score for a specific memory. Score should be 0-1.",
        inputSchema={
            "type": "object",
            "properties": {
                "memory_id": {
                    "type": "string",
                    "description": "The ID of the memory to evaluate.",
                },
                "score": {
                    "type": "number",
                    "description": "Quality score from 0 to 1.",
                },
                "reason": {
                    "type": "string",
                    "description": "Optional reason for the evaluation.",
                },
            },
            "required": ["memory_id", "score"],
        },
    )
)
async def memento_record_quality_evaluation(
    arguments: dict, ctx, access_manager
) -> list[TextContent]:
    if not access_manager.can_write():
        raise PermissionError(
            f"Cannot record evaluation. Current access state is: {access_manager.state}"
        )

    from memento.quality_metrics import QualityMetrics

    memory_id = arguments.get("memory_id", "")
    score = float(arguments.get("score", 0))
    reason = arguments.get("reason", "")

    if not memory_id:
        raise ValueError("memory_id is required")
    if not 0 <= score <= 1:
        raise ValueError("score must be between 0 and 1")

    metrics = QualityMetrics(db_path=ctx.db_path)
    await metrics.record_evaluation(memory_id, score, reason)
    return [
        TextContent(
            type="text",
            text=f"Quality evaluation recorded for memory {memory_id}: score={score}",
        )
    ]
