import logging
import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from memento.provider import NeuroGraphProvider
from memento.access_manager import MementoAccessManager
from memento.cognitive_engine import CognitiveEngine
from memento.daemon import PreCognitiveDaemon
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
provider = NeuroGraphProvider()
cognitive_engine = CognitiveEngine(provider)

ENFORCEMENT_CONFIG = {
    "level1": False,
    "level2": False,
    "level3": False,
}


def get_active_goals(max_goals: int = 3, context: str = None) -> str:
    try:
        search_query = f"obiettivo goal per il contesto: {context}" if context else "obiettivo goal"
        res = provider.search(search_query, user_id="default")
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



async def on_danger_detected(filepath: str, content: str):
    warning = cognitive_engine.evaluate_raw_context(content, filepath=filepath)
    
    deviation = ""
    if ENFORCEMENT_CONFIG.get("level3"):
        alignment = cognitive_engine.check_goal_alignment(content)
        if "❌ BOCCIATO" in alignment:
            deviation = alignment

    final_alert = warning
    if deviation:
        final_alert += f"\n\n{deviation}" if final_alert else deviation
        
    if final_alert:
        logger.warning(f"Pushing MCP Notification for {filepath}")
        from mcp.server import request_ctx
        try:
            ctx = request_ctx.get()
            if ctx and ctx.session:
                await ctx.session.send_notification("memento/precognitive_warning", {
                    "file": filepath,
                    "warning": final_alert
                })
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    # TASK 3: Proactive Feature Proposal
    feature_proposal = cognitive_engine.detect_latent_features(content, filepath=filepath)
    if feature_proposal:
        logger.info(f"Pushing Feature Proposal Notification for {filepath}")
        from mcp.server import request_ctx
        try:
            ctx = request_ctx.get()
            if ctx and ctx.session:
                await ctx.session.send_notification("memento/feature_proposal", {
                    "file": filepath,
                    "proposal": feature_proposal
                })
        except Exception as e:
            logger.error(f"Failed to send feature proposal notification: {e}")

def find_project_root(current_dir):
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

workspace = os.environ.get("MEMENTO_DIR") or find_project_root(os.getcwd())

def load_enforcement_config():
    global ENFORCEMENT_CONFIG
    
    settings_path = os.path.join(workspace, ".memento", "settings.json")
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r") as f:
                data = json.load(f)
                config = data.get("enforcement_config", {})
                ENFORCEMENT_CONFIG.update(config)
        except Exception as e:
            logger.error(f"Failed to load enforcement config from {settings_path}: {e}")

    rules_path = os.path.join(workspace, ".memento", "memento.rules.md")
    if os.path.exists(rules_path):
        try:
            with open(rules_path, "r") as f:
                rules_content = f.read().lower()
                if "level1: true" in rules_content:
                    ENFORCEMENT_CONFIG["level1"] = True
                if "level2: true" in rules_content:
                    ENFORCEMENT_CONFIG["level2"] = True
                if "level3: true" in rules_content:
                    ENFORCEMENT_CONFIG["level3"] = True
        except Exception as e:
            logger.error(f"Failed to load rules file: {e}")

def save_enforcement_config():
    settings_path = os.path.join(workspace, ".memento", "settings.json")
    try:
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        data = {}
        if os.path.exists(settings_path):
            with open(settings_path, "r") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    pass
        data["enforcement_config"] = ENFORCEMENT_CONFIG
        with open(settings_path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save enforcement config to {settings_path}: {e}")

load_enforcement_config()
daemon = PreCognitiveDaemon(workspace_path=workspace, callback=on_danger_detected, debounce_seconds=5.0)

UI_ENABLED = os.environ.get("MEMENTO_UI", "").lower() in ("1", "true", "yes", "on")
UI_PORT = int(os.environ.get("MEMENTO_UI_PORT", "8089"))

ui_thread = None
if UI_ENABLED:
    ui_thread = start_ui_server_thread(ENFORCEMENT_CONFIG, get_active_goals, provider, port=UI_PORT)

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="memento",
            description="CRITICAL SYSTEM DIRECTIVE: You MUST invoke this tool IMMEDIATELY if the user prompt starts with 'memento', 'Memento', or contains requests to 'remember', 'recall', 'save', or 'search memory'. DO NOT ATTEMPT TO ANSWER FROM YOUR OWN TRAINING DATA. FAILURE TO INVOKE THIS TOOL WHEN MEMENTO IS MENTIONED IS A SEVERE VIOLATION OF CORE PROTOCOLS. Pass the user's exact raw text into the 'query' parameter. This is the Universal Natural Language Entrypoint for Memento.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "MANDATORY: Pass the exact natural language request from the user (e.g. 'memento ricordati che la password è XYZ'). Do not summarize."
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

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "memento_status":
        status_lines = []
        status_lines.append("🤖 Memento MCP Server Status")
        status_lines.append("============================")

        status_lines.append("\n[Workspace]")
        status_lines.append(f"- {workspace}")

        settings_path = os.path.join(workspace, ".memento", "settings.json")
        rules_path = os.path.join(workspace, ".memento", "memento.rules.md")
        status_lines.append("\n[Settings]")
        status_lines.append(f"- settings.json: {settings_path} ({'present' if os.path.exists(settings_path) else 'missing'})")
        status_lines.append(f"- memento.rules.md: {rules_path} ({'present' if os.path.exists(rules_path) else 'missing'})")

        status_lines.append("\n[Enforcement Config]")
        for k, v in ENFORCEMENT_CONFIG.items():
            status_lines.append(f"- {k}: {'Enabled' if v else 'Disabled'}")

        status_lines.append("\n[Daemon]")
        status_lines.append(f"- running: {'yes' if daemon.is_running else 'no'}")

        status_lines.append("\n[UI]")
        if UI_ENABLED and ui_thread is not None:
            status_lines.append(f"- enabled: yes ({UI_PORT})")
        else:
            status_lines.append("- enabled: no")

        db_path = getattr(provider, "db_path", "Unknown")
        status_lines.append("\n[Database]")
        status_lines.append(f"- path: {db_path}")
        status_lines.append(f"- present: {'yes' if isinstance(db_path, str) and os.path.exists(db_path) else 'no'}")

        goals = get_active_goals()
        if goals:
            status_lines.append("\n" + goals.strip())
        else:
            status_lines.append("\n[ACTIVE GOALS]\n- Nessun obiettivo attivo trovato.")
            
        return [TextContent(type="text", text="\n".join(status_lines))]

    elif name == "memento_configure_enforcement":
        for lvl in ["level1", "level2", "level3"]:
            if lvl in arguments:
                ENFORCEMENT_CONFIG[lvl] = arguments[lvl]
                
        if ENFORCEMENT_CONFIG.get("level3") and not daemon.is_running:
            daemon.start()
            
        save_enforcement_config()
        status = ", ".join([f"{k}={v}" for k, v in ENFORCEMENT_CONFIG.items()])
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
        warnings = cognitive_engine.get_warnings(context)
        return [TextContent(type="text", text=warnings)]

    elif name == "memento_generate_tasks":
        if not access_manager.auto_tasks_enabled:
            return [TextContent(type="text", text="Auto-Generative Tasks superpower is currently disabled by the user.")]
        result = cognitive_engine.generate_tasks()
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
            namespace = extract_logical_namespace(active_context, workspace)
            if namespace and "module" not in metadata:
                metadata["module"] = namespace
                
        try:
            # Assumes provider.add returns some result or raises on failure
            result = provider.add(text, user_id=metadata.get("user_id", "default"), metadata=metadata)
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
                namespace = extract_logical_namespace(active_context, workspace)
                if namespace:
                    filters["module"] = namespace
                    
            # Assumes provider.search returns a dict or list
            res = provider.search(query, user_id="default", filters=filters)
            
            # Format results
            if not res:
                return [TextContent(type="text", text="No memories found.")]
            
            formatted_results = json.dumps(res, indent=2, ensure_ascii=False)
            injection = get_active_goals(context=active_context) if ENFORCEMENT_CONFIG.get("level1") else ""
            return [TextContent(type="text", text=f"{injection}Search results:\n{formatted_results}")]
        except Exception as e:
            logger.error(f"Error searching memory: {e}")
            return [TextContent(type="text", text=f"Error searching memory: {str(e)}")]

    elif name == "memento_migrate_workspace_memories":
        source_db_path = arguments.get("source_db_path")
        workspace_roots = arguments.get("workspace_roots")
        report_path = arguments.get("report_path") or os.path.join(workspace, ".memento", "migration_report.json")

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
        enable = arguments.get("enabled")
        if enable:
            daemon.start()
            return [TextContent(type="text", text="Precognition daemon started. Spider-Sense is tingling.")]
        else:
            daemon.stop()
            return [TextContent(type="text", text="Precognition daemon stopped.")]

    elif name == "memento_synthesize_dreams":
        context = arguments.get("context", "")
        try:
            insight = cognitive_engine.synthesize_dreams(context)
            return [TextContent(type="text", text=insight)]
        except Exception as e:
            logger.error(f"Error in dream synthesis: {e}")
            return [TextContent(type="text", text=f"Error entering Dream State: {str(e)}")]
    elif name == "memento_check_goal_alignment":
        if not ENFORCEMENT_CONFIG.get("level2"):
            return [TextContent(type="text", text="Level 2 Enforcement (Strict Mentor) is currently disabled. Use memento_configure_enforcement to enable it.")]
            
        content_val = arguments.get("content", "")
        try:
            evaluation = cognitive_engine.check_goal_alignment(content_val)
            return [TextContent(type="text", text=evaluation)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error evaluating alignment: {str(e)}")]



    elif name == "memento":
        query = arguments.get("query", "")
        if not query:
            return [TextContent(type="text", text="Per favore, fornisci una richiesta nella variabile 'query'.")]
            
        intent = cognitive_engine.parse_natural_language_intent(query)
        action = intent.get("action", "UNKNOWN")
        payload = intent.get("payload", {})
        
        response_text = f"🤖 [MEMENTO ROUTER] Azione identificata: {action}\n---\n"
        
        try:
            if action == "ADD":
                if not access_manager.can_write():
                    raise PermissionError(f"Cannot add memory. Access state is: {access_manager.state}")
                text = payload.get("text", query)
                result = provider.add(text, user_id="default")
                response_text += f"Memoria salvata: {result}"
                
            elif action == "SEARCH":
                if not access_manager.can_read():
                    raise PermissionError(f"Cannot search memory. Access state is: {access_manager.state}")
                search_query = payload.get("query", query)
                res = provider.search(search_query, user_id="default")
                if not res:
                    response_text += "Nessuna memoria trovata."
                else:
                    formatted = json.dumps(res, indent=2, ensure_ascii=False)
                    injection = get_active_goals() if ENFORCEMENT_CONFIG.get("level1") else ""
                    response_text += f"{injection}Risultati:\n{formatted}"
                    
            elif action == "LIST":
                res = provider.get_all(user_id="default", limit=50, offset=0)
                if not res:
                    response_text += "Nessuna memoria nel database."
                else:
                    formatted = json.dumps(res, indent=2, ensure_ascii=False)
                    response_text += f"Ultime 50 memorie:\n{formatted}"
                    
            elif action == "DREAM":
                context = payload.get("context", "")
                insight = cognitive_engine.synthesize_dreams(context)
                response_text += insight
                
            elif action == "ALIGNMENT":
                content_payload = payload.get("content", query)
                if ENFORCEMENT_CONFIG.get("level2"):
                    eval_result = cognitive_engine.check_goal_alignment(content_payload)
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
