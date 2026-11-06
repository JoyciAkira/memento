"""Tests for enterprise lossless handoff + resume prompt rendering."""

from memento.handoff_prompt import (
    render_handoff_prompt,
    _derive_blockers,
    _derive_next_steps,
)


def _snapshot(n_l1=25, n_events=20, with_error=True):
    l1 = [
        {"id": f"m{i}", "content": f"working memory item number {i}"}
        for i in range(n_l1)
    ]
    events = []
    for i in range(n_events):
        err = (i == 3) and with_error
        events.append(
            {
                "tool_name": f"tool_{i}",
                "active_context": f"file_{i}.py",
                "arguments_summary": f'{{"q": "query {i}"}}',
                "result_summary": "ok result" if not err else "Error: something failed",
                "is_error": err,
                "created_at": f"2026-07-16T1{i%10}:00:00",
            }
        )
    return {
        "reason": "manual",
        "workspace_root": "/tmp/ws",
        "summary": "Was fixing the auth bug.",
        "goals": [{"goal": "Fix auth"}, {"goal": "Refactor DB"}],
        "l1": l1,
        "active_contexts": ["a.py", "b.py"],
        "git_context": "on branch main",
        "recent_events": events,
        "project_state": "v1.1.0",
        "kg_summary": "entities: 12",
    }


def test_lossless_includes_all_l1_items():
    snap = _snapshot(n_l1=25)
    out = render_handoff_prompt(session_id="s1", snapshot=snap, lossless=True)
    # All 25 L1 ids present (no truncation at 20)
    for i in range(25):
        assert f"m{i}" in out


def test_lossless_includes_all_events_and_replay():
    snap = _snapshot(n_events=20)
    out = render_handoff_prompt(session_id="s1", snapshot=snap, lossless=True)
    for i in range(20):
        assert f"tool_{i}" in out
    assert "TOOL-CALL REPLAY" in out


def test_compact_mode_truncates_like_legacy():
    snap = _snapshot(n_l1=25, n_events=20)
    out = render_handoff_prompt(session_id="s1", snapshot=snap, lossless=False)
    # Legacy caps: L1[:20], events[:15]
    assert "m24" not in out
    assert "tool_19" not in out
    assert "m19" in out
    assert "tool_14" in out


def test_known_blockers_derived_from_errors():
    snap = _snapshot(with_error=True)
    out = render_handoff_prompt(session_id="s1", snapshot=snap, lossless=True)
    assert "KNOWN BLOCKERS" in out
    assert "tool_3" in out
    assert "something failed" in out


def test_next_steps_derived():
    snap = _snapshot()
    out = render_handoff_prompt(session_id="s1", snapshot=snap, lossless=True)
    assert "NEXT STEPS" in out
    assert "Pursue goal: Fix auth" in out
    assert "Continue from:" in out


def test_resume_command_is_lossless_flagged():
    snap = _snapshot()
    out = render_handoff_prompt(session_id="s1", snapshot=snap, lossless=True)
    assert "lossless=true" in out
    assert "zero context loss" in out.lower()


def test_project_state_and_kg_present():
    snap = _snapshot()
    out = render_handoff_prompt(session_id="s1", snapshot=snap, lossless=True)
    assert "PROJECT STATE" in out and "v1.1.0" in out
    assert "KNOWLEDGE GRAPH" in out and "entities: 12" in out


def test_derive_blockers_helper():
    events = [{"tool_name": "x", "result_summary": "Traceback: boom", "is_error": True}]
    assert any("x" in b for b in _derive_blockers(events))


def test_derive_next_steps_helper():
    goals = [{"goal": "Ship it"}]
    steps = _derive_next_steps([], goals)
    assert any("Ship it" in s for s in steps)
