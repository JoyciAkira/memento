def up(conn):
    """Initial schema: memories, embeddings, metadata, and goals tables."""
    conn.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS memories
        USING fts5(id UNINDEXED, user_id UNINDEXED, text, created_at UNINDEXED, metadata UNINDEXED);
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS memory_embeddings (
            id TEXT PRIMARY KEY,
            embedding TEXT
        );
    ''')
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_meta (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            deleted_at TEXT,
            delete_reason TEXT,
            supersedes_id TEXT,
            replaced_by_id TEXT
        );
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_memory_meta_deleted
        ON memory_meta(is_deleted, deleted_at);
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id TEXT PRIMARY KEY,
            context TEXT,
            goal TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            deleted_at TEXT,
            delete_reason TEXT,
            replaced_by_id TEXT
        );
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_goals_context_active
        ON goals(context, is_deleted, is_active, created_at);
    """)
