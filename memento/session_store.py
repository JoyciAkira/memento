import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiosqlite

from memento.redaction import redact_secrets


def _now() -> str:
    return datetime.now().isoformat()


def _truncate(text: str, limit: int) -> str:
    s = text if isinstance(text, str) else str(text)
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _safe_json(obj: Any) -> str:
    try:
        raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        raw = json.dumps({"unserializable": True}, ensure_ascii=False, separators=(",", ":"))
    return redact_secrets(raw)


@dataclass
class SessionRow:
    id: str
    workspace_root: str
    parent_session_id: str | None
    status: str
    started_at: str
    ended_at: str | None
    last_event_at: str | None
    last_checkpoint_at: str | None
    checkpoint_data: str | None
    handoff_prompt: str | None
    metadata: str | None


class SessionStore:
    def __init__(self, *, db_path: str, workspace_root: str):
        self.db_path = db_path
        self.workspace_root = os.path.abspath(workspace_root)

    async def ensure_active_session(self) -> str:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id FROM sessions
                WHERE workspace_root = ? AND status = 'active'
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (self.workspace_root,),
            )
            row = await cursor.fetchone()
            if row and row["id"]:
                return str(row["id"])

            session_id = str(uuid.uuid4())
            now = _now()
            await db.execute(
                """
                INSERT INTO sessions
                (id, workspace_root, parent_session_id, status, started_at, ended_at, last_event_at, last_checkpoint_at, checkpoint_data, handoff_prompt, metadata)
                VALUES (?, ?, NULL, 'active', ?, NULL, NULL, NULL, NULL, NULL, ?)
                """,
                (session_id, self.workspace_root, now, "{}"),
            )
            await db.commit()
            return session_id

    async def close_active_sessions(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            now = _now()
            await db.execute(
                """
                UPDATE sessions SET status='closed', ended_at=?
                WHERE workspace_root=? AND status='active'
                """,
                (now, self.workspace_root),
            )
            await db.commit()

    async def create_child_session(self, *, parent_session_id: str) -> str:
        await self.close_active_sessions()
        child_id = str(uuid.uuid4())
        now = _now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO sessions
                (id, workspace_root, parent_session_id, status, started_at, ended_at, last_event_at, last_checkpoint_at, checkpoint_data, handoff_prompt, metadata)
                VALUES (?, ?, ?, 'active', ?, NULL, NULL, NULL, NULL, NULL, ?)
                """,
                (child_id, self.workspace_root, parent_session_id, now, "{}"),
            )
            await db.commit()
        return child_id

    async def append_tool_event(
        self,
        *,
        session_id: str,
        tool_name: str,
        arguments: dict,
        result_text: str,
        is_error: bool,
        active_context: str | None,
    ) -> str:
        event_id = str(uuid.uuid4())
        now = _now()
        args_summary = _truncate(_safe_json(arguments), 2000)
        res_summary = _truncate(redact_secrets(result_text or ""), 2000)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO session_events
                (id, session_id, workspace_root, event_type, tool_name, active_context, arguments_summary, result_summary, is_error, created_at)
                VALUES (?, ?, ?, 'tool_call', ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    session_id,
                    self.workspace_root,
                    tool_name,
                    active_context,
                    args_summary,
                    res_summary,
                    1 if is_error else 0,
                    now,
                ),
            )
            await db.execute(
                "UPDATE sessions SET last_event_at=? WHERE id=?",
                (now, session_id),
            )
            await db.commit()
        return event_id

    async def update_checkpoint(
        self,
        *,
        session_id: str,
        checkpoint_data: dict,
        handoff_prompt: str | None,
    ) -> None:
        now = _now()
        data_str = _safe_json(checkpoint_data)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE sessions
                SET last_checkpoint_at=?, checkpoint_data=?, handoff_prompt=?
                WHERE id=?
                """,
                (now, data_str, handoff_prompt, session_id),
            )
            await db.commit()

    async def get_session(self, session_id: str) -> SessionRow | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, workspace_root, parent_session_id, status, started_at, ended_at,
                       last_event_at, last_checkpoint_at, checkpoint_data, handoff_prompt, metadata
                FROM sessions
                WHERE id=?
                """,
                (session_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return SessionRow(
                id=row["id"],
                workspace_root=row["workspace_root"],
                parent_session_id=row["parent_session_id"],
                status=row["status"],
                started_at=row["started_at"],
                ended_at=row["ended_at"],
                last_event_at=row["last_event_at"],
                last_checkpoint_at=row["last_checkpoint_at"],
                checkpoint_data=row["checkpoint_data"],
                handoff_prompt=row["handoff_prompt"],
                metadata=row["metadata"],
            )

    async def list_sessions(self, *, limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
        safe_limit = min(int(limit), 200)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            where = "WHERE workspace_root=?"
            params: list[Any] = [self.workspace_root]
            if status:
                where += " AND status=?"
                params.append(status)
            cursor = await db.execute(
                f"""
                SELECT id, parent_session_id, status, started_at, ended_at, last_event_at, last_checkpoint_at
                FROM sessions
                {where}
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (*params, safe_limit),
            )
            rows = await cursor.fetchall()

        return [
            {
                "id": r["id"],
                "parent_session_id": r["parent_session_id"],
                "status": r["status"],
                "started_at": r["started_at"],
                "ended_at": r["ended_at"],
                "last_event_at": r["last_event_at"],
                "last_checkpoint_at": r["last_checkpoint_at"],
            }
            for r in rows
        ]

    async def get_recent_events(self, *, session_id: str, limit: int = 25) -> list[dict[str, Any]]:
        safe_limit = min(int(limit), 200)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT tool_name, active_context, arguments_summary, result_summary, is_error, created_at
                FROM session_events
                WHERE session_id=?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, safe_limit),
            )
            rows = await cursor.fetchall()

        return [
            {
                "tool_name": r["tool_name"],
                "active_context": r["active_context"],
                "arguments_summary": r["arguments_summary"],
                "result_summary": r["result_summary"],
                "is_error": bool(r["is_error"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

