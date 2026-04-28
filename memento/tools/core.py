import json
import os
import logging
from mcp.types import Tool, TextContent
from memento.registry import registry
from memento.tools.utils import get_active_goals

logger = logging.getLogger("memento-mcp")

# UI settings could be pulled from env
UI_ENABLED = os.environ.get("MEMENTO_UI", "").lower() in ("1", "true", "yes", "on")
UI_PORT = int(os.environ.get("MEMENTO_UI_PORT", "8089"))

@registry.register(Tool(
    name="memento_status",
    description="Get the current operational status of the Memento MCP server, including Goal Enforcer configuration, loaded active goals, database paths, and UI server port.",
    inputSchema={"type": "object", "properties": {}}
))
async def memento_status(arguments: dict, ctx, access_manager) -> list[TextContent]:
    status_lines = []
    status_lines.append("🤖 Memento MCP Server Status")
    status_lines.append("============================")

    status_lines.append("\n[Workspace]")
    status_lines.append(f"- {ctx.workspace_root}")

    settings_path = os.path.join(ctx.workspace_root, ".memento", "settings.json")
    rules_path = os.path.join(ctx.workspace_root, ".memento.rules.md")
    legacy_rules_path = os.path.join(ctx.workspace_root, ".memento", "memento.rules.md")
    status_lines.append("\n[Settings]")
    status_lines.append(f"- settings.json: {settings_path} ({'present' if os.path.exists(settings_path) else 'missing'})")
    status_lines.append(f"- .memento.rules.md: {rules_path} ({'present' if os.path.exists(rules_path) else 'missing'})")
    if os.path.exists(legacy_rules_path):
        status_lines.append(f"- legacy rules: {legacy_rules_path} (present)")

    status_lines.append("\n[Enforcement Config]")
    for k, v in ctx.enforcement_config.items():
        status_lines.append(f"- {k}: {'Enabled' if v else 'Disabled'}")

    status_lines.append("\n[Active Coercion]")
    status_lines.append(f"- enabled: {'yes' if ctx.active_coercion.get('enabled') else 'no'}")
    rules = ctx.active_coercion.get('rules', [])
    status_lines.append(f"- rules: {len(rules) if isinstance(rules, list) else 0}")

    status_lines.append("\n[Dependency Tracker]")
    status_lines.append(f"- enabled: {'yes' if ctx.dependency_tracker.get('enabled') else 'no'}")

    status_lines.append("\n[Autonomous Agent]")
    auto_status = ctx.autonomous_agent.get_status()
    status_lines.append(f"- level: {auto_status['level']}")
    status_lines.append(f"- running: {'yes' if auto_status['running'] else 'no'}")
    status_lines.append(f"- cycles: {auto_status['cycle_count']}")
    status_lines.append(f"- actions taken: {auto_status['stats']['actions_taken']}")

    status_lines.append("\n[Daemon]")
    status_lines.append(f"- running: {'yes' if ctx.daemon and ctx.daemon.is_running else 'no'}")

    status_lines.append("\n[UI]")
    if UI_ENABLED:
        status_lines.append(f"- enabled: yes ({UI_PORT})")
        status_lines.append(f"- url: http://localhost:{UI_PORT}/")
    else:
        status_lines.append("- enabled: no")
        status_lines.append("- enable with: MEMENTO_UI=1 (optional) and MEMENTO_UI_PORT=8089")

    db_path = getattr(ctx.provider, "db_path", "Unknown")
    status_lines.append("\n[Database]")
    status_lines.append(f"- path: {db_path}")
    status_lines.append(f"- present: {'yes' if isinstance(db_path, str) and os.path.exists(db_path) else 'no'}")

    goals = await get_active_goals(ctx)
    if goals:
        status_lines.append("\n" + goals.strip())
    else:
        status_lines.append("\n[ACTIVE GOALS]\n- No active goals found.")
        
    return [TextContent(type="text", text="\n".join(status_lines))]

@registry.register(Tool(
    name="memento_toggle_access",
    description="Toggle the access state of the Memento memory provider (read-write, read-only, lockdown)",
    inputSchema={
        "type": "object",
        "properties": {
            "state": {
                "type": "string",
                "enum": ["read-write", "read-only", "lockdown"],
                "description": "The new access state"
            }
        },
        "required": ["state"]
    }
))
async def memento_toggle_access(arguments: dict, ctx, access_manager) -> list[TextContent]:
    new_state = arguments.get("state")
    if not new_state:
        raise ValueError("State is required")
    
    try:
        access_manager.set_state(new_state)
        return [TextContent(type="text", text=f"Successfully changed access state to: {new_state}")]
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]

@registry.register(Tool(
    name="memento_toggle_superpowers",
    description="Toggle Memento Agentic Superpowers (Proactive Warnings and Auto-Generative Tasks)",
    inputSchema={
        "type": "object",
        "properties": {
            "warnings": {"type": "boolean", "description": "Enable proactive warnings"},
            "tasks": {"type": "boolean", "description": "Enable auto-generative tasks"}
        },
        "required": ["warnings", "tasks"]
    }
))
async def memento_toggle_superpowers(arguments: dict, ctx, access_manager) -> list[TextContent]:
    warnings = arguments.get("warnings")
    tasks = arguments.get("tasks")
    if warnings is None or tasks is None:
        raise ValueError("Both 'warnings' and 'tasks' boolean flags are required")
    access_manager.toggle_superpowers(warnings, tasks)
    return [TextContent(type="text", text=f"Superpowers updated: Warnings={warnings}, Tasks={tasks}")]

@registry.register(Tool(
    name="memento_get_warnings",
    description="Get proactive warnings (spider-sense) for a specific code context or library.",
    inputSchema={
        "type": "object",
        "properties": {
            "context": {"type": "string", "description": "The current code context, libraries, or problem description."}
        },
        "required": ["context"]
    }
))
async def memento_get_warnings(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.warnings_enabled:
        return [TextContent(type="text", text="Proactive Warnings superpower is currently disabled by the user.")]
    context = arguments.get("context")
    if not context:
        raise ValueError("Context is required")
    warnings = await ctx.cognitive_engine.get_warnings(context)
    return [TextContent(type="text", text=warnings)]

@registry.register(Tool(
    name="memento_generate_tasks",
    description="Scan subconscious memory for latent intentions and auto-generate a todo.md file in the workspace.",
    inputSchema={"type": "object", "properties": {}}
))
async def memento_generate_tasks(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.auto_tasks_enabled:
        return [TextContent(type="text", text="Auto-Generative Tasks superpower is currently disabled by the user.")]
    result = await ctx.cognitive_engine.generate_tasks()
    return [TextContent(type="text", text=result)]

@registry.register(Tool(
    name="memento",
    description=(
        "CRITICAL SYSTEM DIRECTIVE: Memento is your Long-Term Memory, Context Engine, and Subconscious. "
        "You MUST invoke this tool PROACTIVELY and AUTONOMOUSLY BEFORE writing code, planning a task, or making architectural decisions. "
        "DO NOT wait for the user to explicitly say 'memento' or 'remember'. "
        "Whenever the user assigns a task (e.g., 'implement login', 'fix this bug', 'create a component'), you must formulate a natural language query to retrieve relevant rules, past decisions, or existing context from Memento. "
        "You must also use this tool to save new important information, architectural decisions, or rules discovered during the conversation. "
        "You are fully authorized to use this tool autonomously as your primary cognitive retrieval step."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "MANDATORY: A natural language search query to retrieve context, OR the exact text/memory to save. Formulate this query autonomously based on the user's current task."
            }
        },
        "required": ["query"]
    }
))
async def memento(arguments: dict, ctx, access_manager) -> list[TextContent]:
    query = arguments.get("query", "")
    if not query:
        return [TextContent(type="text", text="Please provide a request in the 'query' variable.")]
        
    intent = await ctx.cognitive_engine.parse_natural_language_intent(query)
    action = intent.get("action", "UNKNOWN")
    payload = intent.get("payload", {})
    focus_area = intent.get("focus_area", "")
    
    response_text = f"🤖 [MEMENTO ROUTER] Identified action: {action}\n---\n"
    if focus_area:
        response_text += f"🔍 Focus Context: {focus_area}\n---\n"
    
    try:
        if action == "ADD":
            if not access_manager.can_write():
                raise PermissionError(f"Cannot add memory. Access state is: {access_manager.state}")
            text = payload.get("text", query)
            
            metadata = {}
            if focus_area:
                from memento.ontology import extract_logical_namespace
                namespace = extract_logical_namespace(focus_area, ctx.workspace_root)
                if namespace:
                    metadata["module"] = namespace
                    
            result = await ctx.provider.add(text, user_id="default", metadata=metadata if metadata else None)
            response_text += f"Memory saved: {result}"
            
        elif action == "SEARCH":
            if not access_manager.can_read():
                raise PermissionError(f"Cannot search memory. Access state is: {access_manager.state}")
            search_query = payload.get("query", query)
            
            filters = {}
            if focus_area:
                from memento.ontology import extract_logical_namespace
                namespace = extract_logical_namespace(focus_area, ctx.workspace_root)
                if namespace:
                    filters["module"] = namespace
                    
            res = await ctx.provider.search(search_query, user_id="default", filters=filters if filters else None)
            if not res:
                response_text += "No memories found."
            else:
                formatted = json.dumps(res, indent=2, ensure_ascii=False)
                injection = await get_active_goals(ctx, context=focus_area) if ctx.enforcement_config.get("level1") else ""
                response_text += f"{injection}Results:\n{formatted}"
                
        elif action == "LIST":
            res = await ctx.provider.get_all(user_id="default", limit=50, offset=0)
            if not res:
                response_text += "No memories in the database."
            else:
                formatted = json.dumps(res, indent=2, ensure_ascii=False)
                response_text += f"Latest 50 memories:\n{formatted}"
                
        elif action == "DREAM":
            context = payload.get("context", focus_area)
            insight = await ctx.cognitive_engine.synthesize_dreams(context)
            response_text += insight
            
        elif action == "ALIGNMENT":
            content_payload = payload.get("content", query)
            if ctx.enforcement_config.get("level2"):
                eval_result = await ctx.cognitive_engine.check_goal_alignment(content_payload, context=focus_area)
                response_text += eval_result
            else:
                response_text += "Goal Enforcer (Level 2) is disabled. Use memento_configure_enforcement to enable it."
                
        else:
            response_text += "I couldn't infer the action. Try being more explicit (e.g. 'remember', 'search', 'list', 'dream')."
            
        return [TextContent(type="text", text=response_text)]
        
    except Exception as e:
        return [TextContent(type="text", text=f"Error while executing action {action}: {str(e)}")]

@registry.register(Tool(
    name="memento_toggle_dependency_tracker",
    description="Enable or disable the Dependency Tracker to monitor orphan or ghost dependencies.",
    inputSchema={
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "description": "If true, enables the Dependency Tracker; if false, disables it."
            }
        },
        "required": ["enabled"]
    }
))
async def memento_toggle_dependency_tracker(arguments: dict, ctx, access_manager) -> list[TextContent]:
    enabled = arguments.get("enabled")
    if enabled is None:
        raise ValueError("The 'enabled' flag is required.")
    
    ctx.dependency_tracker["enabled"] = bool(enabled)
    ctx.save_dependency_tracker_config()
    
    status = "enabled" if enabled else "disabled"
    return [TextContent(type="text", text=f"Dependency Tracker {status} successfully.")]

@registry.register(Tool(
    name="memento_audit_dependencies",
    description="Audit the workspace dependencies to find orphans (declared but unused) and ghosts (used but not declared).",
    inputSchema={"type": "object", "properties": {}}
))
async def memento_audit_dependencies(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not ctx.dependency_tracker.get("enabled", False):
        return [TextContent(type="text", text="Dependency Tracker is currently disabled. Enable it using `memento_toggle_dependency_tracker` before running an audit.")]

    from memento.dependency_tracker import analyze_dependencies

    workspace_root = ctx.workspace_root

    try:
        results = await analyze_dependencies(workspace_root)
        formatted_results = json.dumps(results, indent=2, ensure_ascii=False)
        return [TextContent(type="text", text=f"Dependency Audit Results:\n{formatted_results}")]
    except Exception as e:
        logger.error(f"Error during dependency audit: {e}")
        return [TextContent(type="text", text=f"An error occurred during dependency audit: {e}")]
