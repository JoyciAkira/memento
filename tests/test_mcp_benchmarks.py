"""Benchmark rigidi: Memento deve restare sotto soglie in ms, non passare barriere artificialmente alte."""

from __future__ import annotations

import os
import pathlib
import sys
import time
from statistics import median

import pytest

import memento.tools  # noqa: F401 — registra i tool nel registry
from memento.mcp_server import call_tool
from memento.registry import registry

_tests_dir = str(pathlib.Path(__file__).resolve().parent)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)
import mcp_contract_helpers as _mcp_contract  # noqa: E402

# --- Prestazioni (locale + CI condiviso): warm-up escluso dalle misure.
# Soglie in secondi. Su workstation tipiche sono ordini di grandezza sotto il limite;
# su runner lenti restano barriere molto più severe rispetto a gate da 10s.
_SEARCH_MEMORIES = 4000
_SEARCH_WARMUP = 5
_SEARCH_ITERATIONS = 30
_SEARCH_MEDIAN_MAX_S = 0.10
_SEARCH_P95_MAX_S = 0.35
_SEARCH_MAX_SINGLE_S = 0.75

_VNEXT_MEMORIES = 3500
_VNEXT_WARMUP = 5
_VNEXT_ITERATIONS = 25
_VNEXT_MEDIAN_MAX_S = 0.12
_VNEXT_P95_MAX_S = 0.40
_VNEXT_MAX_SINGLE_S = 0.90

_EXPECTED_TOOL_COUNT = 53


def _p95(sorted_durations: list[float]) -> float:
    if not sorted_durations:
        return 0.0
    idx = int(0.95 * (len(sorted_durations) - 1))
    return sorted_durations[idx]


def test_b1_exact_registered_tool_surface():
    names = {t.name for t in registry.get_tools()}
    assert len(names) == _EXPECTED_TOOL_COUNT, f"attesi {_EXPECTED_TOOL_COUNT} tool, trovati {len(names)}"
    for required in (
        "memento_search_vnext",
        "memento_explain_retrieval",
        "memento_set_goals",
        "memento_list_goals",
    ):
        assert required in names


@pytest.mark.asyncio
async def test_b7_storage_kg_file_distinct_from_memory_db(tmp_path, monkeypatch):
    """Layout storage: KG su file dedicato (stesso harness file-backed dei benchmark)."""
    monkeypatch.delenv("MEMENTO_KG_DB_PATH", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    from memento.provider import NeuroGraphProvider

    mem = tmp_path / "neurograph_memory.db"
    p = NeuroGraphProvider(db_path=str(mem))
    await p.initialize()
    assert os.path.abspath(p.kg_db_path) != os.path.abspath(p.db_path)
    assert os.path.isfile(p.kg_db_path)


@pytest.mark.asyncio
async def test_b2_provider_search_latency_strict(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    from memento.provider import NeuroGraphProvider

    db = tmp_path / "bench.db"
    p = NeuroGraphProvider(db_path=str(db))
    for i in range(_SEARCH_MEMORIES):
        await p.add(
            f"bench item {i} latency token alpha zeta",
            user_id="default",
        )

    for _ in range(_SEARCH_WARMUP):
        await p.search("alpha zeta latency", user_id="default", limit=10)

    durations: list[float] = []
    for _ in range(_SEARCH_ITERATIONS):
        t0 = time.perf_counter()
        rows = await p.search("alpha zeta latency", user_id="default", limit=10)
        durations.append(time.perf_counter() - t0)
        assert isinstance(rows, list)
        assert len(rows) >= 1

    durations.sort()
    med = median(durations)
    p95 = _p95(durations)
    worst = durations[-1]

    assert med < _SEARCH_MEDIAN_MAX_S, (
        f"mediana search troppo alta: {med * 1000:.2f}ms "
        f"(limite {_SEARCH_MEDIAN_MAX_S * 1000:.0f}ms, n={_SEARCH_ITERATIONS})"
    )
    assert p95 < _SEARCH_P95_MAX_S, (
        f"p95 search troppo alta: {p95 * 1000:.2f}ms (limite {_SEARCH_P95_MAX_S * 1000:.0f}ms)"
    )
    assert worst < _SEARCH_MAX_SINGLE_S, (
        f"picco search troppo alto: {worst * 1000:.2f}ms (limite {_SEARCH_MAX_SINGLE_S * 1000:.0f}ms)"
    )


@pytest.mark.asyncio
async def test_b2_vnext_bundle_latency_strict(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    from memento.provider import NeuroGraphProvider

    db = tmp_path / "bench_vnext.db"
    p = NeuroGraphProvider(db_path=str(db))
    for i in range(_VNEXT_MEMORIES):
        await p.add(f"vnext bench row {i} alpha beta gamma", user_id="default")

    for _ in range(_VNEXT_WARMUP):
        await p.search_vnext_bundle("alpha beta", user_id="default", limit=8, trace=False)

    durations: list[float] = []
    for _ in range(_VNEXT_ITERATIONS):
        t0 = time.perf_counter()
        bundle = await p.search_vnext_bundle(
            "alpha beta", user_id="default", limit=8, trace=False
        )
        durations.append(time.perf_counter() - t0)
        assert bundle.get("query") == "alpha beta"
        assert isinstance(bundle.get("results"), list)
        assert len(bundle["results"]) >= 1

    durations.sort()
    med = median(durations)
    p95 = _p95(durations)
    worst = durations[-1]

    assert med < _VNEXT_MEDIAN_MAX_S, (
        f"mediana vnext troppo alta: {med * 1000:.2f}ms "
        f"(limite {_VNEXT_MEDIAN_MAX_S * 1000:.0f}ms)"
    )
    assert p95 < _VNEXT_P95_MAX_S, (
        f"p95 vnext troppo alta: {p95 * 1000:.2f}ms (limite {_VNEXT_P95_MAX_S * 1000:.0f}ms)"
    )
    assert worst < _VNEXT_MAX_SINGLE_S, (
        f"picco vnext troppo alto: {worst * 1000:.2f}ms (limite {_VNEXT_MAX_SINGLE_S * 1000:.0f}ms)"
    )


@pytest.mark.asyncio
async def test_b3_retrieval_top_hit_correctness(tmp_path, monkeypatch):
    """Rigido sul contenuto: il primo risultato deve contenere l'ancora inserita solo lì."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    from memento.provider import NeuroGraphProvider

    db = tmp_path / "correctness.db"
    p = NeuroGraphProvider(db_path=str(db))
    anchor = "UNIQUE_ANCHOR_XQ9Z memento-benchmark-correctness"
    for i in range(400):
        await p.add(f"noise memory {i} generic filler", user_id="default")
    await p.add(anchor, user_id="default")

    rows = await p.search("UNIQUE_ANCHOR_XQ9Z", user_id="default", limit=5)
    assert rows, "search deve restituire almeno una riga"
    top = rows[0]
    assert anchor in (top.get("memory") or "")

    bundle = await p.search_vnext_bundle(
        "UNIQUE_ANCHOR_XQ9Z", user_id="default", limit=5, trace=True
    )
    assert bundle["results"]
    mem0 = bundle["results"][0].get("memory") or ""
    assert "UNIQUE_ANCHOR_XQ9Z" in mem0
    traces = bundle.get("traces") or []
    assert any(t.get("lane") == "fts" for t in traces)


@pytest.mark.asyncio
async def test_b6_offline_mcp_tools_callable(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    ws = str(tmp_path)
    await call_tool(
        "memento_add_memory",
        {"workspace_root": ws, "text": "offline bench memory zeta"},
    )

    cases = [
        ("memento_status", {"workspace_root": ws}),
        ("memento_list_goals", {"workspace_root": ws}),
        (
            "memento_search_memory",
            {"workspace_root": ws, "query": "zeta"},
        ),
        (
            "memento_explain_search",
            {"workspace_root": ws, "query": "zeta"},
        ),
        (
            "memento_search_vnext",
            {"workspace_root": ws, "query": "zeta", "limit": 5, "trace": False},
        ),
        (
            "memento_explain_retrieval",
            {"workspace_root": ws, "query": "zeta"},
        ),
        (
            "memento_set_goals",
            {"workspace_root": ws, "goals": ["benchmark-offline-goal"]},
        ),
        ("memento_memory_stats", {"workspace_root": ws}),
        ("memento_kg_health", {"workspace_root": ws}),
    ]
    for name, args in cases:
        out = await call_tool(name, args)
        assert isinstance(out, list) and len(out) > 0
        if name == "memento_search_memory":
            assert "zeta" in out[0].text.lower()
        elif name == "memento_memory_stats":
            assert "Memory stats" in out[0].text
            assert "{" in out[0].text
        elif name == "memento_kg_health":
            assert "KG health" in out[0].text
            assert "{" in out[0].text
        elif name == "memento_explain_search":
            _mcp_contract.validate_tool_response_contract(
                name, out, strict_search_trace=True
            )
        elif name in (
            "memento_search_vnext",
            "memento_explain_retrieval",
            "memento_list_goals",
            "memento_set_goals",
        ):
            _mcp_contract.validate_tool_response_contract(name, out)
