"""Percorso dedicato per il KG SQLite e migrazione idempotente da DB memorie legacy."""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Final

logger = logging.getLogger(__name__)

_KG_TABLES: Final[tuple[str, ...]] = ("entities", "triples", "rooms")


def is_file_backed_sqlite(db_path: str) -> bool:
    p = (db_path or "").strip()
    if not p or p == ":memory:":
        return False
    low = p.lower()
    if low.startswith("file:") and ("mode=memory" in low or ":memory:" in low):
        return False
    return True


def resolve_kg_db_path(memory_db_path: str) -> str:
    """DB KG dedicato accanto al file memorie; override con MEMENTO_KG_DB_PATH."""
    explicit = os.environ.get("MEMENTO_KG_DB_PATH", "").strip()
    if explicit:
        return os.path.abspath(explicit)
    if not is_file_backed_sqlite(memory_db_path):
        return memory_db_path
    abs_m = os.path.abspath(memory_db_path)
    parent = os.path.dirname(abs_m)
    if not parent:
        return abs_m
    return os.path.join(parent, "neurograph_kg.sqlite")


def migrate_kg_tables_if_needed(memory_db_path: str, kg_db_path: str) -> None:
    """
    Se il DB memorie contiene tabelle KG popolate e il file KG dedicato è vuoto,
    copia entities/triples/rooms. Idempotente e sicuro se il KG ha già dati.
    """
    if not is_file_backed_sqlite(memory_db_path):
        return
    if os.path.abspath(memory_db_path) == os.path.abspath(kg_db_path):
        return

    main_conn = sqlite3.connect(memory_db_path, timeout=30)
    try:
        if not main_conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='entities'"
        ).fetchone():
            return
        n_src = main_conn.execute("SELECT count(*) FROM entities").fetchone()[0]
        if not n_src:
            return
    finally:
        main_conn.close()

    if os.path.isfile(kg_db_path):
        k = sqlite3.connect(kg_db_path, timeout=30)
        try:
            if k.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='entities'"
            ).fetchone():
                n_k = k.execute("SELECT count(*) FROM entities").fetchone()[0]
                if n_k > 0:
                    return
        finally:
            k.close()

    from memento.knowledge_graph import KnowledgeGraph

    KnowledgeGraph(db_path=kg_db_path)

    main_conn = sqlite3.connect(memory_db_path, timeout=30)
    dest = sqlite3.connect(kg_db_path, timeout=30)
    try:
        for tbl in _KG_TABLES:
            try:
                cols = main_conn.execute(f"PRAGMA table_info({tbl})").fetchall()
            except sqlite3.OperationalError:
                continue
            if not cols:
                continue
            col_names = [c[1] for c in cols]
            if not dest.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (tbl,),
            ).fetchone():
                continue
            rows = main_conn.execute(f"SELECT * FROM {tbl}").fetchall()
            if not rows:
                continue
            ph = ",".join(["?"] * len(col_names))
            qmarks = ",".join(col_names)
            dest.executemany(
                f"INSERT OR REPLACE INTO {tbl} ({qmarks}) VALUES ({ph})",
                [tuple(r) for r in rows],
            )
        dest.commit()
        logger.info(
            "Migrated KG tables from %s to dedicated file %s",
            memory_db_path,
            kg_db_path,
        )
    finally:
        main_conn.close()
        dest.close()
