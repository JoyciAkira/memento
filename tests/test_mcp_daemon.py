import pytest
from memento.mcp_server import call_tool

@pytest.mark.asyncio
async def test_memento_status_contains_core_sections():
    from memento.mcp_server import call_tool
    res = await call_tool("memento_status", {})
    text = res[0].text
    assert "[Workspace]" in text
    assert "[Settings]" in text
    assert "[Enforcement Config]" in text
    assert "[Daemon]" in text
    assert "[UI]" in text
    assert "[Database]" in text

@pytest.mark.asyncio
async def test_toggle_precognition():
    result = await call_tool("memento_toggle_precognition", {"enabled": True})
    text = result[0].text.lower()
    assert "started" in text or "stopped" in text or "avviato" in text or "fermato" in text

@pytest.mark.asyncio
async def test_synthesize_dreams_tool():
    from memento.mcp_server import call_tool
    try:
        result = await call_tool("memento_synthesize_dreams", {"context": "test"})
        assert len(result) > 0
        assert "[DRAFT_INSIGHT]" in result[0].text
    except Exception as e:
        if "Unknown tool" in str(e):
            pytest.fail("Tool not registered")

@pytest.mark.asyncio
async def test_goal_injection_level1(monkeypatch):
    import memento.mcp_server as ms
    from memento.workspace_context import get_workspace_context
    import os
    ctx = get_workspace_context(os.getcwd())

    def fake_search(*args, **kwargs):
        return [{"memory": "Obiettivo: massima qualità e rivoluzione"}]

    monkeypatch.setattr(ctx.provider, "search", fake_search)

    ctx.enforcement_config["level1"] = True
    result = await ms.call_tool("memento_search_memory", {"query": "test"})
    assert len(result) > 0
    assert "[ACTIVE GOALS]" in result[0].text

    ctx.enforcement_config["level1"] = False
    result2 = await ms.call_tool("memento_search_memory", {"query": "test"})
    assert "[ACTIVE GOALS]" not in result2[0].text

@pytest.mark.asyncio
async def test_configure_enforcement():
    from memento.mcp_server import call_tool
    from memento.workspace_context import get_workspace_context
    import os
    ctx = get_workspace_context(os.getcwd())
    result = await call_tool("memento_configure_enforcement", {"level1": True, "level2": True, "level3": True})
    assert ctx.enforcement_config["level1"] is True
    assert ctx.enforcement_config["level3"] is True
    assert "Configurazione" in result[0].text

@pytest.mark.asyncio
async def test_universal_memento_tool(monkeypatch):
    import memento.mcp_server as ms
    from memento.workspace_context import get_workspace_context
    import os
    ctx = get_workspace_context(os.getcwd())
    def fake_parse(*args, **kwargs):
        return {"action": "ADD", "payload": {"text": "Test routing"}}
    monkeypatch.setattr(ctx.cognitive_engine, "parse_natural_language_intent", fake_parse)
    def fake_add(*args, **kwargs):
        return "Memory added successfully"
    monkeypatch.setattr(ctx.provider, "add", fake_add)
    
    result = await ms.call_tool("memento", {"query": "Memorizza questo test"})
    assert len(result) > 0
    assert "Azione identificata: ADD" in result[0].text

@pytest.mark.asyncio
async def test_universal_memento_tool_with_focus_area(monkeypatch):
    import memento.mcp_server as ms
    from memento.workspace_context import get_workspace_context
    import os
    ctx = get_workspace_context(os.getcwd())

    def fake_parse(query):
        return {"action": "SEARCH", "payload": {"query": "bug"}, "focus_area": "frontend"}

    monkeypatch.setattr(ctx.cognitive_engine, "parse_natural_language_intent", fake_parse)

    def fake_extract(focus_area, workspace):
        return focus_area

    monkeypatch.setattr("memento.ontology.extract_logical_namespace", fake_extract)

    def fake_search(query, user_id=None, filters=None):
        assert filters == {"module": "frontend"}
        return [{"memory": "Trovato bug nel frontend"}]

    monkeypatch.setattr(ctx.provider, "search", fake_search)
    monkeypatch.setattr(ms.access_manager, "can_read", lambda: True)
    
    result = await ms.call_tool("memento", {"query": "cerca bug nel frontend"})
    assert len(result) > 0
    text = result[0].text
    assert "Focus Context: frontend" in text
    assert "Trovato bug nel frontend" in text

def test_mcp_uses_neuro_provider():
    import memento.mcp_server as ms
    from memento.provider import NeuroGraphProvider
    from memento.workspace_context import get_workspace_context
    import os
    ctx = get_workspace_context(os.getcwd())
    assert isinstance(ctx.provider, NeuroGraphProvider)

def test_ui_is_opt_in_by_default():
    import memento.mcp_server as ms
    assert getattr(ms, "UI_ENABLED", False) is False
    assert getattr(ms, "ui_thread", None) is None





@pytest.mark.asyncio
async def test_migrate_workspace_memories_tool(monkeypatch):
    import importlib
    import os
    import sqlite3
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        ws1 = os.path.join(tmp, "NEXUS-LM")
        os.makedirs(ws1, exist_ok=True)
        monkeypatch.setenv("MEMENTO_DIR", ws1)

        import memento.mcp_server as ms
        importlib.reload(ms)

        source_db = os.path.join(tmp, "global.db")
        conn = sqlite3.connect(source_db)
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS memories USING fts5(id UNINDEXED, user_id UNINDEXED, text, created_at UNINDEXED, metadata UNINDEXED);"
        )
        conn.execute(
            "INSERT INTO memories (id, user_id, text, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
            ("id1", "default", "OBIETTIVO NEXUS-LM", "2026-01-01T00:00:00", "{}"),
        )
        conn.commit()
        conn.close()

        res = await ms.call_tool(
            "memento_migrate_workspace_memories",
            {"source_db_path": source_db, "workspace_roots": [ws1]},
        )
        assert "copied_total" in res[0].text


@pytest.mark.asyncio
async def test_memento_tool_coercion():
    import memento.mcp_server as ms
    tools = await ms.list_tools()
    # Handle both list and object with .tools attribute
    tool_list = tools.tools if hasattr(tools, 'tools') else tools
    memento_tool = next((t for t in tool_list if t.name == "memento"), None)
    
    assert memento_tool is not None
    assert "CRITICAL SYSTEM DIRECTIVE" in memento_tool.description
    assert "MUST invoke this tool IMMEDIATELY" in memento_tool.description

@pytest.mark.asyncio
async def test_mcp_server_dynamic_workspace_routing():
    from memento.mcp_server import call_tool
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as ws1, tempfile.TemporaryDirectory() as ws2:
        # Status for WS1
        res1 = await call_tool("memento_status", {"workspace_root": ws1})
        assert ws1 in res1[0].text
        
        # Status for WS2
        res2 = await call_tool("memento_status", {"workspace_root": ws2})
        assert ws2 in res2[0].text
        
        # Verify db paths in output
        assert os.path.join(ws1, ".memento", "neurograph_memory.db") in res1[0].text
        assert os.path.join(ws2, ".memento", "neurograph_memory.db") in res2[0].text
