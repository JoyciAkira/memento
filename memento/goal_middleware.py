"""Lightweight goal-driven middleware: runs on every tool call without a separate agent loop."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger("memento-goal-middleware")


def _is_goal_relevant_tool(tool_name: str) -> bool:
    """Determine if a tool call is likely relevant for goal tracking."""
    skip_prefixes = (
        "memento_status",
        "memento_list_",
        "memento_session_",
        "memento_begin_",
        "memento_project_state_",
        "memento_get_",
    )
    return not any(tool_name.startswith(p) for p in skip_prefixes)


async def per_call_goal_check(
    *,
    tool_name: str,
    arguments: dict,
    ctx: Any,
    session_id: str,
) -> str | None:
    """
    Lightweight goal awareness check that runs on every relevant tool call.
    Returns a warning string if goals exist but the current work might be drifting,
    or None if everything looks aligned or no goals are set.
    """
    if not _is_goal_relevant_tool(tool_name):
        return None

    try:
        goals = await ctx.provider.list_goals(active_only=True, limit=5)
        if not goals:
            return None

        active_context = arguments.get("active_context", "")
        query = arguments.get("query", "")
        text = arguments.get("text", "")
        combined = f"{active_context} {query} {text}".lower()

        goal_texts = [g.get("goal", "").lower() for g in goals if isinstance(g, dict)]
        if not goal_texts:
            return None

        relevant_keywords = []
        for gt in goal_texts:
            words = [w for w in gt.split() if len(w) > 3]
            relevant_keywords.extend(words[:5])

        matches = sum(1 for kw in relevant_keywords if kw in combined)

        if not relevant_keywords:
            return None

        ratio = matches / min(len(relevant_keywords), 10)

        if ratio < 0.1 and relevant_keywords:
            goal_names = [g.get("goal", "")[:60] for g in goals[:3] if isinstance(g, dict)]
            return (
                f"[GOAL AWARENESS] Current work may not align with active goals. "
                f"Active goals: {', '.join(goal_names)}. "
                f"Consider whether this action advances project objectives."
            )

        return None
    except Exception:
        return None


async def session_progress_report(*, ctx: Any, session_id: str) -> str | None:
    """
    Generate a micro progress report comparing current session activity to active goals.
    Called periodically (every N events) during a session.
    """
    try:
        goals = await ctx.provider.list_goals(active_only=True, limit=5)
        if not goals:
            return None

        events = await ctx.session_manager.store.get_recent_events(session_id=session_id, limit=20)
        if not events:
            return None

        tool_names = [e.get("tool_name", "") for e in events if isinstance(e, dict)]
        if not tool_names:
            return None

        goal_texts = [g.get("goal", "").lower() for g in goals if isinstance(g, dict)]
        combined_tools = " ".join(tool_names).lower()

        aligned = 0
        for gt in goal_texts:
            words = [w for w in gt.split() if len(w) > 4]
            if any(w in combined_tools for w in words):
                aligned += 1

        total = len(goals)
        if total == 0:
            return None

        lines = [f"[SESSION PROGRESS] {aligned}/{total} goals appear addressed in this session."]
        if aligned == 0 and total > 0:
            goal_names = [g.get("goal", "")[:50] for g in goals[:3] if isinstance(g, dict)]
            lines.append(f"  Unaddressed: {', '.join(goal_names)}")

        return "\n".join(lines)
    except Exception:
        return None
