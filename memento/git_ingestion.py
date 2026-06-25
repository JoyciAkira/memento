"""Structured ingestion of git commits and test failures into Memento memory."""
from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memento.provider import NeuroGraphProvider

logger = logging.getLogger(__name__)


def _run_git(args: list[str], cwd: str) -> str:
    try:
        r = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=15, cwd=cwd
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def get_commit_diff(workspace: str, commit_hash: str = "HEAD") -> dict:
    """Return structured info about a commit: hash, message, files changed, stat."""
    hash_ = _run_git(["rev-parse", "--short", commit_hash], workspace)
    msg = _run_git(["log", "-1", "--pretty=%s", commit_hash], workspace)
    author = _run_git(["log", "-1", "--pretty=%an", commit_hash], workspace)
    date = _run_git(["log", "-1", "--pretty=%ai", commit_hash], workspace)
    stat = _run_git(["diff", "--stat", f"{commit_hash}~1", commit_hash], workspace)
    files = _run_git(
        ["diff", "--name-only", f"{commit_hash}~1", commit_hash], workspace
    ).splitlines()
    return {
        "hash": hash_,
        "message": msg,
        "author": author,
        "date": date,
        "stat": stat,
        "files_changed": files,
    }


async def ingest_commit(
    provider: "NeuroGraphProvider",
    workspace: str,
    commit_hash: str = "HEAD",
    user_id: str = "default",
) -> dict:
    """Ingest a git commit as a structured L3 semantic memory + KG entities."""
    info = get_commit_diff(workspace, commit_hash)
    if not info["hash"]:
        return {"ingested": False, "reason": "not a git repo or no commits"}

    # Build memory text
    files_summary = ", ".join(info["files_changed"][:10])
    if len(info["files_changed"]) > 10:
        files_summary += f" (+{len(info['files_changed']) - 10} more)"
    text = (
        f"[git-commit:{info['hash']}] {info['message']}\n"
        f"Author: {info['author']} | Date: {info['date']}\n"
        f"Files changed: {files_summary}\n"
        f"Stat: {info['stat'][:300] if info['stat'] else 'n/a'}"
    )

    result = await provider.add(
        text=text,
        user_id=user_id,
        metadata={
            "type": "git_commit",
            "memory_tier": "semantic",
            "commit_hash": info["hash"],
            "commit_message": info["message"],
            "files_changed": info["files_changed"],
            "workspace": workspace,
        },
    )

    # Add KG entities for changed files → commit relationship
    try:
        kg = provider.kg.kg
        for f in info["files_changed"][:5]:
            kg.add_causal_triple(
                subject=f,
                predicate="introduced_by",
                obj=f"commit:{info['hash']}",
                source_memory_id=result.get("id"),
            )
    except Exception as e:
        logger.debug(f"KG ingestion for commit failed: {e}")

    return {"ingested": True, "memory_id": result.get("id"), "commit": info["hash"]}


async def ingest_test_failure(
    provider: "NeuroGraphProvider",
    test_name: str,
    error_message: str,
    file_path: str = "",
    workspace: str = "",
    user_id: str = "default",
) -> dict:
    """Ingest a test failure as a structured L2 episodic memory + KG causal triple."""
    ts = datetime.now().isoformat()
    text = (
        f"[test-failure:{test_name}] {ts}\n"
        f"File: {file_path}\n"
        f"Error: {error_message[:500]}"
    )
    result = await provider.add(
        text=text,
        user_id=user_id,
        metadata={
            "type": "test_failure",
            "memory_tier": "episodic",
            "test_name": test_name,
            "file_path": file_path,
            "error": error_message[:200],
            "workspace": workspace,
            "timestamp": ts,
        },
    )

    # KG: test_name caused_by file_path
    try:
        if file_path:
            kg = provider.kg.kg
            kg.add_causal_triple(
                subject=test_name,
                predicate="caused_by",
                obj=file_path,
                source_memory_id=result.get("id"),
            )
    except Exception as e:
        logger.debug(f"KG ingestion for test failure failed: {e}")

    return {"ingested": True, "memory_id": result.get("id"), "test": test_name}
