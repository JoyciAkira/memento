import uuid
import json
from datetime import datetime
from typing import Any

import aiosqlite


class GoalStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def set_goals(
        self,
        goals: list[str],
        *,
        context: str | None = None,
        mode: str = "replace",
        delete_reason: str = "replaced",
    ) -> dict[str, Any]:
        now = datetime.now().isoformat()
        batch_id = str(uuid.uuid4())

        clean_goals = [g.strip() for g in (goals or []) if isinstance(g, str) and g.strip()]
        if not clean_goals:
            raise ValueError("goals must be a non-empty list of strings")
        if mode not in {"replace", "append"}:
            raise ValueError("mode must be 'replace' or 'append'")

        async with aiosqlite.connect(self.db_path) as db:
            if mode == "replace":
                await db.execute(
                    """
                    UPDATE goals SET is_active = 0, is_deleted = 1, deleted_at = ?,
                        delete_reason = ?, replaced_by_id = ?, updated_at = ?
                    WHERE is_active = 1 AND is_deleted = 0 AND (context IS ? OR context = ?)
                    """,
                    (now, delete_reason, batch_id, now, context, context),
                )

            inserted_ids: list[str] = []
            for g in clean_goals:
                gid = str(uuid.uuid4())
                inserted_ids.append(gid)
                goal_now = datetime.now().isoformat()
                await db.execute(
                    "INSERT INTO goals (id, context, goal, created_at, updated_at, is_active, is_deleted) VALUES (?, ?, ?, ?, ?, 1, 0)",
                    (gid, context, g, goal_now, goal_now),
                )
            await db.commit()

        return {"batch_id": batch_id, "inserted_ids": inserted_ids, "mode": mode, "context": context}

    async def list_goals(
        self, *, context: str | None = None, active_only: bool = True, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        safe_limit = min(int(limit), 200)
        safe_offset = max(int(offset), 0)

        where: list[str] = []
        params: list[Any] = []
        if context is not None:
            where.append("(context IS ? OR context = ?)")
            params.extend([context, context])
        if active_only:
            where.append("is_active = 1 AND is_deleted = 0")

        where_sql = " AND ".join(where)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""
                SELECT id, context, goal, created_at, updated_at, is_active, is_deleted,
                       deleted_at, delete_reason, replaced_by_id
                FROM goals {"WHERE " + where_sql if where_sql else ""}
                ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?
                """,
                (*params, safe_limit, safe_offset),
            )
            rows = await cursor.fetchall()

        return [
            {
                "id": r["id"], "context": r["context"], "goal": r["goal"],
                "created_at": r["created_at"], "updated_at": r["updated_at"],
                "is_active": bool(r["is_active"]), "is_deleted": bool(r["is_deleted"]),
                "deleted_at": r["deleted_at"], "delete_reason": r["delete_reason"],
                "replaced_by_id": r["replaced_by_id"],
            }
            for r in rows
        ]
