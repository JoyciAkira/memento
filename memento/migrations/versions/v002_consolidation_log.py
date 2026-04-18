def up(conn):
    """Create consolidation_log table for tracking consolidation operations."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS consolidation_log (
            id TEXT PRIMARY KEY,
            consolidated_into_id TEXT NOT NULL,
            source_ids TEXT NOT NULL,
            source_count INTEGER NOT NULL,
            fused_text_preview TEXT,
            created_at TEXT NOT NULL
        );
    """)
