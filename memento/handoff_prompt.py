from __future__ import annotations

from typing import Any


def _as_list(v: Any) -> list:
    return v if isinstance(v, list) else []


def render_handoff_prompt(*, session_id: str, snapshot: dict[str, Any]) -> str:
    ws = snapshot.get("workspace_root") or ""
    summary = snapshot.get("summary") or ""
    goals = _as_list(snapshot.get("goals"))
    l1 = _as_list(snapshot.get("l1"))
    files = _as_list(snapshot.get("active_contexts"))
    git_context = snapshot.get("git_context") or ""
    events = _as_list(snapshot.get("recent_events"))

    goals_lines = "\n".join(f"- {g.get('goal')}" for g in goals if isinstance(g, dict) and g.get("goal"))
    goals_block = goals_lines if goals_lines else "(none)"

    l1_lines = "\n".join(
        f"- {i.get('id')}: {i.get('content')}"
        for i in l1[:20]
        if isinstance(i, dict) and i.get("id") and i.get("content")
    )
    l1_block = l1_lines if l1_lines else "(empty)"

    files_lines = "\n".join(f"- {p}" for p in files if isinstance(p, str) and p)
    files_block = files_lines if files_lines else "(none)"

    ev_lines = []
    for idx, e in enumerate(reversed(events[:15]), start=1):
        if not isinstance(e, dict):
            continue
        tn = e.get("tool_name") or ""
        ac = e.get("active_context") or ""
        ev_lines.append(f"{idx}. {tn}" + (f" ({ac})" if ac else ""))
    ev_block = "\n".join(ev_lines) if ev_lines else "(none)"

    parts = [
        "MEMENTO SESSION HANDOFF",
        f"Session: {session_id}",
        f"Workspace: {ws}",
        "",
        "WHAT I WAS DOING",
        summary or "(no summary available)",
        "",
        "ACTIVE GOALS",
        goals_block,
        "",
        "WORKING MEMORY (L1)",
        l1_block,
        "",
        "FILES / ACTIVE CONTEXTS",
        files_block,
        "",
        "GIT CONTEXT",
        git_context.strip() or "(not a git repo / unavailable)",
        "",
        "RECENT TOOL CALLS",
        ev_block,
        "",
        "TO RESUME",
        f"Call: memento_resume_session(session_id=\"{session_id}\")",
    ]
    return "\n".join(parts).strip() + "\n"

