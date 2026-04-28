import asyncio
import pytest
from mcp.types import Tool
from memento.registry import ToolRegistry


class TestRegistry:
    def test_register_adds_tool(self):
        reg = ToolRegistry()
        tool = Tool(name="test_tool", description="A test tool", inputSchema={"type": "object", "properties": {}})

        @reg.register(tool)
        async def handler(args, ctx, access_manager):
            return []

        names = [t.name for t in reg.get_tools()]
        assert "test_tool" in names

    def test_unknown_tool_raises(self):
        reg = ToolRegistry()
        with pytest.raises(ValueError, match="Unknown tool"):
            asyncio.run(reg.execute("nonexistent_tool", {}, None))

    def test_get_tools_returns_all(self):
        reg = ToolRegistry()

        @reg.register(Tool(name="tool_a", description="A", inputSchema={"type": "object", "properties": {}}))
        async def a(args, ctx, access_manager): pass

        @reg.register(Tool(name="tool_b", description="B", inputSchema={"type": "object", "properties": {}}))
        async def b(args, ctx, access_manager): pass

        names = [t.name for t in reg.get_tools()]
        assert "tool_a" in names
        assert "tool_b" in names
