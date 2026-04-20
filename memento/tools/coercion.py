import json
import os
from mcp.types import Tool, TextContent
from memento.registry import registry

RULE_MODIFICATION_REQUIRES_CONFIRMATION = (
    os.environ.get("MEMENTO_RULE_CONFIRMATION", "true").strip().lower() == "true"
)

PRESETS: dict[str, list[dict]] = {
    "python-dev-basics": [
        {
            "id": "no_print_py",
            "enabled": True,
            "path_globs": ["**/*.py"],
            "kind": "tree-sitter",
            "language": "python",
            "query": '(call function: (identifier) @fn (#eq? @fn "print"))',
            "message": "Do not use print(). Use structured logging instead.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_pdb_py",
            "enabled": True,
            "path_globs": ["**/*.py"],
            "regex": "\\bpdb\\.set_trace\\(",
            "message": "Do not commit pdb.set_trace().",
            "severity": "block",
            "override_token": "memento-override",
        },
    ],
    "python-strict": [
        {
            "id": "py_strict_no_print",
            "enabled": True,
            "path_globs": ["**/*.py"],
            "kind": "tree-sitter",
            "language": "python",
            "query": '(call function: (identifier) @fn (#eq? @fn "print"))',
            "message": "Do not use print(). Use structured logging instead.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "py_strict_no_pdb",
            "enabled": True,
            "path_globs": ["**/*.py"],
            "regex": "\\bpdb\\.set_trace\\(",
            "message": "Do not commit pdb.set_trace().",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_debugger_py",
            "enabled": True,
            "path_globs": ["**/*.py"],
            "regex": "\\bbreakpoint\\(\\)",
            "message": "Do not commit breakpoint() calls.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_bare_except",
            "enabled": True,
            "path_globs": ["**/*.py"],
            "regex": "\\bexcept\\s*:",
            "message": "Bare except clauses catch all exceptions including KeyboardInterrupt and SystemExit. Be specific.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_except_pass",
            "enabled": True,
            "path_globs": ["**/*.py"],
            "regex": "\\bexcept\\s+\\w+\\s*:\\s*pass\\b",
            "message": "Except-pass silently swallows errors. Handle or log the exception.",
            "severity": "warn",
            "override_token": "memento-override",
        },
        {
            "id": "no_import_star",
            "enabled": True,
            "path_globs": ["**/*.py"],
            "regex": "\\bfrom\\s+\\w+\\s+import\\s+\\*",
            "message": "Wildcard imports pollute the namespace and make dependencies unclear.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_mutable_default",
            "enabled": True,
            "path_globs": ["**/*.py"],
            "regex": "\\bdef\\s+\\w+\\([^)]*=\\s*\\[|^def\\s+\\w+\\([^)]*=\\s*\\{|=\\s*set\\(\\)",
            "message": "Mutable default arguments are shared across calls. Use None and initialize inside the function.",
            "severity": "warn",
            "override_token": "memento-override",
        },
        {
            "id": "no_eval",
            "enabled": True,
            "path_globs": ["**/*.py"],
            "regex": "\\beval\\s*\\(",
            "message": "eval() is a security risk. Use ast.literal_eval() or proper parsing.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_exec",
            "enabled": True,
            "path_globs": ["**/*.py"],
            "regex": "\\bexec\\s*\\(",
            "message": "exec() is a security risk and makes code hard to analyze.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_hardcoded_password",
            "enabled": True,
            "path_globs": ["**/*.py"],
            "regex": "(?:password|passwd|pwd|secret|token|api_key|apikey)\\s*=\\s*['\"]",
            "message": "Hardcoded secrets are a security vulnerability. Use environment variables or a secrets manager.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_assert_in_prod",
            "enabled": True,
            "path_globs": ["**/*.py"],
            "regex": "\\bassert\\s+",
            "message": "Assert statements are stripped in optimized mode (-O). Use proper validation.",
            "severity": "warn",
            "override_token": "memento-override",
        },
        {
            "id": "no_todo_without_ticket",
            "enabled": True,
            "path_globs": ["**/*.py"],
            "regex": "#\\s*TODO(?!\\s*\\(#?\\d+|JIRA-|GH-)",
            "message": "TODO comment without ticket reference.",
            "severity": "warn",
            "override_token": "memento-override",
        },
    ],
    "typescript-strict": [
        {
            "id": "no_console_log",
            "enabled": True,
            "path_globs": ["**/*.ts", "**/*.tsx"],
            "kind": "tree-sitter",
            "language": "typescript",
            "query": '(call_expression function: (member_expression object: (identifier) @obj (#eq? @obj "console") property: (property_identifier) @prop (#eq? @prop "log")))',
            "message": "Do not use console.log(). Use a structured logging library.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_debugger_ts",
            "enabled": True,
            "path_globs": ["**/*.ts", "**/*.tsx"],
            "regex": "\\bdebugger\\b",
            "message": "Do not commit debugger statements.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_any_type",
            "enabled": True,
            "path_globs": ["**/*.ts", "**/*.tsx"],
            "regex": ":\\s*any\\b",
            "message": "Do not use the 'any' type. Use proper type annotations.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_as_any",
            "enabled": True,
            "path_globs": ["**/*.ts", "**/*.tsx"],
            "regex": "\\bas\\s+any\\b",
            "message": "Do not cast to 'any'. Use proper type guards or assertions.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_ts_ignore",
            "enabled": True,
            "path_globs": ["**/*.ts", "**/*.tsx"],
            "regex": "//\\s*@ts-ignore",
            "message": "@ts-ignore suppresses errors without fixing them. Fix the underlying type issue.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_ts_expect_error",
            "enabled": True,
            "path_globs": ["**/*.ts", "**/*.tsx"],
            "regex": "//\\s*@ts-expect-error",
            "message": "@ts-expect-error suppresses errors. Only use when intentionally testing type behavior.",
            "severity": "warn",
            "override_token": "memento-override",
        },
        {
            "id": "no_var_ts",
            "enabled": True,
            "path_globs": ["**/*.ts", "**/*.tsx"],
            "regex": "\\bvar\\s+\\w+",
            "message": "Do not use var. Use const or let.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_require_ts",
            "enabled": True,
            "path_globs": ["**/*.ts", "**/*.tsx"],
            "regex": "\\brequire\\s*\\(",
            "message": "Use ES module import instead of require().",
            "severity": "warn",
            "override_token": "memento-override",
        },
        {
            "id": "no_hardcoded_secrets_ts",
            "enabled": True,
            "path_globs": ["**/*.ts", "**/*.tsx"],
            "regex": "(?:password|secret|token|api_key|apikey)\\s*[:=]\\s*['\"]",
            "message": "Hardcoded secrets are a security vulnerability. Use environment variables.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_non_null_assertion",
            "enabled": True,
            "path_globs": ["**/*.ts", "**/*.tsx"],
            "regex": "\\w+!",
            "message": "Non-null assertion (!) bypasses type checking. Use proper type guards.",
            "severity": "warn",
            "override_token": "memento-override",
        },
    ],
    "javascript-safe": [
        {
            "id": "no_console_log_js",
            "enabled": True,
            "path_globs": ["**/*.js", "**/*.jsx", "**/*.mjs"],
            "regex": "\\bconsole\\.log\\(",
            "message": "Do not use console.log(). Use a structured logging library.",
            "severity": "warn",
            "override_token": "memento-override",
        },
        {
            "id": "no_debugger_js",
            "enabled": True,
            "path_globs": ["**/*.js", "**/*.jsx", "**/*.mjs"],
            "regex": "\\bdebugger\\b",
            "message": "Do not commit debugger statements.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_var_js",
            "enabled": True,
            "path_globs": ["**/*.js", "**/*.jsx", "**/*.mjs"],
            "regex": "\\bvar\\s+\\w+",
            "message": "Do not use var. Use const or let.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_eval_js",
            "enabled": True,
            "path_globs": ["**/*.js", "**/*.jsx", "**/*.mjs"],
            "regex": "\\beval\\s*\\(",
            "message": "eval() is a security risk. Avoid at all costs.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_document_write",
            "enabled": True,
            "path_globs": ["**/*.js", "**/*.jsx", "**/*.mjs"],
            "regex": "\\bdocument\\.write\\(",
            "message": "document.write() is a performance and security risk. Use DOM APIs.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_inner_html",
            "enabled": True,
            "path_globs": ["**/*.js", "**/*.jsx", "**/*.mjs"],
            "regex": "\\.innerHTML\\s*=",
            "message": "Direct innerHTML assignment is a XSS risk. Use textContent or DOM APIs.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_alert",
            "enabled": True,
            "path_globs": ["**/*.js", "**/*.jsx", "**/*.mjs"],
            "regex": "\\balert\\s*\\(",
            "message": "Do not use alert(). Use a proper notification UI component.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_hardcoded_secrets_js",
            "enabled": True,
            "path_globs": ["**/*.js", "**/*.jsx", "**/*.mjs"],
            "regex": "(?:password|secret|token|api_key|apikey)\\s*[:=]\\s*['\"]",
            "message": "Hardcoded secrets are a security vulnerability. Use environment variables.",
            "severity": "block",
            "override_token": "memento-override",
        },
    ],
    "react-safe": [
        {
            "id": "no_dangerously_set_inner_html",
            "enabled": True,
            "path_globs": ["**/*.jsx", "**/*.tsx"],
            "regex": "dangerouslySetInnerHTML",
            "message": "dangerouslySetInnerHTML is an XSS risk. Sanitize input or use alternatives.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_inline_function_props",
            "enabled": True,
            "path_globs": ["**/*.jsx", "**/*.tsx"],
            "regex": "onClick=\\{?\\s*\\(\\)\\s*=>",
            "message": "Inline arrow functions in JSX props cause unnecessary re-renders. Extract to a const.",
            "severity": "warn",
            "override_token": "memento-override",
        },
        {
            "id": "no_index_key",
            "enabled": True,
            "path_globs": ["**/*.jsx", "**/*.tsx"],
            "regex": "key=\\{?\\s*(?:index|i|idx)\\b",
            "message": "Using array index as key can cause rendering bugs. Use a stable unique identifier.",
            "severity": "warn",
            "override_token": "memento-override",
        },
        {
            "id": "no_console_in_component",
            "enabled": True,
            "path_globs": ["**/components/**/*.jsx", "**/components/**/*.tsx"],
            "regex": "\\bconsole\\.log\\(",
            "message": "Do not use console.log() in components. Use a structured logging library.",
            "severity": "warn",
            "override_token": "memento-override",
        },
        {
            "id": "no_default_props_class",
            "enabled": True,
            "path_globs": ["**/*.jsx", "**/*.tsx"],
            "regex": "\\.defaultProps\\s*=",
            "message": "defaultProps is deprecated for function components. Use default parameters.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_string_refs",
            "enabled": True,
            "path_globs": ["**/*.jsx", "**/*.tsx"],
            "regex": "ref=[\"']",
            "message": "String refs are deprecated. Use React.createRef() or useRef().",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_direct_state_mutate",
            "enabled": True,
            "path_globs": ["**/*.jsx", "**/*.tsx"],
            "regex": "\\.state\\s*\\.\\w+\\s*=",
            "message": "Never mutate state directly. Use setState() or the updater function.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_use_effect_no_deps",
            "enabled": True,
            "path_globs": ["**/*.jsx", "**/*.tsx"],
            "regex": "useEffect\\s*\\([^)]*\\)\\s*\\{",
            "message": "useEffect without dependency array runs on every render.",
            "severity": "warn",
            "override_token": "memento-override",
        },
    ],
    "go-strict": [
        {
            "id": "no_fmt_println",
            "enabled": True,
            "path_globs": ["**/*.go"],
            "regex": "\\bfmt\\.Println\\(",
            "message": "Use structured logging instead of fmt.Println in production.",
            "severity": "warn",
            "override_token": "memento-override",
        },
        {
            "id": "no_panic_go",
            "enabled": True,
            "path_globs": ["**/*.go"],
            "regex": "\\bpanic\\s*\\(",
            "message": "panic() should not be used in library code. Return errors instead.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_os_exit",
            "enabled": True,
            "path_globs": ["**/*.go"],
            "regex": "\\bos\\.Exit\\s*\\(",
            "message": "os.Exit bypasses deferred functions. Consider returning an error.",
            "severity": "warn",
            "override_token": "memento-override",
        },
        {
            "id": "no_log_fatal",
            "enabled": True,
            "path_globs": ["**/*.go"],
            "regex": "\\blog\\.Fatal",
            "message": "log.Fatal calls os.Exit and bypasses deferred functions. Use structured error handling.",
            "severity": "warn",
            "override_token": "memento-override",
        },
        {
            "id": "no_ignored_error",
            "enabled": True,
            "path_globs": ["**/*.go"],
            "regex": "\\b_\\s*=\\s*\\w+\\(",
            "message": "Do not ignore errors. Handle them or explicitly document why with _ = fn() //nolint:errcheck",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_todo_go",
            "enabled": True,
            "path_globs": ["**/*.go"],
            "regex": "//\\s*TODO",
            "message": "TODO comment found. Consider creating a ticket and referencing it.",
            "severity": "warn",
            "override_token": "memento-override",
        },
        {
            "id": "no_hardcoded_secrets_go",
            "enabled": True,
            "path_globs": ["**/*.go"],
            "regex": "(?:password|secret|token|apikey|api_key)\\s*:=\\s*\"",
            "message": "Hardcoded secrets are a security vulnerability. Use environment variables or config.",
            "severity": "block",
            "override_token": "memento-override",
        },
        {
            "id": "no_global_var_go",
            "enabled": True,
            "path_globs": ["**/*.go"],
            "regex": "^var\\s+\\w+\\s+\\w+",
            "message": "Global variables make code hard to test and reason about. Consider dependency injection.",
            "severity": "warn",
            "override_token": "memento-override",
        },
    ],
}

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
    name="memento_list_active_coercion_presets",
    description="List available Active Coercion preset packs.",
    inputSchema={"type": "object", "properties": {}}
))
async def memento_list_active_coercion_presets(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not PRESETS:
        return [TextContent(type="text", text="No presets available.")]
    names = "\n- ".join(sorted(PRESETS.keys()))
    return [TextContent(type="text", text=f"Available presets:\n- {names}")]

@registry.register(Tool(
    name="memento_apply_active_coercion_preset",
    description="Apply an Active Coercion preset pack to the current workspace (merges by rule id).",
    inputSchema={
        "type": "object",
        "properties": {
            "preset": {"type": "string", "description": "Preset name to apply"}
        },
        "required": ["preset"]
    }
))
async def memento_apply_active_coercion_preset(arguments: dict, ctx, access_manager) -> list[TextContent]:
    preset = arguments.get("preset")
    if not preset or preset not in PRESETS:
        return [TextContent(type="text", text=f"Unknown preset: {preset}")]
    incoming = PRESETS[preset]
    existing = ctx.active_coercion.get("rules", [])
    if not isinstance(existing, list):
        existing = []
    by_id = {r.get("id"): r for r in existing if isinstance(r, dict) and isinstance(r.get("id"), str)}
    for r in incoming:
        if isinstance(r, dict) and isinstance(r.get("id"), str):
            by_id[r["id"]] = r
    ctx.active_coercion["rules"] = list(by_id.values())
    ctx.save_active_coercion_config()
    return [TextContent(type="text", text=f"Applied preset '{preset}'. Total rules: {len(ctx.active_coercion['rules'])}")]

@registry.register(Tool(
    name="memento_add_active_coercion_rule",
    description="Add a new deterministic Active Coercion rule to the workspace. This rule will automatically block commits or trigger IDE warnings if violated.",
    inputSchema={
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "Unique identifier for the rule (e.g. 'no_print_backend')"},
            "enabled": {"type": "boolean", "description": "Whether the rule is active (default: true)"},
            "path_globs": {"type": "array", "items": {"type": "string"}, "description": "List of glob patterns to match files (e.g. ['backend/**/*.py'])"},
            "kind": {"type": "string", "enum": ["regex", "tree-sitter"], "description": "Rule kind (default: regex)"},
            "regex": {"type": "string", "description": "Regex pattern for regex rules (e.g. '\\\\bprint\\\\(')"},
            "language": {"type": "string", "description": "Language name for tree-sitter rules (e.g. 'python')"},
            "query": {"type": "string", "description": "Tree-sitter query string for tree-sitter rules"},
            "message": {"type": "string", "description": "The error message shown to the developer"},
            "severity": {"type": "string", "enum": ["block", "warn"], "description": "Violation severity (default: 'block')"},
            "override_token": {"type": "string", "description": "A token that, if present in the file, bypasses the rule (default: 'memento-override')"}
        },
        "required": ["id", "path_globs", "message"]
    }
))
async def memento_add_active_coercion_rule(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if RULE_MODIFICATION_REQUIRES_CONFIRMATION and not access_manager.can_write():
        raise PermissionError(
            "Rule modification requires write access. "
            "Set MEMENTO_RULE_CONFIRMATION=false to bypass (not recommended for shared workspaces)."
        )

    rule_id = arguments.get("id")
    path_globs = arguments.get("path_globs")
    message = arguments.get("message")
    kind = arguments.get("kind", "regex")
    regex = arguments.get("regex")
    language = arguments.get("language")
    query = arguments.get("query")
    
    if not rule_id or not path_globs or not message:
        raise ValueError("Missing required fields: id, path_globs, message")
    if kind not in ("regex", "tree-sitter"):
        raise ValueError("kind must be 'regex' or 'tree-sitter'")
    if kind == "regex" and not regex:
        raise ValueError("regex is required for kind=regex")
    if kind == "tree-sitter" and (not language or not query):
        raise ValueError("language and query are required for kind=tree-sitter")

    new_rule = {
        "id": rule_id,
        "enabled": arguments.get("enabled", True),
        "path_globs": path_globs,
        "kind": kind,
        "regex": regex,
        "language": language,
        "query": query,
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
    return [TextContent(type="text", text=f"Goal Enforcement configuration updated:\n{status}")]
