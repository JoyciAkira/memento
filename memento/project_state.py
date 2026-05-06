from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import aiosqlite


class ProjectStateStore:
    """Manages project-level state: vision, milestones, blockers, tech_debt, decisions."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def _ensure_table(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS project_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            await db.commit()

    async def get(self, key: str) -> Any | None:
        await self._ensure_table()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT value FROM project_state WHERE key = ?", (key,)
            )
            row = await cursor.fetchone()
            if row:
                try:
                    return json.loads(row[0])
                except Exception:
                    return row[0]
        return None

    async def set(self, key: str, value: Any, metadata: dict | None = None) -> None:
        await self._ensure_table()
        now = datetime.now().isoformat()
        value_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        meta_str = json.dumps(metadata or {}, ensure_ascii=False)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO project_state (key, value, updated_at, metadata)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?, metadata = ?""",
                (key, value_str, now, meta_str, value_str, now, meta_str),
            )
            await db.commit()

    async def delete(self, key: str) -> bool:
        await self._ensure_table()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM project_state WHERE key = ?", (key,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def list_all(self) -> dict[str, Any]:
        await self._ensure_table()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT key, value, updated_at, metadata FROM project_state ORDER BY key"
            )
            rows = await cursor.fetchall()
        result = {}
        for r in rows:
            try:
                result[r["key"]] = json.loads(r["value"])
            except Exception:
                result[r["key"]] = r["value"]
        return result

    async def get_summary(self) -> str:
        """Return a human-readable summary of the project state for context injection."""
        state = await self.list_all()
        if not state:
            return ""

        lines = ["[PROJECT STATE]"]
        for key, value in state.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        status = item.get("status", "")
                        title = item.get("title", item.get("name", str(item)))
                        if status:
                            lines.append(f"  {key}: [{status}] {title}")
                        else:
                            lines.append(f"  {key}: {title}")
                    else:
                        lines.append(f"  {key}: {item}")
            elif isinstance(value, dict):
                lines.append(f"  {key}: {json.dumps(value, ensure_ascii=False)[:200]}")
            else:
                lines.append(f"  {key}: {value}")
        return "\n".join(lines)
