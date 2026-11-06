"""Ground memories in code symbols, keyed by the ledger's file hashes.

A link is current only while ``indexed_files.sha256`` still matches the hash
stored with the link. Editing a file therefore ages out its links without any
extra bookkeeping, and a stale link is never counted as retrieval evidence.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

CACHE_FILENAME = "code_index.sqlite"
MAX_LINKS_PER_MEMORY = 20
MAX_KG_LINKS_PER_MEMORY = 5
GENERIC_DEFINITION_THRESHOLD = 2
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
LOCATOR_RE = re.compile(r"([A-Za-z0-9_./-]+\.(?:pyi?|jsx?|mjs|cjs|tsx?)):(\d+)")

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS memory_links ("
    "memory_id TEXT NOT NULL, "
    "path TEXT NOT NULL, "
    "symbol TEXT NOT NULL DEFAULT '', "
    "kind TEXT NOT NULL, "
    "sha256 TEXT NOT NULL, "
    "created_at TEXT NOT NULL, "
    "confidence REAL NOT NULL DEFAULT 1.0, "
    "PRIMARY KEY (memory_id, path, symbol, kind))",
    "CREATE INDEX IF NOT EXISTS idx_memory_links_symbol ON memory_links(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_memory_links_path ON memory_links(path)",
)


class MemoryGrounder:
    """Map memory text to code symbols and persist hash-stamped links."""

    def __init__(self, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.memento_dir = os.path.join(self.project_root, ".memento")
        self.cache_path = os.path.join(self.memento_dir, CACHE_FILENAME)

    # -- storage ---------------------------------------------------------

    def _connect(self, write: bool = False) -> Optional[sqlite3.Connection]:
        if not os.path.exists(self.cache_path):
            return None
        conn = sqlite3.connect(self.cache_path, timeout=10)
        conn.row_factory = sqlite3.Row
        if write:
            for statement in _SCHEMA:
                conn.execute(statement)
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(memory_links)")
            }
            if "confidence" not in columns:
                conn.execute(
                    "ALTER TABLE memory_links ADD COLUMN "
                    "confidence REAL NOT NULL DEFAULT 1.0"
                )
        return conn

    @staticmethod
    def _load_index(
        conn: sqlite3.Connection,
    ) -> Tuple[
        Dict[str, Dict[str, Any]],
        Dict[str, List[Dict[str, Any]]],
        Dict[str, List[Dict[str, Any]]],
    ]:
        files = {
            row["path"]: {"sha256": row["sha256"]}
            for row in conn.execute("SELECT path, sha256 FROM indexed_files")
        }
        by_name: Dict[str, List[Dict[str, Any]]] = {}
        by_path: Dict[str, List[Dict[str, Any]]] = {}
        for row in conn.execute(
            "SELECT path, name, kind, start_line, end_line FROM symbols"
        ):
            entry = dict(row)
            by_name.setdefault(entry["name"], []).append(entry)
            by_path.setdefault(entry["path"], []).append(entry)
        for entries in by_path.values():
            entries.sort(key=lambda item: item["start_line"])
        return files, by_name, by_path

    # -- matching --------------------------------------------------------

    @staticmethod
    def _links_for_text(
        text: str,
        files: Dict[str, Dict[str, Any]],
        by_name: Dict[str, List[Dict[str, Any]]],
        by_path: Dict[str, List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        links: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

        lowered = text.lower()
        mentioned_paths = {
            path
            for path in files
            if path.lower() in lowered or os.path.basename(path).lower() in lowered
        }
        mentioned_dirs = {os.path.dirname(path) for path in mentioned_paths}

        def add(path: str, symbol: str, kind: str, confidence: float) -> None:
            if path not in files or len(links) >= MAX_LINKS_PER_MEMORY:
                return
            key = (path, symbol, kind)
            confidence = round(min(1.0, max(0.0, confidence)), 3)
            existing = links.get(key)
            if existing is not None:
                if confidence > existing["confidence"]:
                    existing["confidence"] = confidence
                return
            links[key] = {
                "path": path,
                "symbol": symbol,
                "kind": kind,
                "sha256": files[path]["sha256"],
                "confidence": confidence,
            }

        for match in LOCATOR_RE.finditer(text):
            path = match.group(1).lstrip("./").replace(os.sep, "/")
            line = int(match.group(2))
            matched = False
            for entry in by_path.get(path, []):
                if entry["start_line"] <= line <= entry["end_line"]:
                    add(path, entry["name"], "locator", 1.0)
                    matched = True
                    break
            if not matched:
                add(path, "", "file", 0.7)

        for token in set(TOKEN_RE.findall(text)):
            entries = by_name.get(token, [])
            if not entries:
                continue
            paths = {entry["path"] for entry in entries}
            if len(paths) > GENERIC_DEFINITION_THRESHOLD:
                entries = [
                    entry
                    for entry in entries
                    if entry["path"] in mentioned_paths
                    or (
                        os.path.dirname(entry["path"])
                        and os.path.dirname(entry["path"]) in mentioned_dirs
                    )
                ]
                if not entries:
                    continue
                base = 0.62
            elif len(paths) == 1:
                base = 0.9
            else:
                base = 0.78
            for entry in entries[:3]:
                confidence = base
                if entry["path"] in mentioned_paths:
                    confidence += 0.1
                if entry["kind"] in ("class", "interface", "type", "enum"):
                    confidence += 0.03
                if len(token) >= 8:
                    confidence += 0.02
                add(entry["path"], entry["name"], entry["kind"], confidence)

        for path in files:
            basename = os.path.basename(path)
            if path.lower() in lowered:
                add(path, "", "file", 0.62)
            elif basename.lower() in lowered:
                add(path, "", "file", 0.52)

        return sorted(
            links.values(),
            key=lambda link: (
                -link["confidence"],
                0 if link["kind"] == "locator" else 1 if link["symbol"] else 2,
            ),
        )

    # -- writing ---------------------------------------------------------

    def link_memory(
        self,
        memory_id: str,
        text: str,
        kg: Any = None,
    ) -> int:
        conn = self._connect(write=True)
        if conn is None:
            return 0
        links: List[Dict[str, Any]] = []
        try:
            files, by_name, by_path = self._load_index(conn)
            if not files:
                return 0
            links = self._links_for_text(text, files, by_name, by_path)
            now = datetime.now().isoformat()
            with conn:
                conn.execute(
                    "DELETE FROM memory_links WHERE memory_id = ?", (memory_id,)
                )
                for link in links:
                    conn.execute(
                        "INSERT OR REPLACE INTO memory_links "
                        "(memory_id, path, symbol, kind, sha256, created_at, confidence) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            memory_id,
                            link["path"],
                            link["symbol"],
                            link["kind"],
                            link["sha256"],
                            now,
                            link["confidence"],
                        ),
                    )
        finally:
            conn.close()
        if kg is not None and links:
            self._add_kg_triples(kg, memory_id, text, links)
        return len(links)

    def link_all(
        self,
        memories: Iterable[Sequence[Any]],
        rebuild: bool = False,
        kg: Any = None,
        kg_limit: int = 1000,
    ) -> Dict[str, Any]:
        started = time.monotonic()
        rows = [(str(row[0]), str(row[1] or "")) for row in memories]
        report: Dict[str, Any] = {
            "memories_scanned": len(rows),
            "memories_linked": 0,
            "links": 0,
            "kg_triples": 0,
            "rebuilt": rebuild,
            "index_available": False,
            "cache_path": self.cache_path,
            "duration_seconds": 0.0,
        }
        conn = self._connect(write=True)
        if conn is None:
            report["error"] = "code index not found; run 'memento sync' first"
            report["duration_seconds"] = round(time.monotonic() - started, 3)
            return report
        try:
            files, by_name, by_path = self._load_index(conn)
            if not files:
                report["error"] = "code index is empty; run 'memento index' first"
                report["duration_seconds"] = round(time.monotonic() - started, 3)
                return report
            report["index_available"] = True
            if rebuild:
                conn.execute("DELETE FROM memory_links")
                conn.commit()

            now = datetime.now().isoformat()
            kg_candidates: List[Tuple[str, str, List[Dict[str, Any]]]] = []
            for index, (memory_id, text) in enumerate(rows):
                links = self._links_for_text(text, files, by_name, by_path)
                conn.execute(
                    "DELETE FROM memory_links WHERE memory_id = ?", (memory_id,)
                )
                if links:
                    conn.executemany(
                        "INSERT OR REPLACE INTO memory_links "
                        "(memory_id, path, symbol, kind, sha256, created_at, confidence) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [
                            (
                                memory_id,
                                link["path"],
                                link["symbol"],
                                link["kind"],
                                link["sha256"],
                                now,
                                link["confidence"],
                            )
                            for link in links
                        ],
                    )
                    report["memories_linked"] += 1
                    report["links"] += len(links)
                    if kg is not None and len(kg_candidates) < kg_limit:
                        kg_candidates.append((memory_id, text, links))
                if index % 500 == 499:
                    conn.commit()
            conn.commit()
        finally:
            conn.close()

        for memory_id, text, links in kg_candidates:
            report["kg_triples"] += self._add_kg_triples(kg, memory_id, text, links)

        report["duration_seconds"] = round(time.monotonic() - started, 3)
        return report

    @staticmethod
    def _add_kg_triples(
        kg: Any,
        memory_id: str,
        text: str,
        links: List[Dict[str, Any]],
    ) -> int:
        added = 0
        for link in links[:MAX_KG_LINKS_PER_MEMORY]:
            name = (
                f"{link['path']}::{link['symbol']}" if link["symbol"] else link["path"]
            )
            try:
                kg.add_entity(
                    name,
                    "code_symbol",
                    {
                        "path": link["path"],
                        "symbol": link["symbol"],
                        "kind": link["kind"],
                        "sha256": link["sha256"],
                    },
                )
                kg.add_triple(
                    subject=text,
                    predicate="grounded_in",
                    obj=name,
                    confidence=link["confidence"],
                    source_closet=memory_id,
                    source_file=link["path"],
                )
                added += 1
            except Exception:
                continue
        return added

    # -- reading ---------------------------------------------------------

    def links_for_memories(
        self, memory_ids: Sequence[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        ids = [str(memory_id) for memory_id in memory_ids]
        if not ids:
            return {}
        conn = self._connect()
        if conn is None:
            return {}
        result: Dict[str, List[Dict[str, Any]]] = {memory_id: [] for memory_id in ids}
        try:
            placeholders = ",".join(["?"] * len(ids))
            rows = conn.execute(
                "SELECT ml.memory_id, ml.path, ml.symbol, ml.kind, ml.sha256, "
                "ml.confidence, i.sha256 AS current_sha "
                "FROM memory_links ml "
                "LEFT JOIN indexed_files i ON i.path = ml.path "
                f"WHERE ml.memory_id IN ({placeholders})",
                tuple(ids),
            ).fetchall()
        except sqlite3.OperationalError:
            return result
        finally:
            conn.close()

        for row in rows:
            current = row["current_sha"] == row["sha256"]
            result[row["memory_id"]].append(
                {
                    "path": row["path"],
                    "symbol": row["symbol"],
                    "kind": row["kind"],
                    "sha256": row["sha256"],
                    "confidence": row["confidence"],
                    "current": current,
                    "stale": not current,
                }
            )
        return result

    def memory_ids_for_query(self, query: str, limit: int = 40) -> List[str]:
        query = (query or "").strip()
        if not query:
            return []
        tokens = sorted(set(TOKEN_RE.findall(query)))
        conn = self._connect()
        if conn is None:
            return []
        try:
            paths = [
                row["path"] for row in conn.execute("SELECT path FROM indexed_files")
            ]
            lowered = query.lower()
            matched_paths = [
                path
                for path in paths
                if path.lower() in lowered or os.path.basename(path).lower() in lowered
            ]
            if not tokens and not matched_paths:
                return []

            clauses: List[str] = []
            params: List[Any] = []
            if tokens:
                placeholders = ",".join(["?"] * len(tokens))
                clauses.append(f"ml.symbol IN ({placeholders})")
                params.extend(tokens)
            if matched_paths:
                placeholders = ",".join(["?"] * len(matched_paths))
                clauses.append(f"ml.path IN ({placeholders})")
                params.extend(matched_paths)

            rows = conn.execute(
                "SELECT ml.memory_id, SUM(ml.confidence) AS score "
                "FROM memory_links ml "
                "JOIN indexed_files i ON i.path = ml.path "
                "AND i.sha256 = ml.sha256 "
                f"WHERE {' OR '.join(clauses)} "
                "GROUP BY ml.memory_id "
                "ORDER BY score DESC, ml.memory_id LIMIT ?",
                (*params, max(1, int(limit))),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()
        return [row["memory_id"] for row in rows]
