"""MCP tools for predictive cache."""

import json
import logging

from mcp.types import Tool, TextContent

from memento.registry import registry

logger = logging.getLogger("memento-mcp")


@registry.register(
    Tool(
        name="memento_warm_predictive_cache",
        description="Pre-warm the predictive cache by searching for related memories given text context. Useful before starting work on a task.",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The context text to search for related memories.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of related memories to cache. Default: 5.",
                },
            },
            "required": ["text"],
        },
    )
)
async def memento_warm_predictive_cache(
    arguments: dict, ctx, access_manager
) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(
            f"Cannot read predictive cache. Current access state is: {access_manager.state}"
        )

    from memento.predictive_cache import PredictiveCache

    text = arguments.get("text", "")
    limit = int(arguments.get("limit", 5))

    try:
        cache = PredictiveCache(db_path=ctx.db_path, provider=ctx.provider)
        result = await cache.warm_for_context(text, limit)
        formatted = json.dumps(result, indent=2, ensure_ascii=False)
        return [TextContent(type="text", text=f"Cache warmed:\n{formatted}")]
    except Exception as e:
        logger.error(f"Error warming predictive cache: {e}")
        return [
            TextContent(type="text", text=f"Error warming predictive cache: {str(e)}")
        ]


@registry.register(
    Tool(
        name="memento_get_predictive_cache_stats",
        description="Get predictive cache statistics — hit rate, cache size, and TTL info.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    )
)
async def memento_get_predictive_cache_stats(
    arguments: dict, ctx, access_manager
) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(
            f"Cannot read cache stats. Current access state is: {access_manager.state}"
        )

    from memento.predictive_cache import PredictiveCache

    try:
        cache = PredictiveCache(db_path=ctx.db_path)
        stats = cache.cache_stats()
        formatted = json.dumps(stats, indent=2, ensure_ascii=False)
        return [TextContent(type="text", text=f"Cache stats:\n{formatted}")]
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        return [
            TextContent(type="text", text=f"Error getting cache stats: {str(e)}")
        ]
