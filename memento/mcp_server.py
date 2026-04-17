import logging
import asyncio
import os

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from memento.workspace_context import get_workspace_context
from memento.ui_server import start_ui_server_thread

from memento.registry import registry
import memento.tools as _memento_tools
from memento.tools.utils import find_project_root, get_active_goals

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("memento-mcp")

app = Server("memento-mcp")

_ui_thread = None
_tool_registration = _memento_tools

@app.list_tools()
async def list_tools() -> list[Tool]:
    return registry.get_tools()

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    workspace_root = arguments.get("workspace_root")
    active_context = arguments.get("active_context")
    if not workspace_root and isinstance(active_context, str) and active_context.strip():
        candidate = os.path.abspath(active_context)
        if os.path.splitext(candidate)[1]:
            candidate = os.path.dirname(candidate)
        workspace_root = find_project_root(candidate)

    workspace_root = workspace_root or os.environ.get("MEMENTO_DIR") or find_project_root(os.getcwd())
    ctx = get_workspace_context(workspace_root)

    global _ui_thread
    ui_enabled = os.environ.get("MEMENTO_UI", "").lower() in ("1", "true", "yes", "on")
    if ui_enabled and _ui_thread is None:
        ui_port = int(os.environ.get("MEMENTO_UI_PORT", "8089"))
        _ui_thread = start_ui_server_thread(
            ctx.enforcement_config,
            lambda max_goals: get_active_goals(ctx, max_goals=max_goals),
            ctx.provider,
            port=ui_port,
            active_coercion=ctx.active_coercion,
        )
    
    return await registry.execute(name, arguments, ctx, access_manager=ctx.access_manager)

async def run():
    logger.info("Starting Memento MCP server via stdio")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

def main():
    asyncio.run(run())

if __name__ == "__main__":
    main()
