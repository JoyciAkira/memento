import pytest
import tempfile

from memento.workspace_context import get_workspace_context


def test_get_active_goals_uses_context_in_search_query(monkeypatch):
    import memento.mcp_server as ms

    captured = {}

    def fake_search(query, user_id=None, filters=None):
        captured["query"] = query
        captured["user_id"] = user_id
        captured["filters"] = filters
        return [{"memory": "Goal A"}, {"memory": "Goal B"}]

    with tempfile.TemporaryDirectory() as ws:
        ctx = get_workspace_context(ws)
        monkeypatch.setattr(ctx.provider, "search", fake_search)
        out = ms.get_active_goals(ctx, context="frontend/app.py")

    assert captured["user_id"] == "default"
    assert captured["filters"] is None
    assert captured["query"] == "obiettivo goal per il contesto: frontend/app.py"
    assert out.startswith("[ACTIVE GOALS]\n- ")
    assert "Goal A" in out
    assert "Goal B" in out


@pytest.mark.asyncio
async def test_search_memory_applies_module_filter_from_active_context(monkeypatch):
    import memento.mcp_server as ms

    monkeypatch.setattr(ms.access_manager, "can_read", lambda: True)
    monkeypatch.setattr(
        "memento.ontology.extract_logical_namespace",
        lambda active_context, workspace_root: "backend",
    )

    def fake_search(query, user_id=None, filters=None):
        assert query == "find stuff"
        assert user_id == "default"
        assert filters == {"module": "backend"}
        return [{"memory": "Backend memory hit"}]

    with tempfile.TemporaryDirectory() as ws:
        ctx = get_workspace_context(ws)
        monkeypatch.setattr(ctx.provider, "search", fake_search)

        res = await ms.call_tool(
            "memento_search_memory",
            {"query": "find stuff", "active_context": "backend/service.py", "workspace_root": ws},
        )
        assert "Backend memory hit" in res[0].text


@pytest.mark.asyncio
async def test_universal_router_focus_area_routes_and_passes_module_filter(monkeypatch):
    import memento.mcp_server as ms

    with tempfile.TemporaryDirectory() as ws:
        ctx = get_workspace_context(ws)

        monkeypatch.setattr(ms.access_manager, "can_read", lambda: True)
        monkeypatch.setattr(
            ctx.cognitive_engine,
            "parse_natural_language_intent",
            lambda q: {"action": "SEARCH", "payload": {"query": "bug"}, "focus_area": "frontend"},
        )
        monkeypatch.setattr(
            "memento.ontology.extract_logical_namespace",
            lambda focus_area, workspace_root: "frontend",
        )

        def fake_search(query, user_id=None, filters=None):
            assert query == "bug"
            assert user_id == "default"
            assert filters == {"module": "frontend"}
            return [{"memory": "Found frontend bug"}]

        monkeypatch.setattr(ctx.provider, "search", fake_search)

        res = await ms.call_tool("memento", {"query": "cerca bug nel frontend", "workspace_root": ws})
        text = res[0].text
        assert "Focus Context: frontend" in text
        assert "Found frontend bug" in text


@pytest.mark.asyncio
async def test_universal_router_level1_injection_uses_focus_area_as_context(monkeypatch):
    import memento.mcp_server as ms

    with tempfile.TemporaryDirectory() as ws:
        ctx = get_workspace_context(ws)
        prev = dict(ctx.enforcement_config)
        ctx.enforcement_config["level1"] = True
        monkeypatch.setattr(ms.access_manager, "can_read", lambda: True)

        monkeypatch.setattr(
            ctx.cognitive_engine,
            "parse_natural_language_intent",
            lambda q: {"action": "SEARCH", "payload": {"query": "x"}, "focus_area": "frontend"},
        )
        monkeypatch.setattr(
            "memento.ontology.extract_logical_namespace",
            lambda focus_area, workspace_root: "frontend",
        )

        captured = {"ctx": None}

        def fake_get_active_goals(_ctx, max_goals: int = 3, context: str = None):
            captured["ctx"] = context
            return "[ACTIVE GOALS]\n- G1\n\n"

        monkeypatch.setattr(ms, "get_active_goals", fake_get_active_goals)
        monkeypatch.setattr(
            ctx.provider,
            "search",
            lambda query, user_id=None, filters=None: [{"memory": "hit"}],
        )

        res = await ms.call_tool("memento", {"query": "whatever", "workspace_root": ws})
        assert captured["ctx"] == "frontend"
        assert "[ACTIVE GOALS]" in res[0].text
        ctx.enforcement_config.clear()
        ctx.enforcement_config.update(prev)
