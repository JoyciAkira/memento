<div align="center">
  <img src="assets/memento-logo.svg" alt="Memento Logo" width="100%">

  <h1>Memento</h1>
  <p><strong>The Autonomous Nervous System for AI Agents</strong></p>

  [![PyPI version](https://img.shields.io/pypi/v/memento-mcp.svg)](https://pypi.org/project/memento-mcp/)
  [![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
  [![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
  [![MCP Protocol](https://img.shields.io/badge/MCP-Ready-success.svg)](https://modelcontextprotocol.io/)
</div>

---

Memento is a local-first, open-source MCP middleware that gives your AI agents (Cursor, Claude Desktop, Trae, etc.) persistent memory, proactive goal enforcement, and autonomous intelligence — all running on a zero-cost **SQLite temporal graph** with **Reciprocal Rank Fusion (RRF)** retrieval.

No cloud databases. No API calls for storage. Everything stays on your machine.

---

## Architecture

### Temporal Graph Memory (RRF)
Built on **SQLite FTS5** (full-text search) and **cosine similarity** (vector embeddings). Fuses keyword matches and semantic meaning via **Reciprocal Rank Fusion**. WAL-mode enabled for concurrency.

### Tri-State Goal Enforcer
Keep your AI aligned with project objectives at three escalation levels:
- **Level 1 — Context Injection**: Automatically injects active goals into every search result. Active by default.
- **Level 2 — Strict Mentor**: Forces the AI to submit code/plans for goal alignment evaluation via LLM.
- **Level 3 — Daemon Push**: File-watcher monitors your workspace and proactively flags goal drift.

### Active Coercion (Code Immune System)
Deterministic regex/tree-sitter rules that block anti-patterns at commit time and in the IDE. 100% deterministic — zero LLM hallucination risk during enforcement.

### Autonomous Agent
Background cognitive loop with four levels:
- **off**: No background behavior (default).
- **passive**: Observe health and patterns every 5 min. No modifications.
- **active**: Consolidate memories, extract KG, warm caches, detect anomalies every 2 min.
- **autonomous**: All of the above plus dream synthesis, goal drift detection, task generation, health reports every 1 min.

### Workspace Isolation
Each project gets its own `.memento/` directory with an isolated SQLite database. No context bleeding between projects. Configure via `MEMENTO_DIR` or per-project `.cursor/mcp.json`.

### Session Continuity
- Auto-checkpoints every 25 tool calls with full L1 working memory snapshot.
- Auto-resume restores goals and context from the previous session.
- LLM-agnostic handoff prompts for session transfer between agents.

### Project Memory Graph
Semantic entity-relationship graph on top of the Knowledge Graph. Track files, components, decisions, and their dependencies. Impact analysis shows what breaks when you change something.

---

## Unified Tool API (v0.3.x)

Memento exposes **14 action-based tools** via MCP. Each tool uses an `action` parameter instead of separate tools per operation:

| Tool | Actions | Purpose |
|------|---------|---------|
| `memento` | (main router) | Primary proactive memory interface |
| `memento_project` | `set_state`, `get_state`, `delete_state`, `set_goals`, `list_goals`, `summary` | Vision, milestones, blockers, goals |
| `memento_session` | `begin`, `resume`, `handoff`, `status`, `list` | Session lifecycle and handoff |
| `memento_graph` | `add_entity`, `add_relation`, `query`, `impact`, `summary` | Project Memory Graph |
| `memento_search` | `basic`, `advanced`, `explain` | FTS, vNext pipeline, routing trace |
| `memento_remember` | `add`, `consolidate`, `share`, `evaluate`, `hit` | Memory write operations |
| `memento_configure` | `enforcement`, `coercion`, `daemon`, `autonomy`, `consolidation_scheduler`, `kg_scheduler`, `dependency_tracker`, `superpowers`, `access` | All configuration |
| `memento_cognitive` | `dream`, `align`, `warnings`, `tasks` | Cognitive engine operations |
| `memento_health` | `status`, `health`, `memory`, `kg`, `quality`, `relevance`, `cache`, `explain` | Diagnostics |
| `memento_coercion` | `list_presets`, `apply_preset`, `list_rules`, `add_rule`, `remove_rule`, `install_hooks` | Active Coercion management |
| `memento_kg` | `extract`, `health`, `cross_workspace_stats` | Knowledge Graph operations |
| `memento_notifications` | `configure`, `list`, `dismiss` | Proactive notifications |
| `memento_audit_dependencies` | (standalone) | Dependency audit |
| `memento_migrate_workspace_memories` | (standalone) | Workspace memory migration |

---

## Quick Start

### Install

```bash
pip install memento-mcp
```

Or run without installing:

```bash
uvx memento-mcp
```

### Configure (Cursor / Claude Desktop / Trae)

Add to your global `mcp.json` (e.g. `~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "memento": {
      "command": "memento-mcp",
      "env": {
        "OPENAI_API_KEY": "your-api-key",
        "OPENAI_BASE_URL": "https://api.openai.com/v1",
        "MEM0_MODEL": "openai/gpt-4o-mini"
      }
    }
  }
}
```

For **per-project workspace isolation**, add to `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "memento": {
      "command": "memento-mcp",
      "env": {
        "OPENAI_API_KEY": "your-api-key",
        "OPENAI_BASE_URL": "https://api.openai.com/v1",
        "MEM0_MODEL": "openai/gpt-4o-mini",
        "MEMENTO_DIR": "${workspaceFolder}"
      }
    }
  }
}
```

Add `.cursor/` to your `.gitignore` to avoid committing API keys.

### Verify

```bash
memento-mcp --help
memento --help
```

<details>
<summary>Running without OpenAI (offline / testing)</summary>

Set `MEMENTO_EMBEDDING_BACKEND=none` to disable embeddings. Memento falls back to FTS5-only search — no API key needed.

```bash
MEMENTO_EMBEDDING_BACKEND=none memento-mcp
```

</details>

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Required for embeddings and cognitive features |
| `OPENAI_BASE_URL` | Optional OpenAI-compatible endpoint (e.g. OpenRouter) |
| `MEM0_MODEL` | LLM model for cognitive features |
| `MEM0_EMBEDDING_MODEL` | Embeddings model for hybrid search |
| `MEMENTO_EMBEDDING_BACKEND` | Set to `none` for FTS5-only (no API key) |
| `MEMENTO_DIR` | Workspace root for `.memento/` state |
| `MEMENTO_UI` | Enable local web UI (`1`/`true`) |
| `MEMENTO_UI_PORT` | Local UI port (default `8089`) |
| `MEMENTO_HANDOFF_AUTO_CHECKPOINT_EVERY_N_EVENTS` | Auto-checkpoint frequency (default `25`) |

---

## CLI Usage

Memento works from the terminal too:

```bash
# Auto-capture git context as a memory
memento capture --auto

# Save a free-form note
memento capture --text "Resolved auth timeout by increasing JWT expiry"

# Search memories
memento search "how did I fix the promise bug"

# Show workspace status
memento status
```

---

## How Proactivity Works

Memento operates at two levels:

### Always-on (zero configuration)
- **Goal awareness**: Every tool call is checked against active goals. If work drifts, a warning is appended.
- **Auto-resume**: L1 working memory (goals, context) restores from the previous session's checkpoint.
- **Auto-checkpoint**: Every 25 events, a full session snapshot is saved with project state and handoff prompt.
- **Session diff**: Each checkpoint computes the delta from the previous session (goals changed, files touched).

### Activatable (via `memento_configure`)
- **L2 enforcement**: Goal alignment checks via LLM on explicit request.
- **L3 daemon**: File-watcher with proactive goal drift notifications.
- **Autonomous agent**: Background consolidation, KG extraction, dream synthesis, task generation.
- **Active coercion**: Deterministic code pattern enforcement.
- **Consolidation/KG schedulers**: Background deduplication and knowledge extraction.

Example activation sequence:

```
memento_project(action="set_goals", goals=["Implement auth flow", "Refactor DB layer"])
memento_configure(action="enforcement", level="level2", enabled=true)
memento_configure(action="consolidation_scheduler", enabled=true, interval_minutes=30)
memento_configure(action="autonomy", level="active")
```

---

## License

Memento is released under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. If you modify Memento and offer it as a network service, you must release your modified source code under the same license.

See [LICENSE](LICENSE) for details.
