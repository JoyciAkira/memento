import os
import sqlite3

import pytest

from memento.kg_storage import (
    is_file_backed_sqlite,
    migrate_kg_tables_if_needed,
    resolve_kg_db_path,
)
from memento.knowledge_graph import KnowledgeGraph


def test_resolve_kg_db_path_sibling(tmp_path):
    mem = tmp_path / "neurograph_memory.db"
    mem.parent.mkdir(parents=True, exist_ok=True)
    mem.touch()
    out = resolve_kg_db_path(str(mem))
    assert out.endswith("neurograph_kg.sqlite")
    assert os.path.dirname(out) == str(tmp_path)


def test_resolve_kg_db_path_memory_alias():
    assert resolve_kg_db_path(":memory:") == ":memory:"
    assert not is_file_backed_sqlite(":memory:")


def test_migrate_kg_colocated_to_sibling(tmp_path):
    main = tmp_path / "neurograph_memory.db"
    kg_sibling = tmp_path / "neurograph_kg.sqlite"
    if kg_sibling.exists():
        kg_sibling.unlink()

    g = KnowledgeGraph(db_path=str(main))
    g.add_triple("Alpha", "relates_to", "Beta", source_file="test")
    g.close()

    migrate_kg_tables_if_needed(str(main), str(kg_sibling))

    assert kg_sibling.is_file()
    conn = sqlite3.connect(str(kg_sibling))
    try:
        n = conn.execute("SELECT count(*) FROM entities").fetchone()[0]
        assert n >= 2
        t = conn.execute("SELECT count(*) FROM triples").fetchone()[0]
        assert t >= 1
    finally:
        conn.close()


def test_migrate_idempotent(tmp_path):
    main = tmp_path / "m2.db"
    kg = tmp_path / "neurograph_kg.sqlite"
    if kg.exists():
        kg.unlink()
    g = KnowledgeGraph(db_path=str(main))
    g.add_triple("X", "knows", "Y", source_file="t")
    g.close()
    migrate_kg_tables_if_needed(str(main), str(kg))
    conn = sqlite3.connect(str(kg))
    n1 = conn.execute("SELECT count(*) FROM entities").fetchone()[0]
    conn.close()
    migrate_kg_tables_if_needed(str(main), str(kg))
    conn = sqlite3.connect(str(kg))
    n2 = conn.execute("SELECT count(*) FROM entities").fetchone()[0]
    conn.close()
    assert n1 == n2


@pytest.mark.asyncio
async def test_provider_uses_dedicated_kg_file(tmp_path, monkeypatch):
    monkeypatch.delenv("MEMENTO_KG_DB_PATH", raising=False)
    from memento.provider import NeuroGraphProvider

    mem = tmp_path / "neurograph_memory.db"
    p = NeuroGraphProvider(db_path=str(mem))
    await p.initialize()
    assert os.path.abspath(p.kg_db_path) != os.path.abspath(p.db_path)
    assert p.kg.kg.db_path == p.kg_db_path
