"""Backfill memory_tier for rows written before tier persistence.

Rows created by ``provider.add()`` before the tier fix left the FTS column NULL,
so temporal decay always used the semantic lambda. Recover the tier from
``metadata.memory_tier`` when present, then from known ``metadata.type`` values;
anything unknown falls back to ``semantic`` (the slowest-decaying tier), so an
incorrect guess cannot cause premature pruning.
"""

import sqlite3

VALID_TIERS = ("working", "episodic", "semantic")

# Types whose tier is fixed by the code that writes them.
TYPE_TIERS = {
    "git_commit": "semantic",
    "test_failure": "episodic",
    "autonomous_health_report": "episodic",
}

_TYPE_CASE = "\n".join(
    "        WHEN json_valid(metadata) "
    f"AND LOWER(TRIM(COALESCE(json_extract(metadata, '$.type'), ''))) = '{type_name}' "
    f"THEN '{tier}'"
    for type_name, tier in TYPE_TIERS.items()
)

_BACKFILL_SQL = f"""
UPDATE memories
SET memory_tier = CASE
        WHEN json_valid(metadata)
         AND LOWER(TRIM(COALESCE(json_extract(metadata, '$.memory_tier'), '')))
             IN ('working', 'episodic', 'semantic')
        THEN LOWER(TRIM(json_extract(metadata, '$.memory_tier')))
{_TYPE_CASE}
        ELSE 'semantic'
    END
WHERE memory_tier IS NULL OR TRIM(memory_tier) = ''
"""


def up(conn: sqlite3.Connection) -> None:
    conn.execute(_BACKFILL_SQL)
    conn.commit()


def down(conn: sqlite3.Connection) -> None:
    pass
