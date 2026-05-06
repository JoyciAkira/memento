import json
import logging

from mcp.types import Tool, TextContent

from memento.registry import registry

logger = logging.getLogger("memento-mcp")


# ---------------------------------------------------------------------------
# memento_project — unified project state & goals
# ---------------------------------------------------------------------------

@registry.register(
    Tool(
        name="memento_project",
        description=(
            "Manage project state and goals. Actions: "
            "set_state, get_state, delete_state, set_goals, list_goals, summary."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "set_state",
                        "get_state",
                        "delete_state",
                        "set_goals",
                        "list_goals",
                        "summary",
                    ],
                    "description": "Action to perform.",
                },
                # set_state / delete_state
                "key": {
                    "type": "string",
                    "description": "State key for set_state / delete_state.",
                },
                "value": {
                    "type": "string",
                    "description": "JSON string or plain text value for set_state.",
                },
                # set_goals / list_goals
                "goals": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Goal strings for set_goals.",
                },
                "context": {"type": "string"},
                "mode": {
                    "type": "string",
                    "enum": ["replace", "append"],
                    "default": "replace",
                },
                "delete_reason": {"type": "string"},
                "active_only": {"type": "boolean", "default": True},
                "limit": {"type": "integer", "default": 50},
                "offset": {"type": "integer", "default": 0},
                # common
                "workspace_root": {"type": "string"},
            },
            "required": ["action"],
        },
    )
)
async def memento_project(arguments: dict, ctx, access_manager) -> list[TextContent]:
    action = arguments["action"]

    # -- set_state -----------------------------------------------------------
    if action == "set_state":
        if not access_manager.can_write():
            raise PermissionError(f"Cannot set project state. Access: {access_manager.state}")
        key = arguments.get("key")
        raw = arguments.get("value", "")
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            value = raw
        await ctx.project_state.set(key, value)
        return [TextContent(type="text", text=f"Project state '{key}' updated.")]

    # -- get_state -----------------------------------------------------------
    if action == "get_state":
        if not access_manager.can_read():
            raise PermissionError(f"Cannot read project state. Access: {access_manager.state}")
        state = await ctx.project_state.list_all()
        return [TextContent(type="text", text=json.dumps(state, indent=2, ensure_ascii=False))]

    # -- delete_state --------------------------------------------------------
    if action == "delete_state":
        if not access_manager.can_write():
            raise PermissionError(f"Cannot delete project state. Access: {access_manager.state}")
        key = arguments.get("key")
        deleted = await ctx.project_state.delete(key)
        return [TextContent(type="text", text=f"Project state '{key}' {'deleted' if deleted else 'not found'}.")]

    # -- set_goals -----------------------------------------------------------
    if action == "set_goals":
        if not access_manager.can_write():
            raise PermissionError(f"Cannot set goals. Current access state is: {access_manager.state}")
        goals = arguments.get("goals") or []
        context = arguments.get("context")
        mode = arguments.get("mode") or "replace"
        delete_reason = arguments.get("delete_reason") or "replaced"
        try:
            out = await ctx.provider.set_goals(
                goals=goals,
                context=context,
                mode=mode,
                delete_reason=delete_reason,
            )
            return [TextContent(type="text", text=json.dumps(out, indent=2, ensure_ascii=False))]
        except Exception as e:
            logger.error(f"Error setting goals: {e}")
            return [TextContent(type="text", text=f"Error setting goals: {str(e)}")]

    # -- list_goals ----------------------------------------------------------
    if action == "list_goals":
        if not access_manager.can_read():
            raise PermissionError(f"Cannot read goals. Current access state is: {access_manager.state}")
        active_only = bool(arguments.get("active_only", True))
        context = arguments.get("context")
        limit = int(arguments.get("limit") or 50)
        offset = int(arguments.get("offset") or 0)
        out = await ctx.provider.list_goals(
            context=context, active_only=active_only, limit=limit, offset=offset,
        )
        return [TextContent(type="text", text=json.dumps(out, indent=2, ensure_ascii=False))]

    # -- summary -------------------------------------------------------------
    if action == "summary":
        if not access_manager.can_read():
            raise PermissionError(f"Cannot read project state. Access: {access_manager.state}")
        summary = await ctx.project_state.get_summary()
        return [
            TextContent(
                type="text",
                text=summary or "No project state defined. Use set_state to set vision, milestones, etc.",
            )
        ]

    return [TextContent(type="text", text=f"Unknown action: {action}")]


# ---------------------------------------------------------------------------
# memento_session — unified session management
# ---------------------------------------------------------------------------

@registry.register(
    Tool(
        name="memento_session",
        description=(
            "Manage Memento sessions. Actions: "
            "begin, resume, handoff, status, list."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["begin", "resume", "handoff", "status", "list"],
                    "description": "Action to perform.",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session ID for resume.",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for handoff checkpoint.",
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                },
                "status_filter": {
                    "type": "string",
                    "description": "Filter sessions by status.",
                },
                "workspace_root": {"type": "string"},
            },
            "required": ["action"],
        },
    )
)
async def memento_session(arguments: dict, ctx, access_manager) -> list[TextContent]:
    action = arguments["action"]

    # -- begin ---------------------------------------------------------------
    if action == "begin":
        if not access_manager.can_write():
            raise PermissionError(f"Cannot begin session. Current access state is: {access_manager.state}")
        await ctx.session_manager.store.close_active_sessions()
        sid = await ctx.session_manager.store.ensure_active_session()
        return [TextContent(type="text", text=json.dumps({"session_id": sid}, ensure_ascii=False))]

    # -- resume --------------------------------------------------------------
    if action == "resume":
        if not access_manager.can_write():
            raise PermissionError(f"Cannot resume session. Current access state is: {access_manager.state}")
        session_id = arguments.get("session_id")
        if not session_id:
            return [TextContent(type="text", text="Error: session_id is required for resume.")]
        out = await ctx.session_manager.resume_from(session_id=str(session_id))
        return [TextContent(type="text", text=json.dumps(out, ensure_ascii=False))]

    # -- handoff -------------------------------------------------------------
    if action == "handoff":
        if not access_manager.can_read():
            raise PermissionError(f"Cannot read handoff. Current access state is: {access_manager.state}")
        sid = await ctx.session_manager.ensure_session()
        reason = arguments.get("reason") or "manual"
        await ctx.session_manager.create_checkpoint(session_id=sid, reason=str(reason))
        row = await ctx.session_manager.store.get_session(sid)
        prompt = row.handoff_prompt if row else None
        return [TextContent(type="text", text=prompt or "")]

    # -- status --------------------------------------------------------------
    if action == "status":
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

    # -- list ----------------------------------------------------------------
    if action == "list":
        if not access_manager.can_read():
            raise PermissionError(f"Cannot list sessions. Current access state is: {access_manager.state}")
        limit = int(arguments.get("limit") or 20)
        status_filter = arguments.get("status_filter")
        out = await ctx.session_manager.store.list_sessions(limit=limit, status=status_filter)
        return [TextContent(type="text", text=json.dumps(out, ensure_ascii=False, indent=2))]

    return [TextContent(type="text", text=f"Unknown action: {action}")]


# ---------------------------------------------------------------------------
# memento_graph — unified Project Memory Graph
# ---------------------------------------------------------------------------

@registry.register(
    Tool(
        name="memento_graph",
        description=(
            "Manage the Project Memory Graph. Actions: "
            "add_entity, add_relation, query, impact, summary."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "add_entity",
                        "add_relation",
                        "query",
                        "impact",
                        "summary",
                    ],
                    "description": "Action to perform.",
                },
                # add_entity
                "name": {
                    "type": "string",
                    "description": "Entity name for add_entity.",
                },
                "entity_type": {
                    "type": "string",
                    "description": "Entity type: file, component, decision, bug_fix, feature, session, module, api.",
                },
                "properties": {
                    "type": "string",
                    "description": "JSON string of additional entity properties.",
                },
                # add_relation
                "subject": {
                    "type": "string",
                    "description": "Source entity name for add_relation.",
                },
                "predicate": {
                    "type": "string",
                    "description": "Relation: depends_on, blocks, implements, breaks, supersedes, relates_to, part_of, uses.",
                },
                "object": {
                    "type": "string",
                    "description": "Target entity name for add_relation.",
                },
                # query / impact
                "entity_name": {
                    "type": "string",
                    "description": "Entity name for query / impact.",
                },
                "depth": {
                    "type": "integer",
                    "description": "Traversal depth for query (1=direct, 2=one hop further).",
                    "default": 1,
                },
                # common
                "workspace_root": {"type": "string"},
            },
            "required": ["action"],
        },
    )
)
async def memento_graph(arguments: dict, ctx, access_manager) -> list[TextContent]:
    action = arguments["action"]

    # -- add_entity ----------------------------------------------------------
    if action == "add_entity":
        if not access_manager.can_write():
            raise PermissionError(f"Access: {access_manager.state}")
        name = arguments.get("name", "")
        entity_type = arguments.get("entity_type", "")
        props = None
        raw_props = arguments.get("properties")
        if raw_props:
            try:
                props = json.loads(raw_props)
            except Exception:
                props = {"raw": raw_props}
        ok = await ctx.project_memory_graph.add_entity(
            name=name, entity_type=entity_type, properties=props,
        )
        return [TextContent(type="text", text=f"Entity '{name}' ({entity_type}) {'added' if ok else 'failed to add'}.")]

    # -- add_relation --------------------------------------------------------
    if action == "add_relation":
        if not access_manager.can_write():
            raise PermissionError(f"Access: {access_manager.state}")
        subject = arguments.get("subject", "")
        predicate = arguments.get("predicate", "")
        object_ = arguments.get("object", "")
        ok = await ctx.project_memory_graph.add_relation(
            subject=subject, predicate=predicate, object_=object_,
        )
        return [
            TextContent(
                type="text",
                text=f"Relation '{subject} --{predicate}--> {object_}' {'added' if ok else 'failed'}.",
            )
        ]

    # -- query ---------------------------------------------------------------
    if action == "query":
        if not access_manager.can_read():
            raise PermissionError(f"Access: {access_manager.state}")
        entity = arguments.get("entity_name", "")
        depth = int(arguments.get("depth") or 1)
        context = await ctx.project_memory_graph.get_entity_context(
            entity_name=entity, depth=depth,
        )
        return [TextContent(type="text", text=context)]

    # -- impact --------------------------------------------------------------
    if action == "impact":
        if not access_manager.can_read():
            raise PermissionError(f"Access: {access_manager.state}")
        entity = arguments.get("entity_name", "")
        dependents = await ctx.project_memory_graph.get_what_might_break(
            entity_name=entity,
        )
        if not dependents:
            return [TextContent(type="text", text=f"No entities depend on '{entity}'.")]
        lines = [f"Entities that depend on '{entity}':"] + [f"  - {d}" for d in dependents]
        return [TextContent(type="text", text="\n".join(lines))]

    # -- summary -------------------------------------------------------------
    if action == "summary":
        if not access_manager.can_read():
            raise PermissionError(f"Access: {access_manager.state}")
        summary = await ctx.project_memory_graph.get_project_summary()
        return [TextContent(type="text", text=summary)]

    return [TextContent(type="text", text=f"Unknown action: {action}")]
