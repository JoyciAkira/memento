"""Add missing performance indexes for search, consolidation, and extraction queries."""


_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_memory_embeddings_id ON memory_embeddings(id)",
    "CREATE INDEX IF NOT EXISTS idx_memory_meta_deleted ON memory_meta(is_deleted, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_kg_extraction_log_memory_id ON kg_extraction_log(memory_id)",
    "CREATE INDEX IF NOT EXISTS idx_consolidation_log_created_at ON consolidation_log(created_at)",
]


def up(conn):
    for stmt in _INDEXES:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass
    conn.commit()

import sqlite3


def down(conn):
    pass
