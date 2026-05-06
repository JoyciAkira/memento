import json
import os
from typing import Any

from memento.git_context import build_auto_context
from memento.handoff_prompt import render_handoff_prompt
from memento.session_store import SessionStore


class SessionManager:
    def __init__(self, *, db_path: str, workspace_root: str, provider):
        self.db_path = db_path
        self.workspace_root = os.path.abspath(workspace_root)
        self.provider = provider
        self.store = SessionStore(db_path=db_path, workspace_root=self.workspace_root)

    async def ensure_session(self) -> str:
        return await self.store.ensure_active_session()

    async def create_checkpoint(self, *, session_id: str, reason: str) -> dict[str, Any]:
        await self.provider.initialize()

        goals = await self.provider.list_goals(context=None, active_only=True, limit=50, offset=0)
        try:
            l1 = self.provider.orchestrator.l1.dump()
        except Exception:
            l1 = []

        git_context = build_auto_context(self.workspace_root)
        recent_events = await self.store.get_recent_events(session_id=session_id, limit=25)

        active_contexts: list[str] = []
        for e in recent_events:
            ac = e.get("active_context")
            if isinstance(ac, str) and ac and ac not in active_contexts:
                active_contexts.append(ac)

        summary = ""
        if recent_events:
            last = [e.get("tool_name") for e in recent_events[:5] if isinstance(e, dict) and e.get("tool_name")]
            summary = "Recent activity: " + ", ".join(reversed(last))

        snapshot = {
            "reason": reason,
            "workspace_root": self.workspace_root,
            "summary": summary,
            "goals": goals,
            "l1": l1,
            "active_contexts": active_contexts,
            "git_context": git_context,
            "recent_events": list(reversed(recent_events)),
        }

        # Include project state summary in snapshot
        try:
            from memento.project_state import ProjectStateStore
            ps = ProjectStateStore(self.db_path)
            project_summary = await ps.get_summary()
            if project_summary:
                snapshot["project_state"] = project_summary
        except Exception:
            pass

        # Compute session diff from previous session
        session_diff = ""
        try:
            prev_sessions = await self.store.list_sessions(limit=5, status="closed")
            for prev in prev_sessions:
                prev_id = prev.get("id")
                if not prev_id or not prev.get("last_checkpoint_at"):
                    continue
                prev_row = await self.store.get_session(prev_id)
                if not prev_row or not prev_row.checkpoint_data:
                    continue
                prev_data = json.loads(prev_row.checkpoint_data) if prev_row.checkpoint_data else {}
                from memento.handoff_prompt import render_session_diff_prompt
                session_diff = render_session_diff_prompt(
                    current_snapshot=snapshot,
                    previous_snapshot=prev_data,
                )
                break
        except Exception:
            pass

        snapshot["session_diff"] = session_diff
        prompt = render_handoff_prompt(session_id=session_id, snapshot=snapshot)
        if session_diff:
            prompt += "\n" + session_diff
        await self.store.update_checkpoint(session_id=session_id, checkpoint_data=snapshot, handoff_prompt=prompt)
        return snapshot

    async def resume_from(self, *, session_id: str) -> dict[str, Any]:
        await self.provider.initialize()

        row = await self.store.get_session(session_id)
        if row is None:
            raise ValueError(f"Unknown session_id: {session_id}")
        if not row.checkpoint_data:
            await self.create_checkpoint(session_id=session_id, reason="resume")
            row = await self.store.get_session(session_id)
            if row is None or not row.checkpoint_data:
                raise RuntimeError("Failed to create checkpoint for session")

        data = json.loads(row.checkpoint_data) if row.checkpoint_data else {}
        l1_items = data.get("l1") if isinstance(data, dict) else []
        try:
            self.provider.orchestrator.l1.restore(l1_items)
        except Exception:
            pass

        new_id = await self.store.create_child_session(parent_session_id=session_id)
        return {"resumed_from": session_id, "new_session_id": new_id}

