from __future__ import annotations

from typing import Any, List


def _as_list(v: Any) -> list:
    return v if isinstance(v, list) else []


def _cap(text: str, limit: int = 800) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _derive_blockers(events: List[dict]) -> List[str]:
    """Enterprise 'known blockers': error events + failure-looking results."""
    blockers: List[str] = []
    fail_markers = ("error", "exception", "traceback", "failed", "cannot", "denied", "timeout")
    for e in events:
        if not isinstance(e, dict):
            continue
        tool = e.get("tool_name") or "?"
        res = (e.get("result_summary") or "").lower()
        if e.get("is_error") or any(m in res for m in fail_markers):
            snippet = _cap((e.get("result_summary") or "").replace("\n", " "), 160)
            blockers.append(f"- {tool}: {snippet}")
    return blockers[:10]


def _derive_next_steps(events: List[dict], goals: List[dict]) -> List[str]:
    """Enterprise 'next steps': pending goals + where the agent left off."""
    steps: List[str] = []
    for g in goals[:5]:
        goal = g.get("goal") if isinstance(g, dict) else g
        if goal:
            steps.append(f"- Pursue goal: {goal}")
    recent = [e.get("tool_name") for e in events[:3] if isinstance(e, dict) and e.get("tool_name")]
    if recent:
        steps.append("- Continue from: " + ", ".join(reversed(recent)))
    if not steps:
        steps.append("- No pending goals recorded; resume from last tool activity.")
    return steps[:8]


def render_handoff_prompt(
    *,
    session_id: str,
    snapshot: dict[str, Any],
    lossless: bool = True,
) -> str:
    """Render an enterprise handoff prompt that loses NO context.

    When ``lossless`` is True (default) every captured item is included
    (goals, full L1/L2/L3, all tool-call events with arguments + results, KG,
    decisions). Per-item display is capped at a generous limit to avoid absurd
    sizes, but the *structure* (which items existed) is never dropped.

    Adds super-intelligent sections: KNOWN BLOCKERS and NEXT STEPS, derived from
    the event/goal log, plus a TOOL-CALL REPLAY index for exact resume.
    """
    ws = snapshot.get("workspace_root") or ""
    reason = snapshot.get("reason") or ""
    summary = snapshot.get("summary") or ""
    goals = _as_list(snapshot.get("goals"))
    l1 = _as_list(snapshot.get("l1"))
    l2 = _as_list(snapshot.get("l2"))
    l3 = _as_list(snapshot.get("l3"))
    files = _as_list(snapshot.get("active_contexts"))
    git_context = snapshot.get("git_context") or ""
    events = _as_list(snapshot.get("recent_events"))
    project_state = snapshot.get("project_state") or ""
    kg_summary = snapshot.get("kg_summary") or ""
    decisions = _as_list(snapshot.get("decisions"))
    session_diff = snapshot.get("session_diff") or ""

    # Lossless caps: include ALL items; only per-item text is capped.
    l1_cap = len(l1) if lossless else 20
    ev_cap = len(events) if lossless else 15

    goals_block = "\n".join(
        f"- {g.get('goal')}" for g in goals if isinstance(g, dict) and g.get("goal")
    ) or "(none)"

    l1_lines = "\n".join(
        f"- {i.get('id')}: {_cap(str(i.get('content', '')))}"
        for i in l1[:l1_cap]
        if isinstance(i, dict) and i.get("id") is not None
    ) or "(empty)"

    def _tier_block(items: List[dict], label: str) -> str:
        if not items:
            return ""
        lines = "\n".join(
            f"- {_cap(str(i.get('content', i.get('id', ''))), 400)}"
            for i in items[:l1_cap]
            if isinstance(i, dict)
        )
        return f"\n{label}\n" + (lines or "(empty)")

    files_block = "\n".join(f"- {p}" for p in files if isinstance(p, str) and p) or "(none)"

    # Tool-call replay index (full, lossless) — enables exact resume.
    replay_lines: List[str] = []
    for e in events[:ev_cap]:
        if not isinstance(e, dict):
            continue
        tool = e.get("tool_name") or "?"
        args = _cap(e.get("arguments_summary") or "", 300)
        res = _cap(e.get("result_summary") or "", 400)
        flag = " [ERROR]" if e.get("is_error") else ""
        replay_lines.append(f"{tool}{flag}\n    in : {args}\n    out: {res}")
    replay_block = "\n".join(replay_lines) if replay_lines else "(none)"

    blockers = _derive_blockers(events)
    blockers_block = "\n".join(blockers) if blockers else "(none)"
    next_steps = _derive_next_steps(events, goals)
    next_block = "\n".join(next_steps)

    decisions_block = "\n".join(
        f"- {_cap(str(d), 300)}" for d in decisions if d
    ) if decisions else "(none)"

    parts = [
        "MEMENTO SESSION HANDOFF (lossless)",
        f"Session: {session_id}",
        f"Workspace: {ws}",
        f"Reason: {reason}",
        "",
        "WHAT I WAS DOING",
        summary or "(no summary available)",
        "",
        "ACTIVE GOALS",
        goals_block,
        "",
        "WORKING MEMORY (L1)",
        l1_lines,
        _tier_block(l2, "EPISODIC MEMORY (L2)"),
        _tier_block(l3, "SEMANTIC MEMORY (L3)"),
        "",
        "FILES / ACTIVE CONTEXTS",
        files_block,
        "",
        "GIT CONTEXT",
        git_context.strip() or "(not a git repo / unavailable)",
        "",
        "TOOL-CALL REPLAY (exact, for resume)",
        replay_block,
        "",
        "KNOWN BLOCKERS",
        blockers_block,
        "",
        "NEXT STEPS",
        next_block,
        "",
        "DECISIONS / OPEN THREADS",
        decisions_block,
    ]

    if project_state and project_state.strip():
        parts.append("")
        parts.append("PROJECT STATE")
        parts.append(_cap(project_state.strip(), 1200))

    if kg_summary and str(kg_summary).strip():
        parts.append("")
        parts.append("KNOWLEDGE GRAPH")
        parts.append(_cap(str(kg_summary).strip(), 1200))

    if session_diff.strip():
        parts.append("")
        parts.append("SESSION DELTA (since previous session)")
        parts.append(session_diff.strip())

    parts.append("")
    parts.append("TO RESUME (zero context loss)")
    parts.append(f'Call: memento_session(action="resume", session_id="{session_id}", lossless=true)')

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
