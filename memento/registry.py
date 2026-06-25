from typing import Callable, Dict, List, Any, Awaitable
from mcp.types import Tool, TextContent

# Tools that are explicitly about memory search — skip proactive injection to avoid recursion
_SEARCH_TOOLS = frozenset({"memento", "memento_search", "memento_remember", "memento_health"})

# Delimiter that downstream agents can recognize as untrusted injected context
_PROACTIVE_OPEN  = "<!-- memento:proactive-context -->"
_PROACTIVE_CLOSE = "<!-- /memento:proactive-context -->"

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

    @staticmethod
    def _sanitize_memory(text: str) -> str:
        """Strip control tokens that could be used for prompt injection."""
        import re
        # Remove instruction-like patterns that could hijack the agent
        text = re.sub(r'(?i)(ignore\s+(previous|all|prior)\s+instructions?.*)', '[FILTERED]', text)
        text = re.sub(r'(?i)(system\s*:|<\s*system\s*>|</\s*system\s*>)', '[FILTERED]', text)
        text = re.sub(r'(?i)(you\s+are\s+now\s+a?\s*\w+\s+assistant)', '[FILTERED]', text)
        return text

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
        # Check access manager — respect lockdown/read-only
        access_manager = getattr(ctx, "access_manager", None)
        if access_manager and getattr(access_manager, "_state", "read-write") == "lockdown":
            return ""
        # Enforce workspace filter
        workspace_root = arguments.get("workspace_root")
        filters = {"workspace_root": workspace_root} if workspace_root else None
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
            results = await provider.search(query, limit=_settings.proactive_top_k, filters=filters)
        except Exception:
            return ""
        if not results:
            return ""
        lines = [f"{_PROACTIVE_OPEN}", f"[Proactive context — {len(results)} relevant memories]"]
        for r in results:
            sanitized = self._sanitize_memory(r.get("memory", ""))[:200]
            lines.append(f"• {sanitized}")
        lines.append(_PROACTIVE_CLOSE)
        return "\n".join(lines) + "\n\n"

    async def execute(self, name: str, arguments: dict, ctx: Any, **kwargs) -> List[TextContent]:
        """Execute the handler for the given tool name."""
        if name not in self._handlers:
            raise ValueError(f"Unknown tool: {name}")
        handler = self._handlers[name]
        try:
            result = await handler(arguments, ctx, **kwargs)
        except PermissionError as e:
            return [TextContent(type="text", text=f"Permission denied: {e}")]
        except Exception:
            raise
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
