import asyncio
import pytest
from memento.daemon import PreCognitiveDaemon

@pytest.mark.asyncio
async def test_daemon_debounce():
    call_count = 0
    async def mock_callback(filepath, content):
        nonlocal call_count
        call_count += 1
        
    daemon = PreCognitiveDaemon(workspace_path="/tmp", callback=mock_callback, debounce_seconds=0.1)
    await daemon.handle_file_change("/tmp/test.py", "import logging; logging.info('hello')")
    await daemon.handle_file_change("/tmp/test.py", "import logging; logging.info('world')")
    await asyncio.sleep(0.2)
    assert call_count == 1
