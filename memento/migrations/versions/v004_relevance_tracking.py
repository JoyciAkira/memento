def up(conn):
    """Add hit_count and last_accessed_at columns to memory_meta for relevance tracking."""
    for stmt in [
        "ALTER TABLE memory_meta ADD COLUMN hit_count INTEGER DEFAULT 0",
        "ALTER TABLE memory_meta ADD COLUMN last_accessed_at TEXT",
    ]:
        try:
            conn.execute(stmt)
        except Exception:
            pass  # Column may already exist
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_meta_hits ON memory_meta(hit_count)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_meta_last_accessed ON memory_meta(last_accessed_at)"
    )
