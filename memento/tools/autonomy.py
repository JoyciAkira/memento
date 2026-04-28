"""MCP tools for controlling Memento's autonomous agent."""

import json
import logging

from mcp.types import Tool, TextContent
from memento.registry import registry

logger = logging.getLogger("memento-mcp")

_LEVEL_HELP = (
    "off = no autonomous behavior | "
    "passive = observe only, no modifications | "
    "active = consolidate, extract KG, warm caches, detect anomalies | "
    "autonomous = full autonomy with dream synthesis, goal drift, task generation, health reports"
)


@registry.register(Tool(
    name="memento_set_autonomy",
    description=(
        f"Set the autonomous agent level. Levels: {_LEVEL_HELP}. "
        "The autonomous agent runs a background cognitive loop that observes, reasons, and acts proactively."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "level": {
                "type": "string",
                "enum": ["off", "passive", "active", "autonomous"],
                "description": "Autonomy level to set.",
            }
        },
        "required": ["level"],
    },
))
async def memento_set_autonomy(arguments: dict, ctx, access_manager) -> list[TextContent]:
    level = arguments.get("level")
    if not level:
        raise ValueError("The 'level' parameter is required.")

    from memento.autonomous import AutonomyLevel, LEVEL_DESCRIPTIONS

    try:
        autonomy_level = AutonomyLevel(level)
    except ValueError:
        raise ValueError(f"Invalid level '{level}'. Must be one of: off, passive, active, autonomous")

    was_running = ctx.autonomous_agent.is_running
    if was_running:
        ctx.stop_autonomous_agent()

    ctx.autonomy["level"] = level
    ctx.save_autonomy_config()

    ctx.autonomous_agent.set_level(autonomy_level)

    started = False
    if autonomy_level != AutonomyLevel.OFF:
        started = ctx.start_autonomous_agent()

    description = LEVEL_DESCRIPTIONS.get(autonomy_level, "")
    status_parts = [
        f"Autonomy level set to: {level}",
        f"Description: {description}",
    ]
    if started:
        status_parts.append("Status: STARTED")
    elif was_running and autonomy_level == AutonomyLevel.OFF:
        status_parts.append("Status: STOPPED")
    elif autonomy_level == AutonomyLevel.OFF:
        status_parts.append("Status: OFF")
    else:
        status_parts.append("Status: CONFIGURED (will start on next MCP tool call)")

    return [TextContent(type="text", text="\n".join(status_parts))]


@registry.register(Tool(
    name="memento_autonomy_status",
    description=(
        "Get detailed status of the autonomous agent: current level, cycle count, "
        "recent decisions, actions taken, and error count."
    ),
    inputSchema={"type": "object", "properties": {}},
))
async def memento_autonomy_status(arguments: dict, ctx, access_manager) -> list[TextContent]:
    status = ctx.autonomous_agent.get_status()
    lines = [
        "Autonomous Agent Status",
        "=======================",
        f"Level: {status['level']}",
        f"Description: {status['level_description']}",
        f"Running: {status['running']}",
        f"Interval: {status['interval_seconds']}s",
        f"Cycles completed: {status['cycle_count']}",
        f"Actions taken: {status['stats']['actions_taken']}",
        f"Errors: {status['stats']['errors']}",
        f"Last cycle duration: {status['stats']['last_cycle_duration_ms']}ms",
    ]

    recent = status.get("recent_decisions", [])
    if recent:
        lines.append("\nRecent Decisions:")
        for d in recent[-5:]:
            lines.append(
                f"  [{d['timestamp'][:19]}] {d['action']}: {d['reason']} -> {d['outcome']} "
                f"(confidence: {d['confidence']:.2f})"
            )

    return [TextContent(type="text", text="\n".join(lines))]


@registry.register(Tool(
    name="memento_autonomy_decisions",
    description="Get the full decision log of the autonomous agent for auditing.",
    inputSchema={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Max number of decisions to return (default 50).",
            }
        },
    },
))
async def memento_autonomy_decisions(arguments: dict, ctx, access_manager) -> list[TextContent]:
    limit = arguments.get("limit", 50)
    decisions = ctx.autonomous_agent.get_decision_log(limit=limit)
    if not decisions:
        return [TextContent(type="text", text="No autonomous decisions recorded yet.")]
    return [TextContent(type="text", text=json.dumps(decisions, indent=2, ensure_ascii=False))]
