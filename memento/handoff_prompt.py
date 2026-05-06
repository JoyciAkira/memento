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
    ]

    project_state = snapshot.get("project_state") or ""
    if project_state and project_state.strip():
        parts.append("")
        parts.append("PROJECT STATE")
        parts.append(project_state.strip())

    parts.append("")
    parts.append("TO RESUME")
    parts.append(f"Call: memento_resume_session(session_id=\"{session_id}\")")

    return "\n".join(parts).strip() + "\n"


def render_session_diff_prompt(
    *,
    current_snapshot: dict[str, Any],
    previous_snapshot: dict[str, Any] | None,
) -> str:
    """Generate a diff between current and previous session checkpoints."""
    if not previous_snapshot:
        return ""

    parts = ["SESSION DELTA (since last session)", ""]

    prev_goals = {g.get("goal") for g in _as_list(previous_snapshot.get("goals")) if isinstance(g, dict)}
    curr_goals = {g.get("goal") for g in _as_list(current_snapshot.get("goals")) if isinstance(g, dict)}
    new_goals = curr_goals - prev_goals
    removed_goals = prev_goals - curr_goals
    if new_goals:
        parts.append("NEW GOALS:")
        for g in new_goals:
            parts.append(f"  + {g}")
        parts.append("")
    if removed_goals:
        parts.append("REMOVED GOALS:")
        for g in removed_goals:
            parts.append(f"  - {g}")
        parts.append("")
    if not new_goals and not removed_goals:
        parts.append("GOALS: unchanged")
        parts.append("")

    prev_git = previous_snapshot.get("git_context") or ""
    curr_git = current_snapshot.get("git_context") or ""
    if prev_git != curr_git:
        parts.append("GIT CHANGES:")
        if curr_git.strip():
            parts.append(curr_git.strip())
        parts.append("")

    prev_files = set(_as_list(previous_snapshot.get("active_contexts")))
    curr_files = set(_as_list(current_snapshot.get("active_contexts")))
    new_files = curr_files - prev_files
    if new_files:
        parts.append("NEW FILES TOUCHED:")
        for f in sorted(new_files)[:10]:
            parts.append(f"  + {f}")
        parts.append("")

    return "\n".join(parts).strip() + "\n" if len(parts) > 2 else ""
