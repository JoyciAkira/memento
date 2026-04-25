def up(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            workspace_root TEXT NOT NULL,
            parent_session_id TEXT,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            last_event_at TEXT,
            last_checkpoint_at TEXT,
            checkpoint_data TEXT,
            handoff_prompt TEXT,
            metadata TEXT
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_events (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            workspace_root TEXT NOT NULL,
            event_type TEXT NOT NULL,
            tool_name TEXT,
            active_context TEXT,
            arguments_summary TEXT,
            result_summary TEXT,
            is_error INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_workspace_started ON sessions(workspace_root, started_at DESC);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status, started_at DESC);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_events_session_created ON session_events(session_id, created_at DESC);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_events_workspace_created ON session_events(workspace_root, created_at DESC);"
    )

