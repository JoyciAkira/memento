"""Enterprise DB resilience: detect corruption, back it up, and self-heal.

A SQLite database can become corrupted when an external process rewrites a
binary file through a text decode (bytes replaced with U+FFFD), or via disk
faults. Memento must not hard-fail with a cryptic
``database disk image is malformed``. Instead it detects corruption on open,
backs the corrupted file up to a timestamped ``.corrupted-<ts>`` copy, and lets
the next connection recreate a fresh, empty store — while preserving the
original for later recovery with ``sqlite3 "<file>" ".recover"``.
"""
from __future__ import annotations

import os
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger("memento-mcp")

_CORRUPT_MARKER = "corrupted-"


def is_corrupted(db_path: str) -> bool:
    """Return True if ``db_path`` is missing OR fails ``PRAGMA integrity_check``."""
    if not os.path.exists(db_path):
        return False
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute("PRAGMA integrity_check(1)").fetchone()
            return not (row and row[0] == "ok")
        finally:
            conn.close()
    except Exception:
        # Unreadable / malformed header → treat as corrupted.
        return True


def backup_corrupted(db_path: str) -> str | None:
    """Rename a corrupted db (and its ``-wal``/``-shm`` siblings) to a timestamped backup.

    Returns the path of the backed-up main db file, or ``None`` if there was
    nothing to back up. The live file is removed so the next connect recreates
    a fresh store.
    """
    if not os.path.exists(db_path):
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"{db_path}.{_CORRUPT_MARKER}{ts}"
    backed_up: list[str] = []
    for suffix in ("", "-wal", "-shm"):
        src = db_path + suffix
        if os.path.exists(src):
            dst = base + suffix
            try:
                os.replace(src, dst)
                backed_up.append(dst)
            except OSError:
                pass
    return backed_up[0] if backed_up else None


def ensure_healthy_db(db_path: str, *, label: str = "database") -> bool:
    """Ensure ``db_path`` is safe to open.

    If the file is corrupted, backs it up (timestamped) and removes the live
    file so the caller's subsequent connect recreates a fresh, empty store.
    Returns ``True`` when the caller may proceed to connect (file missing,
    healthy, or auto-recovered). A missing file means "recreate".
    """
    if not os.path.exists(db_path):
        return True
    if is_corrupted(db_path):
        backup = backup_corrupted(db_path)
        if backup:
            logger.warning(
                "MEMENTO DB CORRUPTION detected (%s) at %s — backed up to %s and "
                "recreating a fresh store. To attempt data recovery run: "
                "sqlite3 '%s' \".recover\" > recovered.sql",
                label, db_path, backup, backup,
            )
        else:
            logger.warning(
                "MEMENTO DB CORRUPTION detected (%s) at %s — removing unreadable file.",
                label, db_path,
            )
    return True
