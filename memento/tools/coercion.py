import json
from mcp.types import Tool, TextContent
from memento.registry import registry

@registry.register(Tool(
    name="memento_toggle_active_coercion",
    description="Toggle deterministic Active Coercion (IDE notifications and pre-commit blocking) for the current workspace.",
    inputSchema={
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "description": "True to enable Active Coercion, False to disable"
            }
        },
        "required": ["enabled"]
    }
))
async def memento_toggle_active_coercion(arguments: dict, ctx, access_manager) -> list[TextContent]:
    enabled = arguments.get("enabled")
    if enabled is None or not isinstance(enabled, bool):
        raise ValueError("enabled is required (boolean)")
    ctx.active_coercion["enabled"] = enabled
    ctx.save_active_coercion_config()
    return [
        TextContent(
            type="text",
            text=f"Active Coercion for workspace {ctx.workspace_root}: {'ENABLED' if enabled else 'DISABLED'}",
        )
    ]

@registry.register(Tool(
    name="memento_install_git_hooks",
    description="Install or update deterministic git hooks (pre-commit) for Active Coercion in the current git repository.",
    inputSchema={"type": "object", "properties": {}}
))
async def memento_install_git_hooks(arguments: dict, ctx, access_manager) -> list[TextContent]:
    from memento.git_hooks import install_pre_commit_hook
    try:
        hook_path = install_pre_commit_hook(ctx.workspace_root)
        return [TextContent(type="text", text=f"Successfully installed deterministic pre-commit hook at: {hook_path}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error installing pre-commit hook: {str(e)}")]

@registry.register(Tool(
    name="memento_list_active_coercion_rules",
    description="List all deterministic Active Coercion rules currently defined for the workspace.",
    inputSchema={"type": "object", "properties": {}}
))
async def memento_list_active_coercion_rules(arguments: dict, ctx, access_manager) -> list[TextContent]:
    rules = ctx.active_coercion.get("rules", [])
    if not rules:
        return [TextContent(type="text", text="No Active Coercion rules defined for this workspace.")]
    formatted = json.dumps(rules, indent=2, ensure_ascii=False)
    return [TextContent(type="text", text=f"Active Coercion rules for workspace {ctx.workspace_root}:\n{formatted}")]

@registry.register(Tool(
    name="memento_add_active_coercion_rule",
    description="Add a new deterministic Active Coercion rule to the workspace. This rule will automatically block commits or trigger IDE warnings if violated.",
    inputSchema={
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "Unique identifier for the rule (e.g. 'no_print_backend')"},
            "enabled": {"type": "boolean", "description": "Whether the rule is active (default: true)"},
            "path_globs": {"type": "array", "items": {"type": "string"}, "description": "List of glob patterns to match files (e.g. ['backend/**/*.py'])"},
            "regex": {"type": "string", "description": "The exact regex pattern that triggers the violation (e.g. '\\\\bprint\\\\(')"},
            "message": {"type": "string", "description": "The error message shown to the developer"},
            "severity": {"type": "string", "enum": ["block", "warn"], "description": "Violation severity (default: 'block')"},
            "override_token": {"type": "string", "description": "A token that, if present in the file, bypasses the rule (default: 'memento-override')"}
        },
        "required": ["id", "path_globs", "regex", "message"]
    }
))
async def memento_add_active_coercion_rule(arguments: dict, ctx, access_manager) -> list[TextContent]:
    rule_id = arguments.get("id")
    path_globs = arguments.get("path_globs")
    regex = arguments.get("regex")
    message = arguments.get("message")
    
    if not rule_id or not path_globs or not regex or not message:
        raise ValueError("Missing required fields: id, path_globs, regex, message")

    new_rule = {
        "id": rule_id,
        "enabled": arguments.get("enabled", True),
        "path_globs": path_globs,
        "regex": regex,
        "message": message,
        "severity": arguments.get("severity", "block"),
        "override_token": arguments.get("override_token", "memento-override")
    }

    rules = ctx.active_coercion.get("rules", [])
    updated_rules = [r for r in rules if r.get("id") != rule_id]
    updated_rules.append(new_rule)
    
    ctx.active_coercion["rules"] = updated_rules
    ctx.save_active_coercion_config()
    
    return [TextContent(type="text", text=f"Successfully added/updated rule '{rule_id}'. Total rules: {len(updated_rules)}")]

@registry.register(Tool(
    name="memento_remove_active_coercion_rule",
    description="Remove an existing Active Coercion rule from the workspace by its ID.",
    inputSchema={
        "type": "object",
        "properties": {
            "rule_id": {"type": "string", "description": "The unique ID of the rule to remove"}
        },
        "required": ["rule_id"]
    }
))
async def memento_remove_active_coercion_rule(arguments: dict, ctx, access_manager) -> list[TextContent]:
    rule_id = arguments.get("rule_id")
    if not rule_id:
        raise ValueError("rule_id is required")

    rules = ctx.active_coercion.get("rules", [])
    initial_len = len(rules)
    updated_rules = [r for r in rules if r.get("id") != rule_id]
    
    if len(updated_rules) == initial_len:
        return [TextContent(type="text", text=f"Rule '{rule_id}' not found.")]
        
    ctx.active_coercion["rules"] = updated_rules
    ctx.save_active_coercion_config()
    
    return [TextContent(type="text", text=f"Successfully removed rule '{rule_id}'. Remaining rules: {len(updated_rules)}")]

@registry.register(Tool(
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
))
async def memento_configure_enforcement(arguments: dict, ctx, access_manager) -> list[TextContent]:
    for lvl in ["level1", "level2", "level3"]:
        if lvl in arguments:
            ctx.enforcement_config[lvl] = arguments[lvl]
            
    if ctx.enforcement_config.get("level3") and (not ctx.daemon or not ctx.daemon.is_running):
        pass
        
    ctx.save_enforcement_config()
    status = ", ".join([f"{k}={v}" for k, v in ctx.enforcement_config.items()])
    return [TextContent(type="text", text=f"Configurazione Goal Enforcement aggiornata:\n{status}")]
