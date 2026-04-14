import logging
import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from memento.access_manager import MementoAccessManager
from memento.workspace_context import get_workspace_context
from memento.ui_server import start_ui_server_thread
import os
import json

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("memento-mcp")

app = Server("memento-mcp")

access_manager = MementoAccessManager()

def find_project_root(current_dir: str) -> str:
    markers = [".git", "package.json", "pyproject.toml", "cargo.toml"]
    d = os.path.abspath(current_dir)
    original_dir = d
    while True:
        for marker in markers:
            if os.path.exists(os.path.join(d, marker)):
                return d
        parent = os.path.dirname(d)
        if parent == d:
            return original_dir
        d = parent

def get_active_goals(ctx, max_goals: int = 3, context: str = None) -> str:
    try:
        search_query = f"obiettivo goal per il contesto: {context}" if context else "obiettivo goal"
        res = ctx.provider.search(search_query, user_id="default")
        results = res.get("results", []) if isinstance(res, dict) else res
        if not isinstance(results, list):
            return ""
        goals = []
        for r in results[:max_goals]:
            if not isinstance(r, dict):
                continue
            memory = r.get("memory")
            if isinstance(memory, str) and memory.strip():
                goals.append(memory.strip())
        if not goals:
            return ""
        formatted = "\n- ".join(goals)
        return f"[ACTIVE GOALS]\n- {formatted}\n\n"
    except Exception:
        return ""

UI_ENABLED = os.environ.get("MEMENTO_UI", "").lower() in ("1", "true", "yes", "on")
UI_PORT = int(os.environ.get("MEMENTO_UI_PORT", "8089"))

ui_thread = None
# UI server is temporarily disabled for multi-tenant refactor
# if UI_ENABLED:
#     ui_thread = start_ui_server_thread(ENFORCEMENT_CONFIG, get_active_goals, provider, port=UI_PORT)


@app.list_tools()
async def list_tools() -> list[Tool]:
    tools = [
        Tool(
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
        ),
        Tool(
            name="memento_configure_enforcement",
            description="Configure the Tri-State Goal Steering mechanisms. Level 1: Context Injection. Level 2: Strict Mentor Checkpoint. Level 3: Daemon Push Notifications.",
            inputSchema={
                "type": "object",
                "properties": {
                    "level1": {"type": "boolean"},
                    "level2": {"type": "boolean"},
                    "level3": {"type": "boolean"}
                },
                "required": []
            }
        ),
        Tool(
            name="memento_synthesize_dreams",
            description="Enter Dream State: Generates a novel, creative insight (Synthetic Diamond) by finding hidden patterns across existing isolated memories. Returns a DRAFT_INSIGHT that must be manually approved.",
            inputSchema={
                "type": "object",
                "properties": {
                    "context": {
                        "type": "string",
                        "description": "Optional topic or context to focus the dream on. If omitted, random recent memories are used."
                    },
                    "active_context": {
                        "type": "string",
                        "description": "Optional active contextual metadata (e.g. current file, active task) to focus the synthesis."
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="memento_check_goal_alignment",
            description="Level 2 Enforcer: Submit code or plans to be strictly evaluated against the project's core goals. Use this to verify if your work is innovative and aligned before finalizing a task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The code, plan, or decision to evaluate"
                    },
                    "active_context": {
                        "type": "string",
                        "description": "Optional active contextual metadata (e.g. current file, active task) to frame the evaluation."
                    }
                },
                "required": ["content"]
            }
        ),

        Tool(
            name="memento_toggle_precognition",
            description="Toggle the Pre-cognitive Intervention background daemon",
            inputSchema={
                "type": "object",
                "properties": {
                    "enabled": {
                        "type": "boolean",
                        "description": "True to start watching files, False to stop"
                    }
                },
                "required": ["enabled"]
            }
        ),
        Tool(
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
        ),
        Tool(
            name="memento_toggle_superpowers",
            description="Toggle Memento Agentic Superpowers (Proactive Warnings and Auto-Generative Tasks)",
            inputSchema={
                "type": "object",
                "properties": {
                    "warnings": {
                        "type": "boolean",
                        "description": "Enable proactive warnings"
                    },
                    "tasks": {
                        "type": "boolean",
                        "description": "Enable auto-generative tasks"
                    }
                },
                "required": ["warnings", "tasks"]
            }
        ),
        Tool(
            name="memento_get_warnings",
            description="Get proactive warnings (spider-sense) for a specific code context or library.",
            inputSchema={
                "type": "object",
                "properties": {
                    "context": {
                        "type": "string",
                        "description": "The current code context, libraries, or problem description."
                    }
                },
                "required": ["context"]
            }
        ),
        Tool(
            name="memento_generate_tasks",
            description="Scan subconscious memory for latent intentions and auto-generate a todo.md file in the workspace.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="memento_add_memory",
            description="Add a new memory to the Memento provider",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The free text memory to add"
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Optional metadata for the memory",
                        "additionalProperties": True
                    },
                    "active_context": {
                        "type": "string",
                        "description": "Optional active contextual metadata (e.g. current file, active task) to frame the memory."
                    }
                },
                "required": ["text"]
            }
        ),
        Tool(
            name="memento_search_memory",
            description="Search memories in the Memento provider",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query"
                    },
                    "active_context": {
                        "type": "string",
                        "description": "Optional active contextual metadata (e.g. current file, active task) to filter or contextualize the search."
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="memento_migrate_workspace_memories",
            description="Copy-only migration: redistribute memories from a source DB into per-workspace DBs using deterministic text heuristics. Produces a JSON report.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source_db_path": {"type": "string"},
                    "workspace_roots": {"type": "array", "items": {"type": "string"}},
                    "report_path": {"type": "string"},
                },
                "required": ["source_db_path", "workspace_roots"],
            },
        ),
        Tool(
            name="memento_status",
            description="Get the current operational status of the Memento MCP server, including Goal Enforcer configuration, loaded active goals, database paths, and UI server port.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]
    
    for t in tools:
        if "workspace_root" not in t.inputSchema["properties"]:
            t.inputSchema["properties"]["workspace_root"] = {
                "type": "string",
                "description": "MANDATORY: The absolute path of the current project/workspace root."
            }
            
    return tools

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
    
    if name == "memento_status":
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

        status_lines.append("\n[Daemon]")
        status_lines.append(f"- running: {'yes' if ctx.daemon and ctx.daemon.is_running else 'no'}")

        status_lines.append("\n[UI]")
        if UI_ENABLED and ui_thread is not None:
            status_lines.append(f"- enabled: yes ({UI_PORT})")
        else:
            status_lines.append("- enabled: no")

        db_path = getattr(ctx.provider, "db_path", "Unknown")
        status_lines.append("\n[Database]")
        status_lines.append(f"- path: {db_path}")
        status_lines.append(f"- present: {'yes' if isinstance(db_path, str) and os.path.exists(db_path) else 'no'}")

        goals = get_active_goals(ctx)
        if goals:
            status_lines.append("\n" + goals.strip())
        else:
            status_lines.append("\n[ACTIVE GOALS]\n- Nessun obiettivo attivo trovato.")
            
        return [TextContent(type="text", text="\n".join(status_lines))]

    elif name == "memento_configure_enforcement":
        for lvl in ["level1", "level2", "level3"]:
            if lvl in arguments:
                ctx.enforcement_config[lvl] = arguments[lvl]
                
        if ctx.enforcement_config.get("level3") and (not ctx.daemon or not ctx.daemon.is_running):
            # For now, just a placeholder, daemon start is handled in Task 3
            pass
            
        ctx.save_enforcement_config()
        status = ", ".join([f"{k}={v}" for k, v in ctx.enforcement_config.items()])
        return [TextContent(type="text", text=f"Configurazione Goal Enforcement aggiornata:\n{status}")]

    elif name == "memento_toggle_access":
        new_state = arguments.get("state")
        if not new_state:
            raise ValueError("State is required")
        
        try:
            access_manager.set_state(new_state)
            return [TextContent(type="text", text=f"Successfully changed access state to: {new_state}")]
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    elif name == "memento_toggle_superpowers":
        warnings = arguments.get("warnings")
        tasks = arguments.get("tasks")
        if warnings is None or tasks is None:
            raise ValueError("Both 'warnings' and 'tasks' boolean flags are required")
        access_manager.toggle_superpowers(warnings, tasks)
        return [TextContent(type="text", text=f"Superpowers updated: Warnings={warnings}, Tasks={tasks}")]

    elif name == "memento_get_warnings":
        if not access_manager.warnings_enabled:
            return [TextContent(type="text", text="Proactive Warnings superpower is currently disabled by the user.")]
        context = arguments.get("context")
        if not context:
            raise ValueError("Context is required")
        warnings = ctx.cognitive_engine.get_warnings(context)
        return [TextContent(type="text", text=warnings)]

    elif name == "memento_generate_tasks":
        if not access_manager.auto_tasks_enabled:
            return [TextContent(type="text", text="Auto-Generative Tasks superpower is currently disabled by the user.")]
        result = ctx.cognitive_engine.generate_tasks()
        return [TextContent(type="text", text=result)]

    elif name == "memento_add_memory":
        if not access_manager.can_write():
            raise PermissionError(f"Cannot add memory. Current access state is: {access_manager.state}")
            
        text = arguments.get("text")
        if not text:
            raise ValueError("Text is required")
            
        metadata = arguments.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
            
        active_context = arguments.get("active_context")
        if active_context:
            from memento.ontology import extract_logical_namespace
            namespace = extract_logical_namespace(active_context, ctx.workspace_root)
            if namespace and "module" not in metadata:
                metadata["module"] = namespace
                
        try:
            # Assumes provider.add returns some result or raises on failure
            result = ctx.provider.add(text, user_id=metadata.get("user_id", "default"), metadata=metadata)
            # Format result if needed
            return [TextContent(type="text", text=f"Successfully added memory: {result}")]
        except Exception as e:
            logger.error(f"Error adding memory: {e}")
            return [TextContent(type="text", text=f"Error adding memory: {str(e)}")]

    elif name == "memento_search_memory":
        if not access_manager.can_read():
            raise PermissionError(f"Cannot search memory. Current access state is: {access_manager.state}")
            
        query = arguments.get("query")
        active_context = arguments.get("active_context")
        if not query:
            raise ValueError("Query is required")
            
        try:
            filters = {}
            if active_context:
                from memento.ontology import extract_logical_namespace
                namespace = extract_logical_namespace(active_context, ctx.workspace_root)
                if namespace:
                    filters["module"] = namespace
                    
            # Assumes provider.search returns a dict or list
            res = ctx.provider.search(query, user_id="default", filters=filters)
            
            # Format results
            if not res:
                return [TextContent(type="text", text="No memories found.")]
            
            formatted_results = json.dumps(res, indent=2, ensure_ascii=False)
            injection = get_active_goals(ctx, context=active_context) if ctx.enforcement_config.get("level1") else ""
            return [TextContent(type="text", text=f"{injection}Search results:\n{formatted_results}")]
        except Exception as e:
            logger.error(f"Error searching memory: {e}")
            return [TextContent(type="text", text=f"Error searching memory: {str(e)}")]

    elif name == "memento_migrate_workspace_memories":
        source_db_path = arguments.get("source_db_path")
        workspace_roots = arguments.get("workspace_roots")
        report_path = arguments.get("report_path") or os.path.join(ctx.workspace_root, ".memento", "migration_report.json")

        if not source_db_path or not isinstance(source_db_path, str):
            raise ValueError("source_db_path is required")
        if not isinstance(workspace_roots, list) or not workspace_roots:
            raise ValueError("workspace_roots must be a non-empty list")

        from memento.migration import migrate_memories_copy_only

        report = migrate_memories_copy_only(
            source_db_path=source_db_path,
            workspace_roots=workspace_roots,
            report_path=report_path,
        )

        return [
            TextContent(
                type="text",
                text=json.dumps(report["summary"], indent=2, ensure_ascii=False),
            )
        ]

    elif name == "memento_toggle_precognition":
        enabled = arguments.get("enabled", False)
        
        async def _local_callback(filepath, content):
            warning = ctx.cognitive_engine.evaluate_raw_context(content, filepath=filepath)
            deviation = ""
            if ctx.enforcement_config.get("level3"):
                alignment = ctx.cognitive_engine.check_goal_alignment(content)
                if "❌ BOCCIATO" in alignment:
                    deviation = alignment
            
            final_alert = warning
            if deviation:
                final_alert += f"\n\n{deviation}" if final_alert else deviation
                
            if final_alert:
                logger.warning(f"Pushing MCP Notification for {filepath}")
                from mcp.server import request_ctx
                try:
                    req_ctx = request_ctx.get()
                    if req_ctx and req_ctx.session:
                        await req_ctx.session.send_notification("memento/precognitive_warning", {
                            "file": filepath,
                            "warning": final_alert
                        })
                except Exception as e:
                    logger.error(f"Failed to send notification: {e}")

        is_running = ctx.toggle_daemon(enabled, _local_callback)
        state_str = "AVVIATO" if is_running else "FERMATO"
        return [TextContent(type="text", text=f"Daemon Pre-cognitivo {state_str} per il workspace {ctx.workspace_root}.")]

    elif name == "memento_synthesize_dreams":
        context = arguments.get("context", "")
        try:
            insight = ctx.cognitive_engine.synthesize_dreams(context)
            return [TextContent(type="text", text=insight)]
        except Exception as e:
            logger.error(f"Error in dream synthesis: {e}")
            return [TextContent(type="text", text=f"Error entering Dream State: {str(e)}")]
    elif name == "memento_check_goal_alignment":
        if not ctx.enforcement_config.get("level2"):
            return [TextContent(type="text", text="Level 2 Enforcement (Strict Mentor) is currently disabled. Use memento_configure_enforcement to enable it.")]
            
        content_val = arguments.get("content", "")
        try:
            evaluation = ctx.cognitive_engine.check_goal_alignment(content_val)
            return [TextContent(type="text", text=evaluation)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error evaluating alignment: {str(e)}")]



    elif name == "memento":
        query = arguments.get("query", "")
        if not query:
            return [TextContent(type="text", text="Per favore, fornisci una richiesta nella variabile 'query'.")]
            
        intent = ctx.cognitive_engine.parse_natural_language_intent(query)
        action = intent.get("action", "UNKNOWN")
        payload = intent.get("payload", {})
        focus_area = intent.get("focus_area", "")
        
        response_text = f"🤖 [MEMENTO ROUTER] Azione identificata: {action}\n---\n"
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
                        
                result = ctx.provider.add(text, user_id="default", metadata=metadata if metadata else None)
                response_text += f"Memoria salvata: {result}"
                
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
                        
                res = ctx.provider.search(search_query, user_id="default", filters=filters if filters else None)
                if not res:
                    response_text += "Nessuna memoria trovata."
                else:
                    formatted = json.dumps(res, indent=2, ensure_ascii=False)
                    injection = get_active_goals(ctx, context=focus_area) if ctx.enforcement_config.get("level1") else ""
                    response_text += f"{injection}Risultati:\n{formatted}"
                    
            elif action == "LIST":
                res = ctx.provider.get_all(user_id="default", limit=50, offset=0)
                if not res:
                    response_text += "Nessuna memoria nel database."
                else:
                    formatted = json.dumps(res, indent=2, ensure_ascii=False)
                    response_text += f"Ultime 50 memorie:\n{formatted}"
                    
            elif action == "DREAM":
                context = payload.get("context", focus_area)
                insight = ctx.cognitive_engine.synthesize_dreams(context)
                response_text += insight
                
            elif action == "ALIGNMENT":
                content_payload = payload.get("content", query)
                if ctx.enforcement_config.get("level2"):
                    eval_result = ctx.cognitive_engine.check_goal_alignment(content_payload, context=focus_area)
                    response_text += eval_result
                else:
                    response_text += "Il Goal Enforcer (Level 2) è disabilitato. Usa memento_configure_enforcement per attivarlo."
                    
            else:
                response_text += "Non ho capito l'azione. Prova a essere più specifico (es. 'memorizza', 'cerca', 'lista', 'sogna')."
                
            return [TextContent(type="text", text=response_text)]
            
        except Exception as e:
            return [TextContent(type="text", text=f"Errore durante l'esecuzione dell'azione {action}: {str(e)}")]

    else:
        raise ValueError(f"Unknown tool: {name}")

async def run():
    logger.info("Starting Memento MCP server via stdio")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

def main():
    asyncio.run(run())

if __name__ == "__main__":
    main()
