# Dynamic Workspace Router (Zero-Config MCP)

## Overview
Transform the Memento MCP server from a single-workspace global process into a multi-tenant dynamic router. This allows users to install Memento globally in their IDE (like Trae or Claude Desktop) without needing to configure `.trae/mcp.json` in every project. The server will dynamically load the correct SQLite database and enforcement rules based on the `workspace_root` provided in each tool call.

## Architecture

### 1. Tool Schema Modifications
Every tool in `mcp_server.py` will receive a new REQUIRED parameter:
```json
"workspace_root": {
    "type": "string",
    "description": "MANDATORY: The absolute path of the current project/workspace root."
}
```
Because AI agents are aware of their working directory, they will automatically populate this field correctly on every invocation.

### 2. State Management (`WorkspaceContext`)
We will remove the global `provider`, `cognitive_engine`, and `ENFORCEMENT_CONFIG`. Instead, we will introduce a `WorkspaceContext` class and a `ContextManager` cache:

```python
class WorkspaceContext:
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.db_path = os.path.join(workspace_root, ".memento", "neurograph_memory.db")
        self.provider = NeuroGraphProvider(db_path=self.db_path)
        self.cognitive_engine = CognitiveEngine(self.provider)
        self.enforcement_config = self.load_enforcement_config()
        self.daemon = None # Managed separately or initialized on demand
```

A global dictionary `_contexts: dict[str, WorkspaceContext]` will cache these instances so SQLite connections and rules aren't reloaded on every single tool call.

### 3. Tool Execution Flow
Inside `call_tool(name: str, arguments: dict)`:
1. Extract `workspace_root` from `arguments`.
2. Fallback to `os.getcwd()` if missing (for legacy or CLI usage).
3. Retrieve or create the `WorkspaceContext` for that root.
4. Execute the tool logic using the specific `ctx.provider` and `ctx.cognitive_engine`.

### 4. Edge Cases
- **UI Server**: Since the UI server binds to a port, it's tricky to run multiple. We can either start one UI server per workspace on dynamic ports, or make the UI server multi-tenant. For this iteration, we will disable the global UI auto-start or bind it to the first loaded workspace.
- **Daemon (PreCognitiveDaemon)**: The daemon uses `watchdog`. We will instantiate one daemon per `WorkspaceContext` when it's first loaded, ensuring it only watches that specific `workspace_root`.

## Success Criteria
1. The global Trae `mcp.json` configuration can be used for all projects.
2. Calling `memento_add_memory` from NEXUS-LM writes to `NEXUS-LM/.memento/neurograph_memory.db`.
3. Calling `memento_add_memory` from Zeronode writes to `Zeronode/.memento/neurograph_memory.db`.
4. No "bleed-over" of memories between projects.