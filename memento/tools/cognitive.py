import logging
from mcp.types import Tool, TextContent
from memento.registry import registry

logger = logging.getLogger("memento-mcp")

@registry.register(Tool(
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
))
async def memento_toggle_precognition(arguments: dict, ctx, access_manager) -> list[TextContent]:
    enabled = arguments.get("enabled", False)
    
    async def _local_callback(filepath, content):
        if ctx.active_coercion.get("enabled"):
            from memento.active_coercion import normalize_hard_rules, check_text_against_rules

            rules = normalize_hard_rules(ctx.active_coercion.get("rules", []))
            violations = check_text_against_rules(
                workspace_root=ctx.workspace_root,
                rules=rules,
                file_path=filepath,
                content=content,
            )
            block = [v for v in violations if v.severity == "block"]
            if block:
                from mcp.server import request_ctx

                try:
                    req_ctx = request_ctx.get()
                    if req_ctx and req_ctx.session:
                        first = block[0]
                        await req_ctx.session.send_notification(
                            "memento/active_coercion_block",
                            {
                                "file": filepath,
                                "rule_id": first.rule_id,
                                "message": first.message,
                                "violations": [
                                    {
                                        "rule_id": v.rule_id,
                                        "message": v.message,
                                        "severity": v.severity,
                                    }
                                    for v in block
                                ],
                            },
                        )
                except Exception as e:
                    logger.error(f"Failed to send active coercion notification: {e}")

        warning = await ctx.cognitive_engine.evaluate_raw_context(content, filepath=filepath)
        deviation = ""
        if ctx.enforcement_config.get("level3"):
            alignment = await ctx.cognitive_engine.check_goal_alignment(content)
            if "❌ REJECTED" in alignment:
                deviation = alignment
        
        final_alert = warning
        if deviation:
            final_alert += f"\n\n{deviation}" if final_alert else deviation
            
        if final_alert:
            try:
                await ctx.cognitive_engine.consolidate(
                    event=f"Relevant workspace change detected in {filepath}",
                    actual_outcome=content[:1200],
                    force_consolidate=False,
                )
            except Exception as e:
                logger.debug(f"Autonomous consolidation skipped for {filepath}: {e}")

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
    state_str = "STARTED" if is_running else "STOPPED"
    return [TextContent(type="text", text=f"Pre-cognitive daemon {state_str} for workspace {ctx.workspace_root}.")]

@registry.register(Tool(
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
))
async def memento_synthesize_dreams(arguments: dict, ctx, access_manager) -> list[TextContent]:
    context = arguments.get("context", "")
    try:
        insight = await ctx.cognitive_engine.synthesize_dreams(context)
        return [TextContent(type="text", text=insight)]
    except Exception as e:
        logger.error(f"Error in dream synthesis: {e}")
        return [TextContent(type="text", text=f"Error entering Dream State: {str(e)}")]

@registry.register(Tool(
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
))
async def memento_check_goal_alignment(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not ctx.enforcement_config.get("level2"):
        return [TextContent(type="text", text="Level 2 Enforcement (Strict Mentor) is currently disabled. Use memento_configure_enforcement to enable it.")]
        
    content_val = arguments.get("content", "")
    active_ctx = arguments.get("active_context") or ""
    try:
        evaluation = await ctx.cognitive_engine.check_goal_alignment(
            content_val, context=active_ctx if isinstance(active_ctx, str) else ""
        )
        return [TextContent(type="text", text=evaluation)]
    except Exception as e:
        return [TextContent(type="text", text=f"Error evaluating alignment: {str(e)}")]
