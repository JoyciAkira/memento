"""MCP tools for real-time notifications."""

import json
import logging

from mcp.types import Tool, TextContent

from memento.registry import registry

logger = logging.getLogger("memento-mcp")


@registry.register(
    Tool(
        name="memento_configure_notifications",
        description="Configure notification settings — enable/disable, set topics, set confidence threshold.",
        inputSchema={
            "type": "object",
            "properties": {
                "enabled": {
                    "type": "boolean",
                    "description": "Enable or disable notifications.",
                },
                "topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Notification topics to listen for. Allowed: memory_added, consolidation, kg_extraction, relevance_alert, quality_alert.",
                },
                "min_confidence": {
                    "type": "number",
                    "description": "Minimum confidence to trigger notification (0.0-1.0).",
                },
            },
        },
    )
)
async def memento_configure_notifications(arguments: dict, ctx, access_manager) -> list[TextContent]:
    from memento.notifications import NotificationManager

    manager = NotificationManager(db_path=ctx.db_path)

    enabled = arguments.get("enabled")
    topics = arguments.get("topics")
    min_confidence = arguments.get("min_confidence")

    config = manager.configure(
        enabled=enabled,
        topics=topics,
        min_confidence=min_confidence,
    )
    return [TextContent(type="text", text=f"Notification config updated:\n{json.dumps(config, indent=2)}")]


@registry.register(
    Tool(
        name="memento_get_pending_notifications",
        description="Get pending proactive notifications — relevant context alerts and memory events.",
        inputSchema={
            "type": "object",
            "properties": {
                "include_dismissed": {
                    "type": "boolean",
                    "description": "Include dismissed notifications. Default: false.",
                },
            },
        },
    )
)
async def handler(arguments: dict, ctx, access_manager) -> list[TextContent]:
    from memento.notifications import NotificationManager

    manager = NotificationManager(db_path=ctx.db_path)
    notifications = manager.get_pending_notifications(
        include_dismissed=arguments.get("include_dismissed", False),
    )
    if not notifications:
        return [TextContent(type="text", text="No pending notifications.")]

    parts = ["Pending Notifications:"]
    for n in notifications:
        parts.append(f"\n[{n['topic']}] {n['title']}")
        parts.append(f"  {n['body'][:150]}")
        parts.append(f"  ID: {n['id']}")

    return [TextContent(type="text", text="\n".join(parts))]


@registry.register(
    Tool(
        name="memento_dismiss_notification",
        description="Dismiss a notification so it no longer appears.",
        inputSchema={
            "type": "object",
            "properties": {
                "notification_id": {
                    "type": "string",
                    "description": "The notification ID to dismiss.",
                },
            },
            "required": ["notification_id"],
        },
    )
)
async def memento_dismiss_notification(arguments: dict, ctx, access_manager) -> list[TextContent]:
    from memento.notifications import NotificationManager

    manager = NotificationManager(db_path=ctx.db_path)
    notification_id = arguments["notification_id"]
    dismissed = manager.dismiss(notification_id)
    if dismissed:
        return [TextContent(type="text", text=f"Notification {notification_id} dismissed.")]
    return [TextContent(type="text", text=f"Notification {notification_id} not found or already dismissed.")]
