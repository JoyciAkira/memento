import os
import tempfile
import pytest
from memento.provider import NeuroGraphProvider

@pytest.mark.asyncio
async def test_neuro_provider_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_memory.db")
        provider = NeuroGraphProvider(db_path=db_path)
        
        result = await provider.add("La password del server è Pippo123", user_id="default")
        assert "id" in result
        
        search_res = await provider.search("password", user_id="default")
        assert len(search_res) > 0
        assert "Pippo123" not in search_res[0]["memory"]
        assert "[REDACTED]" in search_res[0]["memory"]
        
        all_mem = await provider.get_all(user_id="default")
        assert len(all_mem) > 0


@pytest.mark.asyncio
async def test_neuro_provider_works_without_openai_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    p = NeuroGraphProvider(db_path=str(tmp_path / "mem.db"))
    await p.add("offline memory", user_id="default")
    res = await p.search("offline", user_id="default")
    assert res


@pytest.mark.asyncio
async def test_search_trace_file_not_written_when_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")
    monkeypatch.setenv("MEMENTO_WRITE_SEARCH_TRACE", "0")

    db_file = tmp_path / "mem.db"
    p = NeuroGraphProvider(db_path=str(db_file))
    await p.add("trace off test", user_id="default")
    await p.search("trace", user_id="default")

    trace_path = tmp_path / "traces" / "last_search.json"
    assert not trace_path.is_file()
