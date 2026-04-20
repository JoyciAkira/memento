<div align="center">
  <img src="assets/memento-logo.svg" alt="Memento Logo" width="100%">

  <h1>Memento</h1>
  <p><strong>The Autonomous Nervous System for AI Agents</strong></p>

  [![Tests](https://github.com/JoyciAkira/memento/actions/workflows/ci.yml/badge.svg)](https://github.com/JoyciAkira/memento/actions/workflows/ci.yml)
  [![PyPI version](https://img.shields.io/pypi/v/memento-mcp.svg)](https://pypi.org/project/memento-mcp/)
  [![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
  [![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
  [![MCP Protocol](https://img.shields.io/badge/MCP-Ready-success.svg)](https://modelcontextprotocol.io/)
</div>

---

Memento is a revolutionary, open-source middleware that acts as the "Autonomous Nervous System" for your AI agents (like Cursor, Claude Desktop, or Trae). 

While most agentic memory systems rely on expensive, cloud-hosted graph databases, Memento empowers your local agents with a powerful, zero-cost, **PageRank-optimized SQLite temporal graph** and **Reciprocal Rank Fusion (RRF)** for perfect semantic retrieval.

But Memento goes **Beyond Memory**. It transforms your AI from a reactive assistant into a proactive, context-aware, and strictly aligned pair-programmer.

## 🌟 Enterprise-Grade Architecture

### 1. 🧠 Hybrid Search Engine (RRF)
A zero-cost, local-first temporal graph memory provider optimized for AI.
- Built on **SQLite FTS5** (Full-Text Search) and **Cosine Similarity** (Vector Embeddings).
- Fuses exact keyword matches and semantic meaning using **Reciprocal Rank Fusion (RRF)**.
- **Write-Ahead Logging (WAL)** enabled for extreme concurrency without database locking.
- Completely private and runs locally.

### 2. 🛡️ Active Coercion (The Code Immune System)
A deterministic, regex/AST-based engine that physically prevents the AI (or you) from introducing known anti-patterns.
- **Pre-commit Hook Integration**: Automatically blocks `git commit` if the code violates architectural rules.
- **IDE Runtime Notifications**: Sends push notifications directly to the AI if it generates bad code.
- **100% Deterministic**: Zero LLM hallucinations during enforcement. Bypassable via `// memento-override` tokens.

### 3. 🎯 Tri-State Goal Enforcer
Keep your AI strictly aligned with your project's core objectives:
- **Level 1 (Context Injection)**: Seamlessly injects active goals into the AI's context on every memory retrieval.
- **Level 2 (Strict Mentor Checkpoint)**: Forces the AI to submit code or plans for a strict evaluation against the project's core goals.
- **Level 3 (Proactive Autonomy)**: The AI is instructed via MCP to autonomously query Memento *before* writing any code.

**Goal Enforcer MCP Tools:**

| Tool | Description |
|------|-------------|
| `memento_set_goals` | Set active goals (replace or append mode) |
| `memento_list_goals` | List goals with optional context and active-only filters |
| `memento_check_goal_alignment` | L2 gate — submit code/plans for strict goal evaluation |
| `memento_configure_enforcement` | Toggle L1/L2/L3 enforcement levels |

### 4. 🕸️ Dynamic Workspace Router
Zero-config multi-tenant isolation. Memento automatically detects which project repository the AI is currently working on and routes the memory/database to the correct `.memento/` folder. No more context bleeding between your Frontend and Backend projects.

---

## 🧬 The Seven Superpowers

Memento's cognitive layer goes beyond passive memory. Seven autonomous superpowers transform it into a self-improving, proactive system:

### SP1: Auto-Consolidation
Automatically detects semantically similar memories and merges them into enriched, deduplicated entries. Uses cosine similarity clustering with sentence-level text fusion.
- `memento_consolidate_memories` — run a full consolidation cycle
- `memento_toggle_consolidation_scheduler` — start/stop background scheduler

### SP2: KG Auto-Extraction
Automatically extracts entities and relationships from memories and populates a temporal knowledge graph using LLM analysis.
- `memento_extract_kg` — extract entities and triples from unprocessed memories
- `memento_toggle_kg_extraction_scheduler` — start/stop background scheduler

### SP3: Relevance Tracking
Tracks memory access patterns with hit counting, temporal boosting, and exponential time decay. Frequently accessed recent memories rank higher.
- `memento_get_relevance_stats` — hot/cold distribution, hit counts, decay metrics
- `memento_record_memory_hit` — manually boost specific memories

### SP4: Predictive Cache
Pre-warms an in-memory cache of related memories before starting work. Proactive context injection that anticipates what the AI will need.
- `memento_warm_predictive_cache` — warm cache with context text
- `memento_get_predictive_cache_stats` — hit rate, cache size, TTL info

### SP5: Self-Evaluation Loop
Computes memory health scores (0-100) based on freshness, coverage, redundancy, and size. Identifies stale and orphan memories for cleanup.
- `memento_get_quality_report` — full quality report with health score
- `memento_record_quality_evaluation` — rate memory quality (0-1)
- `memento_system_health` — comprehensive system health dashboard
- `memento_kg_health` — knowledge graph entity/triple metrics

### SP6: Cross-Workspace Sharing
Share memories between different Memento workspaces. Enables cross-project context flow with directional sync tracking.
- `memento_share_memory_to_workspace` — share a memory to another project
- `memento_get_cross_workspace_stats` — sync statistics

### SP7: Real-Time Notifications
Proactive alerts about relevant context changes, memory events, and high-relevance discoveries. Configurable topics and confidence thresholds.
- `memento_configure_notifications` — enable/disable, set topics and confidence
- `memento_get_pending_notifications` — retrieve pending alerts
- `memento_dismiss_notification` — dismiss an alert

---

## 🚀 Quick Start

Choose your preferred installation method:

### Option A: `pip install` (Recommended)

```bash
pip install memento-mcp
```

That's it. The `memento-mcp` and `memento` commands are now available globally.

### Option B: `uvx` (Zero-install)

Run Memento instantly without installing anything permanently:

```bash
uvx memento-mcp
```

### Option C: `pip install` from GitHub (Latest dev)

```bash
pip install git+https://github.com/JoyciAkira/memento.git
```

### Option D: Clone for development

```bash
git clone https://github.com/JoyciAkira/memento.git
cd memento
uv sync
```

Verify any installation:

```bash
python -c "import memento; print(memento.__version__)"
memento-mcp --help
memento --help
```

<details>
<summary>📝 Running without OpenAI (offline / testing)</summary>

Set `MEMENTO_EMBEDDING_BACKEND=none` to disable embeddings entirely. Memento falls back to FTS5-only full-text search — no API key needed.

```bash
MEMENTO_EMBEDDING_BACKEND=none memento-mcp
```

</details>

---

## 🛠️ MCP Configuration (Cursor / Trae / Claude)

Add Memento to your `mcp.json` or IDE configuration. Thanks to the Dynamic Workspace Router, you only need to configure it **once globally**.

### Config for `pip` / `uvx` install (Recommended)

No local clone needed. Just use the installed command directly:

```json
{
  "mcpServers": {
    "memento": {
      "command": "memento-mcp",
      "env": {
        "OPENAI_API_KEY": "your-api-key-here",
        "OPENAI_BASE_URL": "https://api.openai.com/v1",
        "MEM0_MODEL": "openai/gpt-4o-mini",
        "MEM0_EMBEDDING_MODEL": "text-embedding-3-small"
      }
    }
  }
}
```

### Config for local clone (development)

```json
{
  "mcpServers": {
    "memento": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/memento",
        "run",
        "memento-mcp"
      ],
      "env": {
        "OPENAI_API_KEY": "your-api-key-here",
        "OPENAI_BASE_URL": "https://api.openai.com/v1",
        "MEM0_MODEL": "openai/gpt-4o-mini",
        "MEM0_EMBEDDING_MODEL": "text-embedding-3-small"
      }
    }
  }
}
```

### Environment variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Required for embeddings and goal checks |
| `OPENAI_BASE_URL` | Optional OpenAI-compatible endpoint |
| `MEM0_MODEL` | LLM used for cognitive features |
| `MEM0_EMBEDDING_MODEL` | Embeddings model used by the hybrid memory provider |
| `MEMENTO_EMBEDDING_BACKEND` | Set to `none` to disable embeddings (FTS5-only fallback) |
| `MEMENTO_DIR` | Workspace root used for routing `.memento/` state |
| `MEMENTO_UI` | Enable local UI (`1`/`true`) |
| `MEMENTO_UI_PORT` | Local UI port (default `8089`) |

## ⌨️ CLI Usage

Memento also works directly from the terminal — no AI agent required.

```bash
# Auto-capture git context (branch, recent commits, diff stats) as a memory
memento capture --auto

# Save a free-form note
memento capture --text "Resolved the auth timeout by increasing JWT expiry to 1h"

# Combine auto context + custom note
memento capture --auto --text "Refactored the retry logic after the incident"

# Search your memories
memento search "how did I fix the promise bug"

# Show workspace status
memento status
```

The `capture --auto` command extracts the current git branch, last 5 commits, and staged/unstaged diff stats — saving a snapshot of your work context with zero friction. Useful in git hooks, CI scripts, or just as a quick terminal habit.

## 🧠 Using Memento (via MCP)

Memento exposes a suite of MCP tools, but the primary entrypoint is fully autonomous. 

### The Proactive Subconscious
The primary `memento` tool is configured with a **Level 3 Proactive Autonomy** prompt. You don't need to say "Memento, remember this". The AI is strictly instructed to query Memento *before* executing any task, formulating its own search queries to retrieve your architectural rules, past bugs, and context.

### Managing Active Coercion
You can manage the Code Immune System directly via chat using the exposed MCP tools:
- `memento_toggle_active_coercion`
- `memento_install_git_hooks`
- `memento_add_active_coercion_rule`
- `memento_list_active_coercion_rules`

---

## ⚖️ License

Memento is released under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. 
This ensures that Memento remains free and open-source forever. If you modify Memento and offer it as a service over a network (e.g., as a Cloud SaaS), you **must** release your modified source code under the same AGPL-3.0 license. 

See the [LICENSE](LICENSE) file for more details.
