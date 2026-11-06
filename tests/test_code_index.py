import os
import sqlite3

import pytest

from memento.code_index import CodeIndex
from memento.ledger import FileLedger

pytest.importorskip("tree_sitter")


def _write(project, rel: str, text: str) -> str:
    path = os.path.join(str(project), rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def test_index_only_reparses_changed_files(tmp_path):
    _write(
        tmp_path,
        "a.py",
        "from os import path\n\n"
        "def hello(x):\n"
        "    return x\n\n"
        "class Greeter:\n"
        "    def greet(self):\n"
        "        return 'hi'\n",
    )
    _write(tmp_path, "note.txt", "not source")

    ledger = FileLedger(str(tmp_path))
    ledger.sync()
    index = CodeIndex(str(tmp_path), ledger=ledger)

    first = index.update()
    assert first["indexed"] == 1
    assert first["removed"] == 0
    assert first["skipped"] == 1
    assert first["symbols"] == 3
    assert first["languages"] == {"python": 1}
    assert first["parser"] == "tree-sitter"

    second = index.update()
    assert second["indexed"] == 0
    assert second["unchanged"] == 1

    _write(tmp_path, "a.py", "def changed():\n    return 1\n")
    ledger.sync()
    third = index.update()
    assert third["indexed"] == 1
    assert third["symbols"] == 1

    conn = sqlite3.connect(index.cache_path)
    names = {row[0] for row in conn.execute("SELECT name FROM symbols")}
    conn.close()
    assert names == {"changed"}

    os.remove(os.path.join(str(tmp_path), "a.py"))
    ledger.sync()
    fourth = index.update()
    assert fourth["removed"] == 1

    conn = sqlite3.connect(index.cache_path)
    assert conn.execute("SELECT COUNT(*) FROM indexed_files").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0] == 0
    conn.close()


def test_index_without_parser_leaves_cache_untouched(tmp_path):
    _write(tmp_path, "a.py", "def a():\n    return 1\n")
    ledger = FileLedger(str(tmp_path))
    ledger.sync()
    index = CodeIndex(str(tmp_path), ledger=ledger)
    index.parsers = {}

    report = index.update()

    assert report["parser"] == "unavailable"
    assert report["indexed"] == 0
    assert report["error"].startswith("tree-sitter not installed")
    assert not os.path.exists(index.cache_path)


def test_index_extracts_references_and_graph(tmp_path):
    _write(
        tmp_path,
        "a.py",
        "from os import path\n"
        "from .base import Base\n\n"
        "def helper(x):\n"
        "    return x\n\n"
        "def hello():\n"
        "    return helper(1)\n\n"
        "class Greeter(Base):\n"
        "    def greet(self):\n"
        "        return helper(2)\n",
    )
    ledger = FileLedger(str(tmp_path))
    ledger.sync()
    index = CodeIndex(str(tmp_path), ledger=ledger)

    report = index.update()

    assert report["references"] >= 5
    graph = index.graph(symbol="helper")
    assert [node["name"] for node in graph["nodes"]] == ["helper"]
    call_sources = {
        edge["src_symbol"] for edge in graph["edges"] if edge["kind"] == "call"
    }
    assert {"hello", "greet"} <= call_sources
    assert graph["stats"]["references"] >= 5

    by_file = index.graph(file="a.py")
    assert {node["name"] for node in by_file["nodes"]} >= {
        "helper",
        "hello",
        "Greeter",
        "greet",
    }
    assert any(edge["kind"] == "inherits" for edge in by_file["edges"])
    assert any(edge["kind"] == "import" for edge in by_file["edges"])


def test_index_commands_are_wired():
    from memento.cli import _build_parser

    index_args = _build_parser().parse_args(["index", "--rebuild", "--json"])
    assert index_args.command == "index"
    assert index_args.rebuild is True
    assert index_args.json is True

    sync_args = _build_parser().parse_args(["sync", "--no-index", "--compact"])
    assert sync_args.no_index is True
    assert sync_args.compact is True

    hook_args = _build_parser().parse_args(["hooks", "--install"])
    assert hook_args.command == "hooks"
    assert hook_args.install is True
