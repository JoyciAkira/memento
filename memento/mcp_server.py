import logging
import asyncio
import os
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from memento.access_manager import MementoAccessManager
from memento.workspace_context import get_workspace_context
from memento.ui_server import start_ui_server_thread

from memento.registry import registry
import memento.tools  # Trigger tool registration
from memento.tools.utils import find_project_root, get_active_goals

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("memento-mcp")

app = Server("memento-mcp")

access_manager = MementoAccessManager()

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
    
    return await registry.execute(name, arguments, ctx, access_manager=access_manager)

async def run():
    logger.info("Starting Memento MCP server via stdio")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

def main():
    asyncio.run(run())

if __name__ == "__main__":
    main()
