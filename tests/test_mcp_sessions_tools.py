import pytest

from memento.mcp_server import call_tool


@pytest.mark.asyncio
async def test_handoff_and_resume_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")
    monkeypatch.setenv("MEMENTO_HANDOFF_AUTO_CHECKPOINT_EVERY_N_EVENTS", "1000000")
    ws = str(tmp_path)

    out = await call_tool("memento_handoff", {"workspace_root": ws})
    text = out[0].text
    assert "MEMENTO SESSION HANDOFF" in text
    assert "Session:" in text

    session_id_line = next(line for line in text.splitlines() if line.startswith("Session:"))
    session_id = session_id_line.split("Session:", 1)[1].strip()

    out2 = await call_tool("memento_resume_session", {"workspace_root": ws, "session_id": session_id})
    assert "resumed_from" in out2[0].text

