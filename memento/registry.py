from typing import Callable, Dict, List, Any, Awaitable
from mcp.types import Tool, TextContent

# Tools that are explicitly about memory search — skip proactive injection to avoid recursion
_SEARCH_TOOLS = frozenset({"memento", "memento_search", "memento_remember", "memento_health"})

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._handlers: Dict[str, Callable[..., Awaitable[List[TextContent]]]] = {}

    def register(self, tool: Tool):
        """Decorator to register a tool and its handler."""
        if "workspace_root" not in tool.inputSchema.get("properties", {}):
            if "properties" not in tool.inputSchema:
                tool.inputSchema["properties"] = {}
            tool.inputSchema["properties"]["workspace_root"] = {
                "type": "string",
                "description": "MANDATORY: The absolute path of the current project/workspace root."
            }

        def decorator(func: Callable[..., Awaitable[List[TextContent]]]):
            self._tools[tool.name] = tool
            self._handlers[tool.name] = func
            return func
        return decorator

    def get_tools(self, include_deprecated: bool = False) -> List[Tool]:
        """Return registered tools, excluding deprecated ones by default."""
        if include_deprecated:
            return list(self._tools.values())
        return [t for t in self._tools.values() if not t.description.startswith("[DEPRECATED]")]

    async def _proactive_context(self, name: str, arguments: dict, ctx: Any) -> str:
        """Build a proactive context block by searching memories relevant to the current call."""
        from memento.settings import settings as _settings
        if not _settings.proactive_inject:
            return ""
        if name in _SEARCH_TOOLS:
            return ""
        provider = getattr(ctx, "provider", None)
        if provider is None:
            return ""
        # Build query from meaningful string arguments
        skip_keys = {"workspace_root", "action"}
        query_parts = [
            str(v) for k, v in arguments.items()
            if k not in skip_keys and isinstance(v, str) and len(v) > 3
        ]
        if not query_parts:
            return ""
        query = " ".join(query_parts)[:300]
        try:
            results = await provider.search(query, limit=_settings.proactive_top_k)
        except Exception:
            return ""
        if not results:
            return ""
        lines = [f"[Proactive context — {len(results)} relevant memories]"]
        for r in results:
            lines.append(f"• {r.get('memory', '')[:200]}")
        return "\n".join(lines) + "\n\n"

    async def execute(self, name: str, arguments: dict, ctx: Any, **kwargs) -> List[TextContent]:
        """Execute the handler for the given tool name."""
        if name not in self._handlers:
            raise ValueError(f"Unknown tool: {name}")
        handler = self._handlers[name]
        result = await handler(arguments, ctx, **kwargs)
        # Prepend proactive memory context to the first TextContent item
        # Skip if the response is JSON (starts with { or [) to avoid breaking parsers
        try:
            prefix = await self._proactive_context(name, arguments, ctx)
            if prefix and result:
                first = result[0]
                if first.text and first.text.lstrip()[:1] not in ("{", "["):
                    result[0] = TextContent(type="text", text=prefix + first.text)
        except Exception:
            pass
        return result

# Global registry instance
registry = ToolRegistry()
