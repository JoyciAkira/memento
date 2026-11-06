"""Incremental tree-sitter code index driven by the shadow ledger.

The ledger knows the current sha256 of every workspace file. This index keeps a
separate SQLite database (``.memento/code_index.sqlite``) with the symbols and
imports extracted from supported source files, and only re-parses files whose
hash differs from the last indexed hash. Deleting the index is safe: the next
``memento index`` rebuilds it from the ledger without rescanning git history.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from memento.ledger import FileLedger

CACHE_FILENAME = "code_index.sqlite"
MAX_INDEX_BYTES = 2 * 1024 * 1024

LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}

SYMBOL_TYPES = {
    "python": {
        "function_definition": "function",
        "class_definition": "class",
    },
    "javascript": {
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
    },
    "typescript": {
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
        "enum_declaration": "enum",
    },
    "tsx": {
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
        "enum_declaration": "enum",
    },
}

IMPORT_TYPES = {
    "python": {"import_statement", "import_from_statement"},
    "javascript": {"import_statement"},
    "typescript": {"import_statement"},
    "tsx": {"import_statement"},
}


def _language_for(path: str) -> Optional[str]:
    return LANGUAGE_BY_EXTENSION.get(os.path.splitext(path)[1].lower())


def _build_parsers() -> Dict[str, Any]:
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_javascript
        import tree_sitter_python
        import tree_sitter_typescript
    except ImportError:
        return {}

    specs = {
        "python": tree_sitter_python.language,
        "javascript": tree_sitter_javascript.language,
        "typescript": tree_sitter_typescript.language_typescript,
        "tsx": tree_sitter_typescript.language_tsx,
    }
    parsers: Dict[str, Any] = {}
    for name, getter in specs.items():
        try:
            parser = Parser()
            language = Language(getter())
            try:
                parser.language = language
            except Exception:
                parser.set_language(language)
            parsers[name] = parser
        except Exception:
            continue
    return parsers


class CodeIndex:
    """SQLite symbol index that only re-parses files changed in the ledger."""

    def __init__(self, workspace_root: str, ledger: Optional[FileLedger] = None):
        self.workspace_root = os.path.abspath(workspace_root)
        self.ledger = ledger or FileLedger(workspace_root)
        self.project_root = self.ledger.project_root
        self.memento_dir = os.path.join(self.project_root, ".memento")
        self.cache_path = os.path.join(self.memento_dir, CACHE_FILENAME)
        self.parsers = _build_parsers()

    # -- storage ---------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(self.memento_dir, exist_ok=True)
        conn = sqlite3.connect(self.cache_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS indexed_files ("
            "path TEXT PRIMARY KEY, "
            "sha256 TEXT NOT NULL, "
            "language TEXT NOT NULL, "
            "symbols INTEGER NOT NULL DEFAULT 0, "
            "indexed_at TEXT NOT NULL, "
            "error TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS symbols ("
            "path TEXT NOT NULL, "
            "name TEXT NOT NULL, "
            "kind TEXT NOT NULL, "
            "start_line INTEGER NOT NULL, "
            "end_line INTEGER NOT NULL, "
            "signature_hash TEXT NOT NULL, "
            "PRIMARY KEY (path, name, kind, start_line))"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS imports ("
            "path TEXT NOT NULL, "
            "module TEXT NOT NULL, "
            "line INTEGER NOT NULL, "
            "PRIMARY KEY (path, module, line))"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS symbol_references ("
            "path TEXT NOT NULL, "
            "src_symbol TEXT, "
            "kind TEXT NOT NULL, "
            "target TEXT NOT NULL, "
            "line INTEGER NOT NULL, "
            "PRIMARY KEY (path, src_symbol, kind, target, line))"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS memory_links ("
            "memory_id TEXT NOT NULL, "
            "path TEXT NOT NULL, "
            "symbol TEXT NOT NULL DEFAULT '', "
            "kind TEXT NOT NULL, "
            "sha256 TEXT NOT NULL, "
            "created_at TEXT NOT NULL, "
            "confidence REAL NOT NULL DEFAULT 1.0, "
            "PRIMARY KEY (memory_id, path, symbol, kind))"
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_links)")}
        if "confidence" not in columns:
            conn.execute(
                "ALTER TABLE memory_links ADD COLUMN "
                "confidence REAL NOT NULL DEFAULT 1.0"
            )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_symbol_refs_target "
            "ON symbol_references(target)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_symbol_refs_src "
            "ON symbol_references(src_symbol)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_links_symbol "
            "ON memory_links(symbol)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_links_path ON memory_links(path)"
        )
        return conn

    def _indexed_hashes(self) -> Dict[str, str]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT path, sha256 FROM indexed_files").fetchall()
        finally:
            conn.close()
        return {row["path"]: row["sha256"] for row in rows}

    @staticmethod
    def _store_file(
        conn: sqlite3.Connection,
        path: str,
        sha256: str,
        language: str,
        symbols: List[Dict[str, Any]],
        imports: List[Dict[str, Any]],
        references: List[Dict[str, Any]],
        error: Optional[str] = None,
    ) -> None:
        conn.execute("DELETE FROM symbols WHERE path = ?", (path,))
        conn.execute("DELETE FROM imports WHERE path = ?", (path,))
        conn.execute("DELETE FROM symbol_references WHERE path = ?", (path,))
        conn.execute(
            "INSERT INTO indexed_files "
            "(path, sha256, language, symbols, indexed_at, error) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET "
            "sha256=excluded.sha256, language=excluded.language, "
            "symbols=excluded.symbols, indexed_at=excluded.indexed_at, "
            "error=excluded.error",
            (
                path,
                sha256,
                language,
                len(symbols),
                datetime.now().isoformat(),
                error,
            ),
        )
        for symbol in symbols:
            conn.execute(
                "INSERT OR REPLACE INTO symbols "
                "(path, name, kind, start_line, end_line, signature_hash) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    path,
                    symbol["name"],
                    symbol["kind"],
                    symbol["start_line"],
                    symbol["end_line"],
                    symbol["signature_hash"],
                ),
            )
        for imported in imports:
            conn.execute(
                "INSERT OR REPLACE INTO imports (path, module, line) VALUES (?, ?, ?)",
                (path, imported["module"], imported["line"]),
            )
        for reference in references:
            conn.execute(
                "INSERT OR REPLACE INTO symbol_references "
                "(path, src_symbol, kind, target, line) VALUES (?, ?, ?, ?, ?)",
                (
                    path,
                    reference.get("src_symbol"),
                    reference["kind"],
                    reference["target"],
                    reference["line"],
                ),
            )

    # -- parsing ---------------------------------------------------------

    @staticmethod
    def _text(source: bytes, node: Any) -> str:
        return (
            source[node.start_byte : node.end_byte].decode("utf-8", "replace").strip()
        )

    def _enclosing_symbol(
        self, node: Any, symbol_types: Dict[str, str], source: bytes
    ) -> Optional[str]:
        parent = node.parent
        while parent is not None:
            if parent.type in symbol_types:
                name_node = parent.child_by_field_name("name")
                if name_node is not None:
                    return self._text(source, name_node)
            parent = parent.parent
        return None

    def _call_target(self, source: bytes, node: Any) -> str:
        function = node.child_by_field_name("function")
        if function is None:
            return ""
        if function.type == "attribute":
            attribute = function.child_by_field_name("attribute")
            return self._text(source, attribute) if attribute is not None else ""
        if function.type == "member_expression":
            prop = function.child_by_field_name("property")
            return self._text(source, prop) if prop is not None else ""
        return self._text(source, function)

    def _import_targets(self, language: str, source: bytes, node: Any) -> List[str]:
        targets: List[str] = []
        if language == "python":
            if node.type == "import_from_statement":
                module = node.child_by_field_name("module_name")
                if module is not None:
                    targets.append(self._text(source, module))
                else:
                    text = self._text(source, node)
                    if text.startswith("from "):
                        targets.append(text[5:].split(" import ", 1)[0].strip())
            else:
                for child in node.children:
                    if child.type == "dotted_name":
                        targets.append(self._text(source, child))
                    elif child.type == "aliased_import":
                        name = child.child_by_field_name("name")
                        targets.append(
                            self._text(source, name)
                            if name is not None
                            else self._text(source, child)
                        )
        else:
            source_node = node.child_by_field_name("source")
            if source_node is not None:
                targets.append(self._text(source, source_node).strip("'\"`"))
        return [target[:200] for target in targets if target]

    def _inheritance_targets(
        self, language: str, source: bytes, node: Any
    ) -> List[str]:
        targets: List[str] = []
        if language == "python":
            superclasses = node.child_by_field_name("superclasses")
            if superclasses is not None:
                for child in superclasses.named_children:
                    if child.type in ("identifier", "attribute", "subscript"):
                        targets.append(self._text(source, child))
        else:
            clause = next(
                (c for c in node.named_children if c.type == "extends_clause"), None
            )
            if clause is not None:
                for child in clause.named_children:
                    if child.type in (
                        "identifier",
                        "member_expression",
                        "type_identifier",
                    ):
                        targets.append(self._text(source, child))
        return [target[:200] for target in targets if target]

    def _extract(
        self, language: str, source: bytes
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        parser = self.parsers.get(language)
        if parser is None:
            return [], [], []

        tree = parser.parse(source)
        symbols: List[Dict[str, Any]] = []
        imports: List[Dict[str, Any]] = []
        references: List[Dict[str, Any]] = []
        seen_refs: set[Tuple[Optional[str], str, str, int]] = set()
        symbol_types = SYMBOL_TYPES.get(language, {})
        import_types = IMPORT_TYPES.get(language, set())

        def add_reference(target: str, kind: str, node: Any) -> None:
            target = target.strip()
            if not target:
                return
            source_symbol = self._enclosing_symbol(node, symbol_types, source)
            line = node.start_point[0] + 1
            key = (source_symbol, kind, target[:200], line)
            if key in seen_refs:
                return
            seen_refs.add(key)
            references.append(
                {
                    "src_symbol": source_symbol,
                    "kind": kind,
                    "target": target[:200],
                    "line": line,
                }
            )

        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type in symbol_types:
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    name = self._text(source, name_node)
                    kind = symbol_types[node.type]
                    if (
                        language == "python"
                        and node.type == "function_definition"
                        and node.parent is not None
                        and node.parent.type == "class_definition"
                    ):
                        kind = "method"
                    first_line = source[node.start_byte : node.end_byte].split(
                        b"\n", 1
                    )[0]
                    symbols.append(
                        {
                            "name": name,
                            "kind": kind,
                            "start_line": node.start_point[0] + 1,
                            "end_line": node.end_point[0] + 1,
                            "signature_hash": hashlib.sha256(first_line).hexdigest(),
                        }
                    )
            if node.type in ("call", "call_expression"):
                add_reference(self._call_target(source, node), "call", node)
            if language == "python" and node.type == "class_definition":
                for target in self._inheritance_targets(language, source, node):
                    add_reference(target, "inherits", node)
            elif language != "python" and node.type == "class_heritage":
                for target in self._inheritance_targets(language, source, node):
                    add_reference(target, "inherits", node)
            if node.type in import_types:
                text = self._text(source, node)
                if text:
                    imports.append(
                        {"module": text[:500], "line": node.start_point[0] + 1}
                    )
                for target in self._import_targets(language, source, node):
                    add_reference(target, "import", node)
            stack.extend(reversed(node.children))
        return symbols, imports, references

    # -- update ----------------------------------------------------------

    def update(self, rebuild: bool = False) -> Dict[str, Any]:
        """Index only files whose sha256 differs from the stored one."""
        state = self.ledger.cache_state()
        if not state:
            self.ledger.sync(scan=False)
            state = self.ledger.cache_state()

        if not self.parsers:
            return {
                "scanned": len(state),
                "indexed": 0,
                "removed": 0,
                "unchanged": 0,
                "skipped": len(state),
                "symbols": 0,
                "references": 0,
                "languages": {},
                "parser": "unavailable",
                "cache_path": self.cache_path,
                "rebuild": rebuild,
                "error": "tree-sitter not installed; index left untouched",
            }

        conn = self._connect()
        try:
            if rebuild:
                conn.execute("DELETE FROM symbols")
                conn.execute("DELETE FROM imports")
                conn.execute("DELETE FROM symbol_references")
                conn.execute("DELETE FROM memory_links")
                conn.execute("DELETE FROM indexed_files")
                conn.commit()

            indexed = self._indexed_hashes()
            removed = sorted(set(indexed) - set(state))
            to_index = sorted(
                path
                for path, info in state.items()
                if indexed.get(path) != info["sha256"]
            )

            for path in removed:
                conn.execute("DELETE FROM symbols WHERE path = ?", (path,))
                conn.execute("DELETE FROM imports WHERE path = ?", (path,))
                conn.execute("DELETE FROM symbol_references WHERE path = ?", (path,))
                conn.execute("DELETE FROM memory_links WHERE path = ?", (path,))
                conn.execute("DELETE FROM indexed_files WHERE path = ?", (path,))

            indexed_count = 0
            skipped = 0
            symbols_total = 0
            references_total = 0
            languages: Dict[str, int] = {}
            for path in to_index:
                language = _language_for(path)
                if language is None:
                    skipped += 1
                    continue
                abs_path = os.path.join(self.project_root, path)
                sha256 = state[path]["sha256"]
                try:
                    if os.path.getsize(abs_path) > MAX_INDEX_BYTES:
                        self._store_file(
                            conn, path, sha256, language, [], [], [], error="too_large"
                        )
                        skipped += 1
                        continue
                    with open(abs_path, "rb") as handle:
                        source = handle.read()
                    symbols, imports, references = self._extract(language, source)
                except OSError as exc:
                    self._store_file(
                        conn,
                        path,
                        sha256,
                        language,
                        [],
                        [],
                        [],
                        error=str(exc)[:200],
                    )
                    skipped += 1
                    continue

                self._store_file(
                    conn, path, sha256, language, symbols, imports, references
                )
                indexed_count += 1
                symbols_total += len(symbols)
                references_total += len(references)
                languages[language] = languages.get(language, 0) + 1

            conn.commit()
            unchanged = sum(
                1
                for path, info in state.items()
                if path in indexed and indexed[path] == info["sha256"]
            )
        finally:
            conn.close()

        return {
            "scanned": len(state),
            "indexed": indexed_count,
            "removed": len(removed),
            "unchanged": unchanged,
            "skipped": skipped,
            "symbols": symbols_total,
            "references": references_total,
            "languages": languages,
            "parser": "tree-sitter" if self.parsers else "unavailable",
            "cache_path": self.cache_path,
            "rebuild": rebuild,
        }

    # -- graph -----------------------------------------------------------

    def graph(
        self,
        symbol: Optional[str] = None,
        file: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Return symbol nodes and reference edges for the CLI/MCP graph view."""
        limit = max(1, min(int(limit), 500))
        conn = self._connect()
        try:
            stats = {
                "files": conn.execute("SELECT COUNT(*) FROM indexed_files").fetchone()[
                    0
                ],
                "symbols": conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0],
                "references": conn.execute(
                    "SELECT COUNT(*) FROM symbol_references"
                ).fetchone()[0],
                "memory_links": conn.execute(
                    "SELECT COUNT(*) FROM memory_links ml "
                    "JOIN indexed_files i ON i.path = ml.path "
                    "AND i.sha256 = ml.sha256"
                ).fetchone()[0],
            }

            nodes: List[Dict[str, Any]] = []
            edges: List[Dict[str, Any]] = []
            top_targets: List[Dict[str, Any]] = []

            if symbol:
                rows = conn.execute(
                    "SELECT path, name, kind, start_line, end_line, signature_hash "
                    "FROM symbols WHERE name = ? ORDER BY path, start_line LIMIT ?",
                    (symbol, limit),
                ).fetchall()
                nodes = [dict(row) for row in rows]
                rows = conn.execute(
                    "SELECT path, src_symbol, kind, target, line "
                    "FROM symbol_references "
                    "WHERE target = ? OR src_symbol = ? "
                    "ORDER BY path, line LIMIT ?",
                    (symbol, symbol, limit * 10),
                ).fetchall()
                edges = [dict(row) for row in rows]
            elif file:
                normalized = file.replace(os.sep, "/")
                rows = conn.execute(
                    "SELECT path, name, kind, start_line, end_line, signature_hash "
                    "FROM symbols WHERE path = ? ORDER BY start_line LIMIT ?",
                    (normalized, limit),
                ).fetchall()
                nodes = [dict(row) for row in rows]
                rows = conn.execute(
                    "SELECT path, src_symbol, kind, target, line "
                    "FROM symbol_references WHERE path = ? "
                    "ORDER BY line LIMIT ?",
                    (normalized, limit * 10),
                ).fetchall()
                edges = [dict(row) for row in rows]
            else:
                rows = conn.execute(
                    "SELECT s.path, s.name, s.kind, s.start_line, s.end_line, "
                    "COUNT(r.target) AS incoming "
                    "FROM symbols s "
                    "LEFT JOIN symbol_references r ON r.target = s.name "
                    "GROUP BY s.path, s.name, s.kind, s.start_line, s.end_line "
                    "ORDER BY incoming DESC, s.name LIMIT ?",
                    (limit,),
                ).fetchall()
                nodes = [dict(row) for row in rows]
                rows = conn.execute(
                    "SELECT target, kind, COUNT(*) AS count "
                    "FROM symbol_references GROUP BY target, kind "
                    "ORDER BY count DESC, target LIMIT ?",
                    (limit,),
                ).fetchall()
                top_targets = [dict(row) for row in rows]

            if edges:
                names = sorted({edge["target"] for edge in edges})
                placeholders = ",".join(["?"] * len(names))
                resolved = conn.execute(
                    "SELECT path, name, kind, start_line FROM symbols "
                    f"WHERE name IN ({placeholders})",
                    tuple(names),
                ).fetchall()
                targets: Dict[str, List[Dict[str, Any]]] = {}
                for row in resolved:
                    targets.setdefault(row["name"], []).append(dict(row))
                for edge in edges:
                    edge["resolved"] = targets.get(edge["target"], [])
                symbols_for_links = sorted(
                    {edge["src_symbol"] for edge in edges if edge["src_symbol"]}
                )
                if symbols_for_links:
                    placeholders = ",".join(["?"] * len(symbols_for_links))
                    link_rows = conn.execute(
                        "SELECT ml.symbol, ml.path, COUNT(DISTINCT ml.memory_id) AS count "
                        "FROM memory_links ml "
                        "JOIN indexed_files i ON i.path = ml.path "
                        "AND i.sha256 = ml.sha256 "
                        f"WHERE ml.symbol IN ({placeholders}) "
                        "GROUP BY ml.symbol, ml.path",
                        tuple(symbols_for_links),
                    ).fetchall()
                    link_counts = {
                        (row["symbol"], row["path"]): row["count"] for row in link_rows
                    }
                    for node in nodes:
                        node["memory_links"] = link_counts.get(
                            (node["name"], node["path"]), 0
                        )
        finally:
            conn.close()

        return {
            "stats": stats,
            "nodes": nodes,
            "edges": edges,
            "top_targets": top_targets,
            "symbol": symbol,
            "file": file,
        }
