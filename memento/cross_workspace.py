"""Cross-workspace memory sharing — share memories between Memento workspaces."""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiosqlite

logger = logging.getLogger(__name__)


class CrossWorkspaceManager:
    """Manages memory sharing between different workspaces."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def share_memory(
        self,
        memory_id: str,
        target_workspace_path: str,
        source_workspace_path: str,
    ) -> Dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, text, metadata FROM memories WHERE id = ?",
                (memory_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return {"error": f"Memory not found: {memory_id}"}

            shared_memory_id = f"shared_{uuid.uuid4().hex[:12]}"
            sync_id = str(uuid.uuid4())
            now = datetime.now().isoformat()

            try:
                await db.execute(
                    """
                    INSERT INTO cross_workspace_sync_log
                    (id, source_workspace, target_workspace, memory_id,
                     shared_memory_id, status, shared_at)
                    VALUES (?, ?, ?, ?, ?, 'shared', ?)
                    """,
                    (
                        sync_id,
                        source_workspace_path,
                        target_workspace_path,
                        memory_id,
                        shared_memory_id,
                        now,
                    ),
                )
                await db.commit()
            except aiosqlite.IntegrityError:
                return {
                    "error": f"Memory {memory_id} already shared from "
                    f"{source_workspace_path} to {target_workspace_path}",
                }

        return {
            "original_id": memory_id,
            "shared_id": shared_memory_id,
            "target_workspace": target_workspace_path,
            "status": "shared",
            "text_preview": row["text"][:100] if row["text"] else "",
            "metadata": row["metadata"],
        }

    async def list_shared_memories(
        self,
        direction: str = "outgoing",
        workspace_path: str = "",
    ) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if direction == "outgoing":
                cursor = await db.execute(
                    """
                    SELECT id, source_workspace, target_workspace,
                           memory_id, shared_memory_id, status, shared_at
                    FROM cross_workspace_sync_log
                    WHERE source_workspace = ?
                    ORDER BY shared_at DESC
                    """,
                    (workspace_path,),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT id, source_workspace, target_workspace,
                           memory_id, shared_memory_id, status, shared_at
                    FROM cross_workspace_sync_log
                    WHERE target_workspace = ?
                    ORDER BY shared_at DESC
                    """,
                    (workspace_path,),
                )
            rows = await cursor.fetchall()

        return [
            {
                "sync_id": r["id"],
                "source_workspace": r["source_workspace"],
                "target_workspace": r["target_workspace"],
                "memory_id": r["memory_id"],
                "shared_memory_id": r["shared_memory_id"],
                "status": r["status"],
                "shared_at": r["shared_at"],
            }
            for r in rows
        ]

    async def get_sync_stats(self) -> Dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM cross_workspace_sync_log WHERE status = 'shared'"
            )
            shared_count = (await cursor.fetchone())[0]

            cursor = await db.execute(
                "SELECT COUNT(*) FROM cross_workspace_sync_log WHERE status = 'imported'"
            )
            imported_count = (await cursor.fetchone())[0]

            cursor = await db.execute(
                "SELECT COUNT(*) FROM cross_workspace_sync_log WHERE status = 'pending'"
            )
            pending_count = (await cursor.fetchone())[0]

            cursor = await db.execute(
                "SELECT COUNT(*) FROM cross_workspace_sync_log"
            )
            total = (await cursor.fetchone())[0]

            cursor = await db.execute(
                "SELECT DISTINCT source_workspace FROM cross_workspace_sync_log"
            )
            sources = [r[0] for r in await cursor.fetchall()]

            cursor = await db.execute(
                "SELECT DISTINCT target_workspace FROM cross_workspace_sync_log"
            )
            targets = [r[0] for r in await cursor.fetchall()]

        return {
            "total": total,
            "shared": shared_count,
            "imported": imported_count,
            "pending": pending_count,
            "source_workspaces": sources,
            "target_workspaces": targets,
        }

    async def import_shared_memory(
        self,
        shared_memory_id: str,
        source_workspace_path: str,
        text: str,
        metadata: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        new_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        meta = metadata or {}
        meta["imported_from"] = source_workspace_path
        meta["original_shared_id"] = shared_memory_id
        meta_str = json.dumps(meta) if meta else "{}"

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO memories (id, user_id, text, created_at, metadata)
                VALUES (?, 'shared', ?, ?, ?)
                """,
                (new_id, text, now, meta_str),
            )
            await db.execute(
                """
                UPDATE cross_workspace_sync_log
                SET status = 'imported', shared_memory_id = ?
                WHERE shared_memory_id = ? AND status = 'shared'
                """,
                (shared_memory_id, shared_memory_id),
            )
            await db.commit()

        return {
            "imported_memory_id": new_id,
            "shared_memory_id": shared_memory_id,
            "source_workspace": source_workspace_path,
            "status": "imported",
        }
