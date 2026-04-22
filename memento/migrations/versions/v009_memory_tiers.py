import sqlite3

def up(conn: sqlite3.Connection) -> None:
    # Collect all existing data first
    cursor = conn.execute("SELECT id, user_id, text, created_at, metadata FROM memories")
    rows = cursor.fetchall()

    # Drop the old FTS5 virtual table
    conn.execute("DROP TABLE memories")

    # Create new FTS5 table with memory_tier column
    conn.execute('''
        CREATE VIRTUAL TABLE memories
        USING fts5(id UNINDEXED, user_id UNINDEXED, text, created_at UNINDEXED, metadata UNINDEXED, memory_tier UNINDEXED)
    ''')

    # Rebuild with all data + default tier
    for row in rows:
        id_val, user_id, text, created_at, metadata = row
        conn.execute(
            "INSERT INTO memories(id, user_id, text, created_at, metadata, memory_tier) VALUES (?, ?, ?, ?, ?, 'semantic')",
            (id_val, user_id, text, created_at, metadata)
        )

    conn.commit()
