# Dynamic Workspace Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform Memento MCP server into a multi-tenant dynamic router that automatically isolates SQLite databases and configurations based on the `workspace_root` provided in each tool call.

**Architecture:** Introduce a `WorkspaceContext` class that lazily initializes `NeuroGraphProvider`, `CognitiveEngine`, and `ENFORCEMENT_CONFIG` for a given workspace root. Update all tool schemas to require `workspace_root` and route execution to the appropriate context.

**Tech Stack:** Python, MCP SDK, SQLite.

---

### Task 1: Create the WorkspaceContext Manager

**Files:**
- Create: `memento/workspace_context.py`
- Modify: `tests/test_workspace_isolation.py` (new test file)

- [ ] **Step 1: Write the failing test**

Create `tests/test_workspace_isolation.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workspace_isolation.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'memento.workspace_context')

- [ ] **Step 3: Write minimal implementation**

Create `memento/workspace_context.py`:

```python
import os
import json
import logging
from typing import Dict
from memento.provider import NeuroGraphProvider
from memento.cognitive_engine import CognitiveEngine
from memento.enforcement_rules import extract_goal_enforcer_config_from_rules_md, upsert_goal_enforcer_block

logger = logging.getLogger("memento-workspace")

class WorkspaceContext:
    def __init__(self, workspace_root: str):
        self.workspace_root = os.path.abspath(workspace_root)
        
        # Ensure .memento directory exists
        self.memento_dir = os.path.join(self.workspace_root, ".memento")
        os.makedirs(self.memento_dir, exist_ok=True)
        
        self.db_path = os.path.join(self.memento_dir, "neurograph_memory.db")
        self.provider = NeuroGraphProvider(db_path=self.db_path)
        self.cognitive_engine = CognitiveEngine(self.provider)
        
        self.enforcement_config = {
            "level1": False,
            "level2": False,
            "level3": False,
        }
        self.load_enforcement_config()
        self.daemon = None

    def load_enforcement_config(self):
        settings_path = os.path.join(self.memento_dir, "settings.json")
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r") as f:
                    data = json.load(f)
                    config = data.get("enforcement_config", {})
                    self.enforcement_config.update(config)
            except Exception as e:
                logger.error(f"Failed to load config from {settings_path}: {e}")

        rules_path = os.path.join(self.workspace_root, ".memento.rules.md")
        if os.path.exists(rules_path):
            try:
                with open(rules_path, "r") as f:
                    rules_content = f.read()
                extracted = extract_goal_enforcer_config_from_rules_md(rules_content)
                if extracted is not None:
                    self.enforcement_config.update(extracted)
            except Exception as e:
                logger.error(f"Failed to load rules from {rules_path}: {e}")

    def save_enforcement_config(self):
        settings_path = os.path.join(self.memento_dir, "settings.json")
        try:
            data = {}
            if os.path.exists(settings_path):
                with open(settings_path, "r") as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        pass
            data["enforcement_config"] = self.enforcement_config
            with open(settings_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save config to {settings_path}: {e}")

        rules_path = os.path.join(self.workspace_root, ".memento.rules.md")
        try:
            rules_content = ""
            if os.path.exists(rules_path):
                with open(rules_path, "r") as f:
                    rules_content = f.read()
            new_content = upsert_goal_enforcer_block(rules_content, self.enforcement_config)
            with open(rules_path, "w") as f:
                f.write(new_content)
        except Exception as e:
            logger.error(f"Failed to save rules to {rules_path}: {e}")

_contexts: Dict[str, WorkspaceContext] = {}

def get_workspace_context(workspace_root: str) -> WorkspaceContext:
    if not workspace_root:
        workspace_root = os.getcwd()
    abs_root = os.path.abspath(workspace_root)
    if abs_root not in _contexts:
        _contexts[abs_root] = WorkspaceContext(abs_root)
    return _contexts[abs_root]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workspace_isolation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add memento/workspace_context.py tests/test_workspace_isolation.py
git commit -m "feat: implement WorkspaceContext for dynamic multi-tenant isolation"
```

---

### Task 2: Refactor MCP Server to use WorkspaceContext

**Files:**
- Modify: `memento/mcp_server.py`
- Modify: `tests/test_mcp_daemon.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_mcp_daemon.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mcp_daemon.py::test_mcp_server_dynamic_workspace_routing -v`
Expected: FAIL (memento_status doesn't accept workspace_root yet, or returns global status).

- [ ] **Step 3: Update tool schemas and routing logic**

In `memento/mcp_server.py`:
1. Remove global `provider`, `cognitive_engine`, `ENFORCEMENT_CONFIG`, `workspace`, `daemon`, `load_enforcement_config`, `save_enforcement_config`.
2. Import `get_workspace_context`: `from memento.workspace_context import get_workspace_context`
3. Update `get_active_goals` to accept `ctx: WorkspaceContext`:
```python
def get_active_goals(ctx, max_goals: int = 3, context: str = None) -> str:
    try:
        search_query = f"obiettivo goal per il contesto: {context}" if context else "obiettivo goal"
        res = ctx.provider.search(search_query, user_id="default")
        results = res.get("results", []) if isinstance(res, dict) else res
        if not isinstance(results, list): return ""
        goals = []
        for r in results[:max_goals]:
            if not isinstance(r, dict): continue
            memory = r.get("memory")
            if isinstance(memory, str) and memory.strip():
                goals.append(memory.strip())
        if not goals: return ""
        formatted = "\n- ".join(goals)
        return f"[ACTIVE GOALS]\n- {formatted}\n\n"
    except Exception:
        return ""
```

4. Update `on_danger_detected` to be a method or factory that captures `ctx`. Actually, we can move daemon initialization to `WorkspaceContext` later, for now we will disable the global daemon auto-start or wrap it. For this step, let's just comment out `daemon = PreCognitiveDaemon(...)` globally.

5. Update `list_tools()` to add `workspace_root` to ALL tools:
```python
        # Add to properties of EVERY tool:
        "workspace_root": {
            "type": "string",
            "description": "MANDATORY: The absolute path of the current project/workspace root."
        }
        # Add to 'required' array of EVERY tool.
```

6. Update `call_tool()` routing:
```python
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    workspace_root = arguments.get("workspace_root", os.getcwd())
    ctx = get_workspace_context(workspace_root)
    
    if name == "memento_status":
        status_lines = []
        status_lines.append("🤖 Memento MCP Server Status")
        status_lines.append("============================")
        status_lines.append("\n[Workspace]")
        status_lines.append(f"- {ctx.workspace_root}")
        
        settings_path = os.path.join(ctx.workspace_root, ".memento", "settings.json")
        rules_path = os.path.join(ctx.workspace_root, ".memento.rules.md")
        status_lines.append("\n[Settings]")
        status_lines.append(f"- settings.json: {settings_path} ({'present' if os.path.exists(settings_path) else 'missing'})")
        status_lines.append(f"- .memento.rules.md: {rules_path} ({'present' if os.path.exists(rules_path) else 'missing'})")
        
        status_lines.append("\n[Enforcement Config]")
        for k, v in ctx.enforcement_config.items():
            status_lines.append(f"- {k}: {'Enabled' if v else 'Disabled'}")
            
        db_path = getattr(ctx.provider, "db_path", "Unknown")
        status_lines.append("\n[Database]")
        status_lines.append(f"- path: {db_path}")
        status_lines.append(f"- present: {'yes' if isinstance(db_path, str) and os.path.exists(db_path) else 'no'}")
        
        goals = get_active_goals(ctx)
        if goals:
            status_lines.append("\n" + goals.strip())
        else:
            status_lines.append("\n[ACTIVE GOALS]\n- Nessun obiettivo attivo trovato.")
            
        return [TextContent(type="text", text="\n".join(status_lines))]

    elif name == "memento_configure_enforcement":
        if "level1" in arguments: ctx.enforcement_config["level1"] = arguments["level1"]
        if "level2" in arguments: ctx.enforcement_config["level2"] = arguments["level2"]
        if "level3" in arguments: ctx.enforcement_config["level3"] = arguments["level3"]
        ctx.save_enforcement_config()
        return [TextContent(type="text", text=f"Enforcement config aggiornata per il workspace {ctx.workspace_root}: {json.dumps(ctx.enforcement_config)}")]
    
    elif name == "memento_migrate_workspace_memories":
        # Keep existing logic, just use ctx.workspace_root if report_path is missing
        source_db_path = arguments.get("source_db_path")
        workspace_roots = arguments.get("workspace_roots")
        report_path = arguments.get("report_path") or os.path.join(ctx.workspace_root, ".memento", "migration_report.json")
        # ... rest of the code ...
        
    elif name == "memento":
        # Update references to use ctx.provider, ctx.cognitive_engine, ctx.enforcement_config
        # ...
```
*(You will need to systematically replace `provider`, `cognitive_engine`, `ENFORCEMENT_CONFIG`, and `workspace` with `ctx.provider`, `ctx.cognitive_engine`, `ctx.enforcement_config`, and `ctx.workspace_root` throughout `call_tool`)*

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_mcp_daemon.py -v`
Fix any failing tests that relied on the global state. Many tests might need `workspace_root` added to their empty `{}` tool call arguments.

- [ ] **Step 5: Commit**

```bash
git add memento/mcp_server.py tests/test_mcp_daemon.py
git commit -m "refactor: transition MCP server to dynamic WorkspaceContext routing"
```

---

### Task 3: Handle Daemon and UI Server for Multi-Tenant

**Files:**
- Modify: `memento/workspace_context.py`
- Modify: `memento/mcp_server.py`

- [ ] **Step 1: Write the minimal implementation for Daemon lifecycle**

In `memento/workspace_context.py`, add the daemon initialization to the `WorkspaceContext` class, lazily created when toggled:

```python
    def toggle_daemon(self, enabled: bool, callback) -> bool:
        if enabled:
            if not self.daemon or not self.daemon.is_running:
                from memento.daemon import PreCognitiveDaemon
                self.daemon = PreCognitiveDaemon(workspace_path=self.workspace_root, callback=callback, debounce_seconds=5.0)
                self.daemon.start()
            return True
        else:
            if self.daemon and self.daemon.is_running:
                self.daemon.stop()
            return False
```

In `memento/mcp_server.py`:
Update `memento_toggle_precognition`:
```python
    elif name == "memento_toggle_precognition":
        enabled = arguments.get("enabled", False)
        
        async def _local_callback(filepath, content):
            # Similar to old on_danger_detected but using ctx
            warning = ctx.cognitive_engine.evaluate_raw_context(content, filepath=filepath)
            deviation = ""
            if ctx.enforcement_config.get("level3"):
                alignment = ctx.cognitive_engine.check_goal_alignment(content)
                if "❌ BOCCIATO" in alignment:
                    deviation = alignment
            # ... send notification logic ...

        is_running = ctx.toggle_daemon(enabled, _local_callback)
        state_str = "AVVIATO" if is_running else "FERMATO"
        return [TextContent(type="text", text=f"Daemon Pre-cognitivo {state_str} per il workspace {ctx.workspace_root}.")]
```

For the UI Server, we will disable the global auto-start in `mcp_server.py` and remove it from `memento_status` for now (or report it as unsupported in multi-tenant mode until we refactor it).

- [ ] **Step 2: Update tests and run**

Run: `uv run pytest tests/ -v`

- [ ] **Step 3: Commit**

```bash
git add memento/workspace_context.py memento/mcp_server.py
git commit -m "feat: scope precognitive daemon to specific workspace contexts"
```