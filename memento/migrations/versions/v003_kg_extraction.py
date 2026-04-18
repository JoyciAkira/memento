def up(conn):
    """Create kg_extraction_log table for tracking KG auto-extraction."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kg_extraction_log (
            memory_id TEXT PRIMARY KEY,
            memory_text_hash TEXT NOT NULL,
            extracted_at TEXT NOT NULL,
            entities_found INTEGER DEFAULT 0,
            triples_found INTEGER DEFAULT 0,
            extraction_error TEXT,
            llm_model TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_kg_extraction_hash
        ON kg_extraction_log(memory_text_hash)
    """)
