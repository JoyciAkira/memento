import os

import pytest

from memento.code_grounding import MemoryGrounder
from memento.code_index import CodeIndex
from memento.knowledge_graph import KnowledgeGraph
from memento.ledger import FileLedger

pytest.importorskip("tree_sitter")


def _write(project, rel: str, text: str) -> str:
    path = os.path.join(str(project), rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _project(tmp_path):
    (tmp_path / ".git").mkdir()
    _write(
        tmp_path,
        "a.py",
        "class Base:\n"
        "    pass\n\n"
        "class Greeter(Base):\n"
        "    def greet(self):\n"
        "        return helper(1)\n\n"
        "def helper(x):\n"
        "    return x\n",
    )
    ledger = FileLedger(str(tmp_path))
    ledger.sync()
    index = CodeIndex(str(tmp_path), ledger=ledger)
    index.update()
    return ledger, index


def test_links_memories_with_hashes_and_filters_stale(tmp_path):
    ledger, index = _project(tmp_path)
    grounder = MemoryGrounder(str(tmp_path))

    report = grounder.link_all([("m1", "Greeter.greet should call helper; see a.py:6")])

    assert report["memories_linked"] == 1
    assert report["links"] >= 3
    links = grounder.links_for_memories(["m1"])["m1"]
    assert links and all(link["current"] for link in links)
    assert all(0.5 <= link["confidence"] <= 1.0 for link in links)
    assert {link["symbol"] for link in links} & {"Greeter", "greet", "helper"}
    assert grounder.memory_ids_for_query("helper") == ["m1"]

    _write(tmp_path, "a.py", "def helper(x):\n    return x + 1\n")
    ledger.sync()
    index.update()

    stale = grounder.links_for_memories(["m1"])["m1"]
    assert any(link["stale"] for link in stale)
    assert grounder.memory_ids_for_query("helper") == []

    rebuilt = grounder.link_all([("m1", "Greeter calls helper")], rebuild=True)
    assert rebuilt["memories_linked"] == 1
    assert grounder.memory_ids_for_query("helper") == ["m1"]
    fresh = grounder.links_for_memories(["m1"])["m1"]
    assert fresh and all(link["current"] for link in fresh)


def test_generic_symbols_require_path_context(tmp_path):
    (tmp_path / ".git").mkdir()
    for name in ("a.py", "b.py", "c.py", "d.py"):
        _write(tmp_path, name, "def run():\n    return 1\n")
    ledger = FileLedger(str(tmp_path))
    ledger.sync()
    CodeIndex(str(tmp_path), ledger=ledger).update()
    grounder = MemoryGrounder(str(tmp_path))

    report = grounder.link_all([("m1", "run the tests")])
    assert report["memories_linked"] == 0
    assert grounder.memory_ids_for_query("run") == []

    report = grounder.link_all([("m2", "run in a.py")])
    assert report["memories_linked"] == 1
    links = grounder.links_for_memories(["m2"])["m2"]
    run_links = [link for link in links if link["symbol"] == "run"]
    assert [link["path"] for link in run_links] == ["a.py"]
    assert run_links[0]["confidence"] >= 0.7


def test_grounding_writes_kg_triples(tmp_path):
    _project(tmp_path)
    kg = KnowledgeGraph(str(tmp_path / "kg.sqlite"))
    grounder = MemoryGrounder(str(tmp_path))

    report = grounder.link_all([("m1", "helper is used by Greeter")], kg=kg)

    assert report["kg_triples"] >= 1
    triples = kg.query_entity("helper is used by Greeter", direction="outgoing")
    assert any(triple["predicate"] == "grounded_in" for triple in triples)
    kg.close()


def test_grounding_requires_existing_index(tmp_path):
    grounder = MemoryGrounder(str(tmp_path))

    report = grounder.link_all([("m1", "helper")])

    assert report["index_available"] is False
    assert "memento sync" in report["error"]


@pytest.mark.asyncio
async def test_provider_links_and_surfaces_code(tmp_path):
    (tmp_path / ".git").mkdir()
    _write(tmp_path, "a.py", "def helper(x):\n    return x\n")
    ledger = FileLedger(str(tmp_path))
    ledger.sync()
    CodeIndex(str(tmp_path), ledger=ledger).update()

    from memento.provider import NeuroGraphProvider

    db_path = str(tmp_path / ".memento" / "neurograph_memory.db")
    provider = NeuroGraphProvider(db_path=db_path)

    result = await provider.add("helper is used in the sample")
    links = provider.code_grounder.links_for_memories([result["id"]])
    assert links[result["id"]]

    found = await provider.search("helper", user_id="default", limit=5)
    assert found
    assert any(item.get("code_links") for item in found)
