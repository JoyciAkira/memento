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
from memento.goal_middleware import per_call_goal_check, session_progress_report

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("memento-mcp")

app = Server("memento-mcp")

_ui_thread = None
_tool_registration = _memento_tools


def _auto_checkpoint_every_n() -> int:
    try:
        return max(int(os.environ.get("MEMENTO_HANDOFF_AUTO_CHECKPOINT_EVERY_N_EVENTS", "25")), 1)
    except Exception:
        return 25


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

    # Start autonomous agent if configured and not running
    if ctx.autonomy.get("level", "off") != "off" and not ctx.autonomous_agent.is_running:
        try:
            ctx.start_autonomous_agent()
        except Exception:
            pass

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

    await ctx.provider.initialize()
    session_id = await ctx.session_manager.ensure_session()

    # Auto-resume: restore L1 from last checkpoint on first tool call of session
    try:
        event_count = await ctx.session_manager.store.count_events(session_id=session_id)
        if event_count <= 1:
            sessions = await ctx.session_manager.store.list_sessions(limit=5, status="closed")
            for prev in sessions:
                prev_id = prev.get("id")
                if not prev_id or not prev.get("last_checkpoint_at"):
                    continue
                prev_row = await ctx.session_manager.store.get_session(prev_id)
                if not prev_row or not prev_row.checkpoint_data:
                    continue
                import json as _json
                data = _json.loads(prev_row.checkpoint_data) if prev_row.checkpoint_data else {}
                l1_items = data.get("l1") if isinstance(data, dict) else []
                if l1_items:
                    try:
                        ctx.provider.orchestrator.l1.restore(l1_items)
                    except Exception:
                        pass
                break
    except Exception:
        pass

    is_error = False
    out: list[TextContent] = []
    try:
        out = await registry.execute(name, arguments, ctx, access_manager=ctx.access_manager)

        # Goal-driven middleware: lightweight awareness check on relevant tool calls
        try:
            warning = await per_call_goal_check(
                tool_name=name,
                arguments=arguments,
                ctx=ctx,
                session_id=session_id,
            )
            if warning:
                out.append(TextContent(type="text", text=f"\n{warning}"))
        except Exception:
            pass

        return out
    except Exception:
        is_error = True
        raise
    finally:
        try:
            active_context_val = arguments.get("active_context") if isinstance(arguments, dict) else None
            result_text = "\n".join(
                c.text
                for c in out
                if getattr(c, "type", None) == "text" and isinstance(getattr(c, "text", None), str)
            )
            await ctx.session_manager.store.append_tool_event(
                session_id=session_id,
                tool_name=name,
                arguments=arguments if isinstance(arguments, dict) else {},
                result_text=result_text,
                is_error=is_error,
                active_context=active_context_val if isinstance(active_context_val, str) else None,
            )

            n = _auto_checkpoint_every_n()
            cnt = await ctx.session_manager.store.count_events(session_id=session_id)
            if cnt > 0 and cnt % n == 0:
                await ctx.session_manager.create_checkpoint(session_id=session_id, reason="auto")

            # Session progress report every 3 auto-checkpoints
            if cnt > 0 and cnt % (n * 3) == 0:
                try:
                    progress = await session_progress_report(ctx=ctx, session_id=session_id)
                    if progress:
                        logger.info(progress)
                except Exception:
                    pass
        except Exception:
            pass

async def run():
    logger.info("Starting Memento MCP server via stdio")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

def main():
    asyncio.run(run())

if __name__ == "__main__":
    main()
