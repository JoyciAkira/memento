import json
import logging

from mcp.types import Tool, TextContent

from memento.registry import registry

logger = logging.getLogger("memento-mcp")


@registry.register(
    Tool(
        name="memento_begin_session",
        description="Start a new Memento session for this workspace (closes any active session).",
        inputSchema={"type": "object", "properties": {"workspace_root": {"type": "string"}}},
    )
)
async def memento_begin_session(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_write():
        raise PermissionError(f"Cannot begin session. Current access state is: {access_manager.state}")
    await ctx.session_manager.store.close_active_sessions()
    sid = await ctx.session_manager.store.ensure_active_session()
    return [TextContent(type="text", text=json.dumps({"session_id": sid}, ensure_ascii=False))]


@registry.register(
    Tool(
        name="memento_handoff",
        description="Create a checkpoint and generate an LLM-agnostic handoff prompt for continuing in a new chat.",
        inputSchema={
            "type": "object",
            "properties": {"workspace_root": {"type": "string"}, "reason": {"type": "string"}},
        },
    )
)
async def memento_handoff(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot read handoff. Current access state is: {access_manager.state}")
    sid = await ctx.session_manager.ensure_session()
    reason = arguments.get("reason") or "manual"
    await ctx.session_manager.create_checkpoint(session_id=sid, reason=str(reason))
    row = await ctx.session_manager.store.get_session(sid)
    prompt = row.handoff_prompt if row else None
    return [TextContent(type="text", text=prompt or "")]


@registry.register(
    Tool(
        name="memento_resume_session",
        description="Resume from a previous session_id by restoring its checkpoint (including L1) and opening a new active session.",
        inputSchema={
            "type": "object",
            "properties": {"workspace_root": {"type": "string"}, "session_id": {"type": "string"}},
            "required": ["session_id"],
        },
    )
)
async def memento_resume_session(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_write():
        raise PermissionError(f"Cannot resume session. Current access state is: {access_manager.state}")
    session_id = arguments.get("session_id")
    out = await ctx.session_manager.resume_from(session_id=str(session_id))
    return [TextContent(type="text", text=json.dumps(out, ensure_ascii=False))]


@registry.register(
    Tool(
        name="memento_list_sessions",
        description="List recent sessions for the current workspace.",
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_root": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
                "status": {"type": "string"},
            },
        },
    )
)
async def memento_list_sessions(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot list sessions. Current access state is: {access_manager.state}")
    limit = int(arguments.get("limit") or 20)
    status = arguments.get("status")
    out = await ctx.session_manager.store.list_sessions(limit=limit, status=status)
    return [TextContent(type="text", text=json.dumps(out, ensure_ascii=False, indent=2))]


@registry.register(
    Tool(
        name="memento_session_status",
        description="Show status for the current active session in this workspace.",
        inputSchema={"type": "object", "properties": {"workspace_root": {"type": "string"}}},
    )
)
async def memento_session_status(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot read session status. Current access state is: {access_manager.state}")
    sid = await ctx.session_manager.ensure_session()
    row = await ctx.session_manager.store.get_session(sid)
    out = {
        "session_id": sid,
        "status": row.status if row else None,
        "started_at": row.started_at if row else None,
        "last_event_at": row.last_event_at if row else None,
        "last_checkpoint_at": row.last_checkpoint_at if row else None,
    }
    return [TextContent(type="text", text=json.dumps(out, ensure_ascii=False, indent=2))]

