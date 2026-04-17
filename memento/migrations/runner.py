from __future__ import annotations

import logging
import sqlite3
from typing import Callable, List, Tuple

logger = logging.getLogger(__name__)

MigrationFn = Callable[[sqlite3.Connection], None]

MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS _schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
"""


class MigrationRunner:
    """Lightweight SQLite migration runner with version tracking."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._migrations: List[Tuple[int, str, MigrationFn]] = []

    def register(self, version: int, name: str, fn: MigrationFn) -> None:
        self._migrations.append((version, name, fn))
        self._migrations.sort(key=lambda x: x[0])

    def current_version(self) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(MIGRATIONS_DDL)
            row = conn.execute(
                "SELECT MAX(version) FROM _schema_migrations"
            ).fetchone()
            return row[0] or 0
        except Exception:
            return 0
        finally:
            conn.close()

    def run(self) -> int:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute(MIGRATIONS_DDL)
        current = 0
        try:
            row = conn.execute(
                "SELECT MAX(version) FROM _schema_migrations"
            ).fetchone()
            current = row[0] or 0
        except Exception:
            current = 0

        applied = 0
        for version, name, fn in self._migrations:
            if version <= current:
                continue
            try:
                fn(conn)
                conn.execute(
                    "INSERT INTO _schema_migrations (version, name, applied_at) VALUES (?, ?, datetime('now'))",
                    (version, name),
                )
                conn.commit()
                applied += 1
                logger.info(f"Applied migration {version}: {name}")
            except Exception as e:
                conn.rollback()
                raise RuntimeError(f"Migration {version} ({name}) failed: {e}") from e
        conn.close()
        return applied
