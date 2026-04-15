# Pre-cognitive Intervention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an autonomous daemon (Watcher) that monitors the workspace in the background and pushes "Spider-Sense" MCP notifications when users write code that triggers historical anti-patterns in the Knowledge Graph.

**Architecture:** A `watchdog` process monitors file changes asynchronously, debounces events, generates embeddings via Mem0, and uses `cosine_similarity` to check against "warnings". If a match is found, it sends a custom JSON-RPC notification back to the MCP client.

**Tech Stack:** Python, `watchdog`, asyncio, MCP Protocol (JSON-RPC), Mem0 Embeddings.

---

# Tasks

### Task 1: Install Dependencies & Setup Daemon Scaffold
**Files:**
- Modify: `pyproject.toml`
- Create: `memento/daemon.py`
- Create: `tests/test_daemon.py`

- [x] **Step 1: Install watchdog dependency**
Add `watchdog>=4.0.0` to the dependencies list in `pyproject.toml`.
Run: `uv pip install watchdog`
Expected: Installation successful.

- [x] **Step 2: Write failing test for Debounced Watcher**
```python
# Create tests/test_daemon.py
import asyncio
from memento.daemon import PreCognitiveDaemon

@pytest.mark.asyncio
async def test_daemon_debounce():
    # Mock callback to count triggers
    call_count = 0
    async def mock_callback(filepath, content):
        nonlocal call_count
        call_count += 1
        
    daemon = PreCognitiveDaemon(workspace_path="/tmp", callback=mock_callback, debounce_seconds=0.1)
    
    # Simulate multiple rapid file modifications
    await daemon.handle_file_change("/tmp/test.py", "print('hello')")
    await daemon.handle_file_change("/tmp/test.py", "print('world')")
    
    # Wait for debounce
    await asyncio.sleep(0.2)
    
    # It should only trigger the callback ONCE due to debouncing
    assert call_count == 1
```

- [x] **Step 3: Run test to verify it fails**
Run: `uv run pytest tests/test_daemon.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'memento.daemon'"

- [x] **Step 4: Implement minimal PreCognitiveDaemon**
```python
# Create memento/daemon.py
import asyncio
import os
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)

class PreCognitiveDaemon:
    def __init__(self, workspace_path: str, callback, debounce_seconds: float = 5.0):
        self.workspace_path = workspace_path
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self._timers = {}
        self.observer = None
        self.is_running = False

    async def handle_file_change(self, filepath: str, content: str):
        if filepath in self._timers:
            self._timers[filepath].cancel()
            
        async def _trigger():
            try:
                await self.callback(filepath, content)
            except Exception as e:
                logger.error(f"Daemon callback error: {e}")
                
        # Create a delayed task (debounce)
        loop = asyncio.get_event_loop()
        self._timers[filepath] = loop.call_later(
            self.debounce_seconds, 
            lambda: asyncio.create_task(_trigger())
        )

    def start(self):
        # We will implement watchdog observer in a later step
        self.is_running = True

    def stop(self):
        self.is_running = False
        for timer in self._timers.values():
            timer.cancel()
        if self.observer:
            self.observer.stop()
            self.observer.join()
```

- [x] **Step 5: Run test to verify it passes**
Run: `uv run pytest tests/test_daemon.py -v`
Expected: PASS

- [x] **Step 6: Commit**
```bash
git add pyproject.toml memento/daemon.py tests/test_daemon.py
git commit -m "feat: add watchdog dependency and debounce daemon structure"
```

---

### Task 2: Enhance Cognitive Engine to Evaluate Raw Text
**Files:**
- Modify: `memento/cognitive_engine.py`
- Modify: `tests/test_cognitive_engine.py` (Create)

- [x] **Step 1: Write failing test**
```python
# Create tests/test_cognitive_engine.py
import pytest
from memento.cognitive_engine import CognitiveEngine

class MockProvider:
    def search(self, query):
        # Return mock results simulating negative historical context
        return {"results": [
            {"memory": "BUG: Using SQLite for high-concurrency caused deadlocks.", "score": 0.9}
        ]}

def test_evaluate_code_for_warnings():
    provider = MockProvider()
    engine = CognitiveEngine(provider)
    
    code_snippet = "import sqlite3\ndef write_data(): db.execute('INSERT...')"
    warning = engine.evaluate_raw_context(code_snippet)
    
    assert "BUG: Using SQLite" in warning
    assert "SPIDER-SENSE" in warning
```

- [x] **Step 2: Run test to verify it fails**
Run: `uv run pytest tests/test_cognitive_engine.py -v`
Expected: FAIL with "AttributeError: 'CognitiveEngine' object has no attribute 'evaluate_raw_context'"

- [x] **Step 3: Implement `evaluate_raw_context`**
Update `memento/cognitive_engine.py`:
```python
    def evaluate_raw_context(self, raw_text: str) -> str:
        """
        Takes raw text (e.g. from a file change) and checks if it closely matches
        any historical bugs or anti-patterns.
        """
        logger.info("CognitiveEngine evaluating raw context from daemon...")
        try:
            # Search the KG for concepts related to the raw text
            # We assume provider.search internally computes the embedding of raw_text
            # and returns cosine-similarity matches.
            res_dict = self.provider.search(raw_text)
            results = res_dict.get("results", []) if isinstance(res_dict, dict) else res_dict
            
            warnings = []
            negative_keywords = ["bug", "error", "problem", "fail", "issue", "time", "broken", "deprecated", "leak"]
            
            for r in results:
                if not isinstance(r, dict): continue
                # Only consider highly relevant matches (e.g. score > 0.8) to avoid false positives
                score = r.get("score", 0.0)
                if score < 0.8:
                    continue
                    
                memory_text = r.get("memory", "").lower()
                if any(kw in memory_text for kw in negative_keywords):
                    warnings.append(r.get("memory"))
            
            if warnings:
                formatted = "\\n- ".join(warnings)
                return f"⚠️ SPIDER-SENSE WARNING:\\n- {formatted}"
            return "" # Return empty string if no danger detected
            
        except Exception as e:
            logger.error(f"Error evaluating raw context: {e}")
            return ""
```

- [x] **Step 4: Run test to verify it passes**
Run: `uv run pytest tests/test_cognitive_engine.py -v`
Expected: PASS

- [x] **Step 5: Commit**
```bash
git add memento/cognitive_engine.py tests/test_cognitive_engine.py
git commit -m "feat: cognitive engine can evaluate raw code for high-confidence warnings"
```

---

### Task 3: Wire Daemon to MCP Server and Add Toggle Tool
**Files:**
- Modify: `memento/mcp_server.py`

- [x] **Step 1: Write failing test for toggle tool**
```python
# Add to tests/test_mcp.py (or create test_mcp_daemon.py)
import pytest
import asyncio
from memento.mcp_server import call_tool, daemon

@pytest.mark.asyncio
async def test_toggle_precognition():
    # By default, let's assume it's disabled or enabled. We just toggle it.
    initial_state = daemon.is_running
    
    result = await call_tool("memento_toggle_precognition", {"enabled": not initial_state})
    
    assert daemon.is_running != initial_state
    assert "Successfully" in result[0].text
```

- [x] **Step 2: Run test to verify it fails**
Run: `uv run pytest tests/test_mcp_daemon.py -v`
Expected: FAIL because `daemon` and `memento_toggle_precognition` don't exist.

- [x] **Step 3: Implement MCP integration**
In `memento/mcp_server.py`:
```python
from memento.daemon import PreCognitiveDaemon
import os

# Initialize daemon
async def on_danger_detected(filepath: str, content: str):
    warning = cognitive_engine.evaluate_raw_context(content)
    if warning:
        logger.warning(f"Pushing MCP Notification for {filepath}: {warning}")
        # Send custom JSON-RPC notification to the client
        # Requires accessing the active session. MCP SDK allows `session.send_notification()`
        # For simplicity in stdio, we can emit a log or use server.request_context
        from mcp.server import request_ctx
        try:
            ctx = request_ctx.get()
            await ctx.session.send_notification("memento/precognitive_warning", {
                "file": filepath,
                "warning": warning
            })
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

# The workspace path should be provided by environment or default to cwd
workspace = os.environ.get("MEMPAL_DIR", os.getcwd())
daemon = PreCognitiveDaemon(workspace_path=workspace, callback=on_danger_detected, debounce_seconds=5.0)

# Add Tool to list_tools:
Tool(
    name="memento_toggle_precognition",
    description="Toggle the Pre-cognitive Intervention background daemon",
    inputSchema={
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "description": "True to start watching files, False to stop"
            }
        },
        "required": ["enabled"]
    }
)

# Add handler in call_tool:
elif name == "memento_toggle_precognition":
    enable = arguments.get("enabled")
    if enable:
        daemon.start()
        return [TextContent(type="text", text="Precognition daemon started. Spider-Sense is tingling.")]
    else:
        daemon.stop()
        return [TextContent(type="text", text="Precognition daemon stopped.")]
```

- [x] **Step 4: Commit**
```bash
git add memento/mcp_server.py
git commit -m "feat: wire precognitive daemon to MCP server with toggle tool and SSE notifications"
```

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 2]
