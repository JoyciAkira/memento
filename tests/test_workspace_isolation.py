import os
import tempfile
import pytest

@pytest.mark.asyncio
async def test_workspace_context_isolation():
    from memento.workspace_context import get_workspace_context
    
    with tempfile.TemporaryDirectory() as ws1, tempfile.TemporaryDirectory() as ws2:
        ctx1 = get_workspace_context(ws1)
        ctx2 = get_workspace_context(ws2)
        
        assert ctx1 is not ctx2
        assert ctx1.provider.db_path.startswith(ws1)
        assert ctx2.provider.db_path.startswith(ws2)
        
        # Test caching
        ctx1_cached = get_workspace_context(ws1)
        assert ctx1 is ctx1_cached
