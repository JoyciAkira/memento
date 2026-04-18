"""Benchmark misurabili per superficie MCP (gate numerici, no hype)."""

import time

import pytest

import memento.tools  # noqa: F401 — registra i tool nel registry
from memento.mcp_server import call_tool
from memento.registry import registry


def test_b1_registered_tool_surface_complete():
    names = {t.name for t in registry.get_tools()}
    assert "memento_search_vnext" in names
    assert "memento_explain_retrieval" in names
    assert "memento_set_goals" in names
    assert "memento_list_goals" in names
    assert len(names) >= 45


@pytest.mark.asyncio
async def test_b2_provider_search_latency_gate(tmp_path, monkeypatch):
    """Gate su mediana/p95 locale (embedding disabilitato, nessuna rete)."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    from memento.provider import NeuroGraphProvider

    db = tmp_path / "bench.db"
    p = NeuroGraphProvider(db_path=str(db))
    for i in range(30):
        await p.add(f"task memory benchmark item {i} about latency", user_id="default")

    durations: list[float] = []
    for _ in range(12):
        t0 = time.perf_counter()
        await p.search("benchmark latency", user_id="default", limit=10)
        durations.append(time.perf_counter() - t0)

    durations.sort()
    median = durations[len(durations) // 2]
    p95 = durations[int(0.95 * (len(durations) - 1))]

    assert median < 10.0, f"median search too slow: {median:.3f}s"
    assert p95 < 15.0, f"p95 search too slow: {p95:.3f}s"


@pytest.mark.asyncio
async def test_b2_vnext_bundle_latency_gate(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    from memento.provider import NeuroGraphProvider

    db = tmp_path / "bench_vnext.db"
    p = NeuroGraphProvider(db_path=str(db))
    for i in range(20):
        await p.add(f"vnext bench row {i} alpha beta", user_id="default")

    durations: list[float] = []
    for _ in range(10):
        t0 = time.perf_counter()
        await p.search_vnext_bundle("alpha", user_id="default", limit=8, trace=False)
        durations.append(time.perf_counter() - t0)

    durations.sort()
    median = durations[len(durations) // 2]
    assert median < 10.0, f"median vnext search too slow: {median:.3f}s"


@pytest.mark.asyncio
async def test_b6_offline_mcp_tools_callable(tmp_path, monkeypatch):
    """Senza OPENAI_API_KEY: tool read-only / retrieval locale non devono sollevare."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    ws = str(tmp_path)
    cases = [
        ("memento_status", {"workspace_root": ws}),
        ("memento_list_goals", {"workspace_root": ws}),
        ("memento_search_vnext", {"workspace_root": ws, "query": "x"}),
        ("memento_explain_retrieval", {"workspace_root": ws, "query": "x"}),
    ]
    for name, args in cases:
        out = await call_tool(name, args)
        assert isinstance(out, list) and len(out) > 0
