def up(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT DEFAULT 'unknown',
            properties TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS triples (
            id TEXT PRIMARY KEY,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object TEXT NOT NULL,
            valid_from TEXT,
            valid_to TEXT,
            confidence REAL DEFAULT 1.0,
            source_closet TEXT,
            source_file TEXT,
            extracted_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subject) REFERENCES entities(id),
            FOREIGN KEY (object) REFERENCES entities(id)
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            centroid TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_triples_subject ON triples(subject)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_triples_object ON triples(object)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_triples_predicate ON triples(predicate)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_triples_valid ON triples(valid_from, valid_to)")
