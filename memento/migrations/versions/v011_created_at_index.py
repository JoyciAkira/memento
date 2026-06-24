"""Add descending index on memory_meta.created_at for O(1) MAX(created_at) resolution."""
import sqlite3


def up(conn):
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_meta_created_at_desc "
            "ON memory_meta(created_at DESC)"
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass


def down(conn):
    pass
