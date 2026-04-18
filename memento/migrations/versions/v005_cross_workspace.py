def up(conn):
    """Add cross_workspace_sync_log table for tracking shared memories."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cross_workspace_sync_log (
            id TEXT PRIMARY KEY,
            source_workspace TEXT NOT NULL,
            target_workspace TEXT NOT NULL,
            memory_id TEXT NOT NULL,
            shared_memory_id TEXT,
            status TEXT DEFAULT 'pending',
            shared_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(source_workspace, target_workspace, memory_id)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_cross_workspace_sync_source 
        ON cross_workspace_sync_log(source_workspace)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_cross_workspace_sync_status 
        ON cross_workspace_sync_log(status)
    """)
