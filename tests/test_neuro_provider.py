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
