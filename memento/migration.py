from __future__ import annotations

import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class WorkspaceTarget:
    root: str
    name: str
    db_path: str


def _init_db(db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS memories USING fts5(id UNINDEXED, user_id UNINDEXED, text, created_at UNINDEXED, metadata UNINDEXED);"
    )
    conn.commit()
    conn.close()


def _read_all_memories(db_path: str) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT id, user_id, text, created_at, metadata FROM memories ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "user_id": r[1],
            "text": r[2],
            "created_at": r[3],
            "metadata": r[4],
        }
        for r in rows
    ]


def _exists_id(db_path: str, mem_id: str) -> bool:
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT 1 FROM memories WHERE id = ? LIMIT 1", (mem_id,)).fetchone()
    conn.close()
    return row is not None


def _insert_memory(db_path: str, mem: dict[str, Any]) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO memories (id, user_id, text, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
        (
            mem["id"],
            mem.get("user_id", "default"),
            mem["text"],
            mem["created_at"],
            mem.get("metadata") or "{}",
        ),
    )
    conn.commit()
    conn.close()


def _targets_from_workspace_roots(workspace_roots: list[str]) -> list[WorkspaceTarget]:
    targets: list[WorkspaceTarget] = []
    for root in workspace_roots:
        abs_root = os.path.abspath(root)
        name = os.path.basename(abs_root)
        db_path = os.path.join(abs_root, ".memento", "neurograph_memory.db")
        targets.append(WorkspaceTarget(root=abs_root, name=name, db_path=db_path))
    return targets


def classify_memory_to_targets(memory_text: str, targets: list[WorkspaceTarget]) -> list[WorkspaceTarget]:
    text = (memory_text or "").lower()
    matches: list[WorkspaceTarget] = []
    for t in targets:
        if t.name.lower() and t.name.lower() in text:
            matches.append(t)
    return matches


def migrate_memories_copy_only(
    source_db_path: str,
    workspace_roots: list[str],
    report_path: str | None = None,
) -> dict[str, Any]:
    if not os.path.exists(source_db_path):
        raise FileNotFoundError(source_db_path)

    targets = _targets_from_workspace_roots(workspace_roots)
    for t in targets:
        _init_db(t.db_path)

    backup_dir = os.path.join(os.path.dirname(source_db_path), "backup")
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(
        backup_dir,
        f"{os.path.basename(source_db_path)}.{datetime.now().strftime('%Y%m%d%H%M%S')}.bak",
    )
    shutil.copy2(source_db_path, backup_path)

    memories = _read_all_memories(source_db_path)

    per_workspace: dict[str, dict[str, int]] = {t.root: {"copied": 0, "skipped_existing": 0} for t in targets}
    unassigned: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []

    copied_total = 0
    for mem in memories:
        mem_id = str(mem.get("id") or "")
        text = str(mem.get("text") or "")

        matches = classify_memory_to_targets(text, targets)
        if len(matches) == 0:
            unassigned.append({"id": mem_id, "created_at": mem.get("created_at"), "snippet": text[:200]})
            continue
        if len(matches) > 1:
            ambiguous.append(
                {
                    "id": mem_id,
                    "created_at": mem.get("created_at"),
                    "candidates": [m.root for m in matches],
                    "snippet": text[:200],
                }
            )
            continue

        target = matches[0]
        if _exists_id(target.db_path, mem_id):
            per_workspace[target.root]["skipped_existing"] += 1
            continue

        _insert_memory(target.db_path, mem)
        per_workspace[target.root]["copied"] += 1
        copied_total += 1

    payload = {
        "source_db_path": os.path.abspath(source_db_path),
        "backup_path": os.path.abspath(backup_path),
        "workspaces": [{"root": t.root, "name": t.name, "db_path": t.db_path} for t in targets],
        "per_workspace": per_workspace,
        "unassigned": unassigned,
        "ambiguous": ambiguous,
        "summary": {
            "seen_total": len(memories),
            "copied_total": copied_total,
            "unassigned_total": len(unassigned),
            "ambiguous_total": len(ambiguous),
        },
        "generated_at": datetime.now().isoformat(),
    }

    if report_path:
        os.makedirs(os.path.dirname(os.path.abspath(report_path)), exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    return payload
