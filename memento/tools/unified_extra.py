"""Additional unified MCP tools: search, remember, configure, cognitive, health, coercion, kg, notifications."""

import json
import logging
import os

from mcp.types import Tool, TextContent

from memento.registry import registry

logger = logging.getLogger("memento-mcp")


# ---------------------------------------------------------------------------
# memento_search — unified search
# ---------------------------------------------------------------------------

@registry.register(
    Tool(
        name="memento_search",
        description=(
            "Search memories. Modes: basic (FTS), advanced (vNext pipeline), explain (routing trace)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "mode": {
                    "type": "string",
                    "enum": ["basic", "advanced", "explain"],
                    "default": "basic",
                },
                "limit": {"type": "integer", "default": 10},
                "filters": {"type": "object"},
                "trace": {"type": "boolean", "default": False},
                "active_context": {"type": "string"},
                "workspace_root": {"type": "string"},
            },
            "required": ["query"],
        },
    )
)
async def memento_search(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot search. Access: {access_manager.state}")
    query = arguments.get("query", "")
    mode = arguments.get("mode", "basic")
    limit = int(arguments.get("limit") or 10)
    filters = arguments.get("filters")
    active_context = arguments.get("active_context")

    if mode == "basic":
        actual_filters = filters or {}
        if active_context:
            try:
                from memento.ontology import extract_logical_namespace
                ns = extract_logical_namespace(active_context, ctx.workspace_root)
                if ns:
                    actual_filters["module"] = ns
            except Exception:
                pass
        res = await ctx.provider.search(query, user_id="default", filters=actual_filters or None)
        from memento.tools.utils import get_active_goals
        injection = await get_active_goals(ctx) if ctx.enforcement_config.get("level1") else ""
        return [TextContent(type="text", text=f"{injection}Results:\n{json.dumps(res, indent=2, ensure_ascii=False)}")]

    if mode == "advanced":
        res = await ctx.provider.search_vnext_bundle(query, user_id="default", limit=limit, filters=filters, trace=arguments.get("trace", False))
        return [TextContent(type="text", text=json.dumps(res, indent=2, ensure_ascii=False, default=str))]

    if mode == "explain":
        res = await ctx.provider.search_vnext_bundle(query, user_id="default", limit=limit, filters=filters, trace=True)
        explained = {k: res[k] for k in ("query", "routing", "traces") if k in res}
        return [TextContent(type="text", text=json.dumps(explained, indent=2, ensure_ascii=False, default=str))]

    return [TextContent(type="text", text=f"Unknown mode: {mode}")]


# ---------------------------------------------------------------------------
# memento_remember — unified memory write operations
# ---------------------------------------------------------------------------

@registry.register(
    Tool(
        name="memento_remember",
        description=(
            "Memory operations. Actions: add, consolidate, share, evaluate, hit."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "consolidate", "share", "evaluate", "hit"],
                },
                "text": {"type": "string", "description": "Memory text (for add)."},
                "metadata": {"type": "object"},
                "threshold": {"type": "number", "default": 0.92},
                "min_age_hours": {"type": "number", "default": 1},
                "memory_id": {"type": "string"},
                "target_workspace": {"type": "string"},
                "score": {"type": "number"},
                "reason": {"type": "string"},
                "memory_ids": {"type": "array", "items": {"type": "string"}},
                "active_context": {"type": "string"},
                "workspace_root": {"type": "string"},
            },
            "required": ["action"],
        },
    )
)
async def memento_remember(arguments: dict, ctx, access_manager) -> list[TextContent]:
    action = arguments["action"]

    if action == "add":
        if not access_manager.can_write():
            raise PermissionError(f"Cannot add memory. Access: {access_manager.state}")
        text = arguments.get("text", "")
        metadata = arguments.get("metadata") or {}
        active_context = arguments.get("active_context")
        if active_context:
            try:
                from memento.ontology import extract_logical_namespace
                ns = extract_logical_namespace(active_context, ctx.workspace_root)
                if ns:
                    metadata["module"] = ns
            except Exception:
                pass
        result = await ctx.provider.add(text, user_id="default", metadata=metadata or None)
        return [TextContent(type="text", text=f"Memory saved: {result}")]

    if action == "consolidate":
        if not access_manager.can_write():
            raise PermissionError(f"Cannot consolidate. Access: {access_manager.state}")
        from memento.consolidation import ConsolidationEngine
        threshold = float(arguments.get("threshold") or 0.92)
        min_age = float(arguments.get("min_age_hours") or 1)
        engine = ConsolidationEngine(ctx.db_path, threshold=threshold, min_age_hours=min_age)
        result = await engine.consolidate()
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

    if action == "share":
        if not access_manager.can_write():
            raise PermissionError(f"Cannot share. Access: {access_manager.state}")
        memory_id = arguments.get("memory_id", "")
        target = arguments.get("target_workspace", "")
        from memento.cross_workspace import CrossWorkspaceManager
        mgr = CrossWorkspaceManager(ctx.db_path)
        result = await mgr.share_memory(memory_id, target, ctx.workspace_root)
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

    if action == "evaluate":
        if not access_manager.can_write():
            raise PermissionError(f"Cannot evaluate. Access: {access_manager.state}")
        memory_id = arguments.get("memory_id", "")
        score = arguments.get("score")
        reason = arguments.get("reason")
        if score is None or not (0 <= float(score) <= 1):
            return [TextContent(type="text", text="Error: score must be 0-1.")]
        from memento.quality_metrics import QualityMetrics
        metrics = QualityMetrics(ctx.db_path)
        await metrics.record_evaluation(memory_id, float(score), reason)
        return [TextContent(type="text", text=f"Quality evaluation recorded for {memory_id}.")]

    if action == "hit":
        if not access_manager.can_write():
            raise PermissionError(f"Cannot record hit. Access: {access_manager.state}")
        memory_ids = arguments.get("memory_ids") or []
        from memento.relevance_tracker import RelevanceTracker
        tracker = RelevanceTracker(ctx.db_path)
        await tracker.record_hits(memory_ids)
        return [TextContent(type="text", text=f"Recorded hits for {len(memory_ids)} memories.")]

    return [TextContent(type="text", text=f"Unknown action: {action}")]


# ---------------------------------------------------------------------------
# memento_configure — unified configuration
# ---------------------------------------------------------------------------

@registry.register(
    Tool(
        name="memento_configure",
        description=(
            "Configure Memento. Actions: enforcement, coercion, daemon, autonomy, "
            "consolidation_scheduler, kg_scheduler, dependency_tracker, superpowers, access."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "enforcement", "coercion", "daemon", "autonomy",
                        "consolidation_scheduler", "kg_scheduler", "dependency_tracker",
                        "superpowers", "access",
                    ],
                },
                "enabled": {"type": "boolean"},
                "level": {"type": "string"},
                "state": {"type": "string"},
                "warnings": {"type": "boolean"},
                "tasks": {"type": "boolean"},
                "interval_minutes": {"type": "number"},
                "install_git_hooks": {"type": "boolean"},
                "workspace_root": {"type": "string"},
            },
            "required": ["action"],
        },
    )
)
async def memento_configure(arguments: dict, ctx, access_manager) -> list[TextContent]:
    action = arguments["action"]
    enabled = arguments.get("enabled")
    level = arguments.get("level")

    if action == "enforcement":
        if level:
            ctx.enforcement_config[level] = bool(enabled)
        ctx.save_enforcement_config()
        return [TextContent(type="text", text=f"Enforcement config: {ctx.enforcement_config}")]

    if action == "coercion":
        ctx.active_coercion["enabled"] = bool(enabled)
        ctx.save_active_coercion_config()
        if arguments.get("install_git_hooks"):
            from memento.git_hooks import install_pre_commit_hook
            install_pre_commit_hook(ctx.workspace_root)
        return [TextContent(type="text", text=f"Active coercion {'enabled' if enabled else 'disabled'}.")]

    if action == "daemon":
        from memento.tools.cognitive import memento_toggle_precognition as _daemon_impl
        return await _daemon_impl(arguments, ctx, access_manager)

    if action == "autonomy":
        from memento.autonomous import AutonomyLevel
        try:
            AutonomyLevel(level or "off")
        except ValueError:
            return [TextContent(type="text", text="Invalid level. Use: off, passive, active, autonomous.")]
        if ctx.autonomous_agent.is_running:
            ctx.stop_autonomous_agent()
        ctx.autonomy["level"] = level or "off"
        ctx.save_autonomy_config()
        if level and level != "off":
            ctx.start_autonomous_agent()
        return [TextContent(type="text", text=f"Autonomy set to: {level or 'off'}.")]

    if action == "consolidation_scheduler":
        if enabled:
            from memento.consolidation import ConsolidationScheduler
            interval = float(arguments.get("interval_minutes") or 30)
            scheduler = ConsolidationScheduler(
                db_path=ctx.db_path,
                consolidate_fn=ctx.provider.consolidate,
                interval_minutes=interval,
                initial_delay_minutes=5,
            )
            scheduler.start()
            ctx.consolidation_scheduler = scheduler
            return [TextContent(type="text", text=f"Consolidation scheduler started (every {interval}m).")]
        if ctx.consolidation_scheduler:
            ctx.consolidation_scheduler.stop()
            return [TextContent(type="text", text="Consolidation scheduler stopped.")]
        return [TextContent(type="text", text="No scheduler running.")]

    if action == "kg_scheduler":
        if enabled:
            from memento.kg_extraction_scheduler import KGExtractionScheduler
            interval = float(arguments.get("interval_minutes") or 60)
            scheduler = KGExtractionScheduler(
                db_path=ctx.db_path,
                extract_fn=lambda: ctx.provider.extract_kg(max_memories=50),
                interval_minutes=interval,
                initial_delay_minutes=10,
            )
            scheduler.start()
            ctx.kg_extraction_scheduler = scheduler
            return [TextContent(type="text", text=f"KG extraction scheduler started (every {interval}m).")]
        if ctx.kg_extraction_scheduler:
            ctx.kg_extraction_scheduler.stop()
            return [TextContent(type="text", text="KG extraction scheduler stopped.")]
        return [TextContent(type="text", text="No scheduler running.")]

    if action == "dependency_tracker":
        ctx.dependency_tracker["enabled"] = bool(enabled)
        ctx.save_dependency_tracker_config()
        return [TextContent(type="text", text=f"Dependency tracker {'enabled' if enabled else 'disabled'}.")]

    if action == "superpowers":
        warnings = arguments.get("warnings", False)
        tasks = arguments.get("tasks", False)
        access_manager.toggle_superpowers(warnings, tasks)
        return [TextContent(type="text", text=f"Superpowers: warnings={warnings}, tasks={tasks}")]

    if action == "access":
        state = arguments.get("state") or arguments.get("level")
        if state:
            access_manager.set_state(state)
            return [TextContent(type="text", text=f"Access state: {state}")]
        return [TextContent(type="text", text=f"Current access state: {access_manager.state}")]

    return [TextContent(type="text", text=f"Unknown config action: {action}")]


# ---------------------------------------------------------------------------
# memento_cognitive — unified cognitive engine
# ---------------------------------------------------------------------------

@registry.register(
    Tool(
        name="memento_cognitive",
        description=(
            "Cognitive engine. Actions: dream (creative insight), align (goal check), "
            "warnings (spider-sense), tasks (auto-generate)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["dream", "align", "warnings", "tasks"],
                },
                "content": {"type": "string", "description": "Code/plan to evaluate (for align)."},
                "context": {"type": "string", "description": "Topic/context (for dream, warnings)."},
                "active_context": {"type": "string"},
                "workspace_root": {"type": "string"},
            },
            "required": ["action"],
        },
    )
)
async def memento_cognitive(arguments: dict, ctx, access_manager) -> list[TextContent]:
    action = arguments["action"]

    if action == "dream":
        context = arguments.get("context") or arguments.get("active_context")
        result = await ctx.cognitive_engine.synthesize_dreams(context)
        return [TextContent(type="text", text=result)]

    if action == "align":
        content = arguments.get("content", "")
        if ctx.enforcement_config.get("level2"):
            result = await ctx.cognitive_engine.check_goal_alignment(
                content, context=arguments.get("active_context"),
            )
            return [TextContent(type="text", text=result)]
        return [TextContent(type="text", text="Goal Enforcer L2 is disabled. Enable via memento_configure action=enforcement level=level2 enabled=true.")]

    if action == "warnings":
        if not access_manager.warnings_enabled:
            return [TextContent(type="text", text="Proactive warnings disabled. Enable via memento_configure action=superpowers warnings=true.")]
        context = arguments.get("context", "")
        warnings = await ctx.cognitive_engine.get_warnings(context)
        return [TextContent(type="text", text=warnings)]

    if action == "tasks":
        if not access_manager.auto_tasks_enabled:
            return [TextContent(type="text", text="Auto-tasks disabled. Enable via memento_configure action=superpowers tasks=true.")]
        result = await ctx.cognitive_engine.generate_tasks()
        return [TextContent(type="text", text=result)]

    return [TextContent(type="text", text=f"Unknown cognitive action: {action}")]


# ---------------------------------------------------------------------------
# memento_health — unified diagnostics
# ---------------------------------------------------------------------------

@registry.register(
    Tool(
        name="memento_health",
        description=(
            "System diagnostics. Actions: status (quick overview), health (full report), "
            "memory (stats), kg (knowledge graph), quality (quality report), "
            "relevance (hot/cold), cache (predictive), explain (search trace)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "health", "memory", "kg", "quality", "relevance", "cache", "explain"],
                    "default": "status",
                },
                "query": {"type": "string", "description": "Query to explain (for explain)."},
                "workspace_root": {"type": "string"},
            },
        },
    )
)
async def memento_health(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot read health. Access: {access_manager.state}")
    action = arguments.get("action", "status")
    db_path = ctx.db_path

    if action == "status":
        lines = ["Memento Status", "=" * 40]
        lines.append(f"Workspace: {ctx.workspace_root}")
        lines.append(f"DB: {db_path}")
        lines.append(f"Enforcement: {ctx.enforcement_config}")
        lines.append(f"Daemon: {'running' if ctx.daemon and ctx.daemon.is_running else 'stopped'}")
        auto = ctx.autonomous_agent.get_status()
        lines.append(f"Autonomy: {auto['level']} ({'running' if auto['running'] else 'stopped'})")
        goals = await ctx.provider.list_goals(active_only=True, limit=3)
        if goals:
            lines.append(f"Active goals ({len(goals)}):")
            for g in goals:
                lines.append(f"  - {g.get('goal', '')[:80]}")
        return [TextContent(type="text", text="\n".join(lines))]

    if action == "health":
        kg_path = getattr(ctx.provider, "kg_db_path", db_path)
        from memento.quality_metrics import QualityMetrics
        metrics = QualityMetrics(db_path, kg_path)
        result = await metrics.system_health()
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False, default=str))]

    if action == "memory":
        from memento.quality_metrics import QualityMetrics
        metrics = QualityMetrics(db_path)
        result = await metrics.memory_stats()
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False, default=str))]

    if action == "kg":
        kg_path = getattr(ctx.provider, "kg_db_path", db_path)
        from memento.quality_metrics import QualityMetrics
        metrics = QualityMetrics(db_path, kg_path)
        result = await metrics.kg_health()
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False, default=str))]

    if action == "quality":
        from memento.quality_metrics import QualityMetrics
        metrics = QualityMetrics(db_path)
        result = await metrics.get_quality_report()
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False, default=str))]

    if action == "relevance":
        from memento.relevance_tracker import RelevanceTracker
        tracker = RelevanceTracker(db_path)
        result = await tracker.get_stats()
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False, default=str))]

    if action == "cache":
        from memento.predictive_cache import PredictiveCache
        cache = PredictiveCache(db_path)
        result = await cache.cache_stats()
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False, default=str))]

    if action == "explain":
        query = arguments.get("query", "")
        trace_path = os.path.join(ctx.memento_dir, "traces", "last_search.json")
        if os.path.exists(trace_path):
            with open(trace_path, "r") as f:
                data = json.load(f)
            return [TextContent(type="text", text=json.dumps(data, indent=2, ensure_ascii=False))]
        return [TextContent(type="text", text=json.dumps({"query": query, "error": "no trace available"}))]

    return [TextContent(type="text", text=f"Unknown health action: {action}")]


# ---------------------------------------------------------------------------
# memento_coercion — unified coercion CRUD
# ---------------------------------------------------------------------------

@registry.register(
    Tool(
        name="memento_coercion",
        description=(
            "Active Coercion management. Actions: list_presets, apply_preset, "
            "list_rules, add_rule, remove_rule, install_hooks."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_presets", "apply_preset", "list_rules", "add_rule", "remove_rule", "install_hooks"],
                },
                "preset": {"type": "string"},
                "rule_id": {"type": "string"},
                "rule": {"type": "object"},
                "workspace_root": {"type": "string"},
            },
            "required": ["action"],
        },
    )
)
async def memento_coercion(arguments: dict, ctx, access_manager) -> list[TextContent]:
    from memento.tools.coercion import (
        memento_list_active_coercion_presets as _list_presets,
        memento_apply_active_coercion_preset as _apply_preset,
        memento_list_active_coercion_rules as _list_rules,
        memento_add_active_coercion_rule as _add_rule,
        memento_remove_active_coercion_rule as _remove_rule,
        memento_install_git_hooks as _install_hooks,
    )
    action = arguments["action"]

    if action == "list_presets":
        return await _list_presets(arguments, ctx, access_manager)
    if action == "apply_preset":
        arguments["preset"] = arguments.get("preset")
        return await _apply_preset(arguments, ctx, access_manager)
    if action == "list_rules":
        return await _list_rules(arguments, ctx, access_manager)
    if action == "add_rule":
        return await _add_rule(arguments, ctx, access_manager)
    if action == "remove_rule":
        return await _remove_rule(arguments, ctx, access_manager)
    if action == "install_hooks":
        return await _install_hooks(arguments, ctx, access_manager)

    return [TextContent(type="text", text=f"Unknown coercion action: {action}")]


# ---------------------------------------------------------------------------
# memento_kg — unified KG operations
# ---------------------------------------------------------------------------

@registry.register(
    Tool(
        name="memento_kg",
        description="Knowledge Graph operations. Actions: extract, health, cross_workspace_stats.",
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["extract", "health", "cross_workspace_stats"],
                },
                "max_memories": {"type": "integer", "default": 50},
                "workspace_root": {"type": "string"},
            },
            "required": ["action"],
        },
    )
)
async def memento_kg(arguments: dict, ctx, access_manager) -> list[TextContent]:
    action = arguments["action"]

    if action == "extract":
        if not access_manager.can_write():
            raise PermissionError(f"Cannot extract KG. Access: {access_manager.state}")
        max_mem = int(arguments.get("max_memories") or 50)
        result = await ctx.provider.extract_kg(max_mem)
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False, default=str))]

    if action == "health":
        kg_path = getattr(ctx.provider, "kg_db_path", ctx.db_path)
        from memento.quality_metrics import QualityMetrics
        metrics = QualityMetrics(ctx.db_path, kg_path)
        result = await metrics.kg_health()
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False, default=str))]

    if action == "cross_workspace_stats":
        from memento.cross_workspace import CrossWorkspaceManager
        mgr = CrossWorkspaceManager(ctx.db_path)
        result = await mgr.get_sync_stats()
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False, default=str))]

    return [TextContent(type="text", text=f"Unknown KG action: {action}")]


# ---------------------------------------------------------------------------
# memento_notifications — unified notifications
# ---------------------------------------------------------------------------

@registry.register(
    Tool(
        name="memento_notifications",
        description="Notifications. Actions: configure, list, dismiss.",
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["configure", "list", "dismiss"],
                },
                "enabled": {"type": "boolean"},
                "topics": {"type": "array", "items": {"type": "string"}},
                "min_confidence": {"type": "number"},
                "notification_id": {"type": "string"},
                "include_dismissed": {"type": "boolean", "default": False},
                "workspace_root": {"type": "string"},
            },
            "required": ["action"],
        },
    )
)
async def memento_notifications(arguments: dict, ctx, access_manager) -> list[TextContent]:
    action = arguments["action"]
    from memento.notifications import NotificationManager
    mgr = NotificationManager(ctx.db_path)

    if action == "configure":
        config = {}
        if "enabled" in arguments:
            config["enabled"] = arguments["enabled"]
        if "topics" in arguments:
            config["topics"] = arguments["topics"]
        if "min_confidence" in arguments:
            config["min_confidence"] = arguments["min_confidence"]
        result = mgr.configure(**{k: v for k, v in config.items()})
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

    if action == "list":
        include = arguments.get("include_dismissed", False)
        result = mgr.get_pending_notifications(include_dismissed=include)
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False, default=str))]

    if action == "dismiss":
        nid = arguments.get("notification_id", "")
        result = mgr.dismiss(nid)
        return [TextContent(type="text", text=f"Notification {nid} dismissed: {result}")]

    return [TextContent(type="text", text=f"Unknown notification action: {action}")]
