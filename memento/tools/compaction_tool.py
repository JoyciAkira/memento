"""MCP tool: memento_compact — token-friendly compaction, "a tool like caveman".

Exposes the deterministic compaction engine (memento.compaction) so any client
can compress arbitrary text on demand using the same strategies Memento applies
to its injected context. Dependency-free, no LLM call.
"""

from mcp.types import Tool, TextContent
from memento.registry import registry
from memento.compaction import compact, STRATEGIES


@registry.register(
    Tool(
        name="memento_compact",
        description=(
            "Compress natural-language text to save tokens while preserving technical "
            "substance (code, URLs, file paths). Strategies: "
            f"{', '.join(STRATEGIES)}. 'caveman' applies the MIT-licensed caveman-compress "
            "rule-based tersification; 'truncate' hard-cuts at the token budget; "
            "'graphify'/'ponytail' are native token-light heuristics. No LLM call."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to compact.",
                },
                "strategy": {
                    "type": "string",
                    "enum": list(STRATEGIES),
                    "description": "Compaction strategy (default: caveman).",
                    "default": "caveman",
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Approximate token budget for the output (default: 60).",
                    "default": 60,
                },
            },
            "required": ["text"],
        },
    )
)
async def memento_compact(arguments: dict, ctx, access_manager) -> list[TextContent]:
    text = arguments.get("text", "")
    strategy = str(arguments.get("strategy", "caveman")).lower()
    if strategy not in STRATEGIES:
        strategy = "caveman"
    try:
        max_tokens = int(arguments.get("max_tokens", 60))
    except (TypeError, ValueError):
        max_tokens = 60

    if not text:
        return [TextContent(type="text", text="")]

    out = compact(text, strategy=strategy, max_tokens=max_tokens)
    saved = max(0, len(text) - len(out))
    return [
        TextContent(
            type="text",
            text=f"[compacted · strategy={strategy} · -{saved} chars]\n{out}",
        )
    ]
