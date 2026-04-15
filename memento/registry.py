from typing import Callable, Dict, List, Any, Awaitable
from mcp.types import Tool, TextContent

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

    def get_tools(self) -> List[Tool]:
        """Return a list of all registered tools."""
        return list(self._tools.values())

    async def execute(self, name: str, arguments: dict, ctx: Any, **kwargs) -> List[TextContent]:
        """Execute the handler for the given tool name."""
        if name not in self._handlers:
            raise ValueError(f"Unknown tool: {name}")
        handler = self._handlers[name]
        return await handler(arguments, ctx, **kwargs)

# Global registry instance
registry = ToolRegistry()
