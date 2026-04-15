<div align="center">
  <img src="https://coreva-normal.trae.ai/api/ide/v1/text_to_image?prompt=A%20minimalist%2C%20enterprise-grade%20vector%20logo%20for%20an%20AI%20memory%20system%20called%20%27Memento%27.%20The%20design%20should%20be%20clean%2C%20monochromatic%20%28black%20and%20white%20or%20subtle%20grayscale%29%2C%20resembling%20Vercel%20or%20Next.js%20aesthetics.%20It%20should%20subtly%20hint%20at%20a%20neural%20graph%2C%20a%20node%20network%2C%20or%20an%20abstract%20brain%20structure%2C%20but%20remain%20highly%20geometric%20and%20professional.%20No%20text%20in%20the%20image%2C%20just%20the%20icon.&image_size=landscape_16_9" alt="Memento Logo" width="100%">

  <h1>Memento</h1>
  <p><strong>The Autonomous Nervous System for AI Agents</strong></p>

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

### 4. 🕸️ Dynamic Workspace Router
Zero-config multi-tenant isolation. Memento automatically detects which project repository the AI is currently working on and routes the memory/database to the correct `.memento/` folder. No more context bleeding between your Frontend and Backend projects.

---

## 🚀 Installation

You can install Memento globally via `uv` (recommended) or standard `pip`.

```bash
# Clone the repository
git clone https://github.com/yourusername/Memento.git
cd Memento

# Install dependencies and sync lockfile
uv sync

# Run the MCP Server
uv run memento-mcp
```

## 🛠️ MCP Configuration (Cursor / Trae / Claude)

Add Memento to your `mcp.json` or IDE configuration. Thanks to the Dynamic Workspace Router, you only need to configure it **once globally**:

```json
{
  "mcpServers": {
    "memento": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/Memento",
        "run",
        "memento-mcp"
      ],
      "env": {
        "OPENAI_API_KEY": "your-api-key-here",
        "OPENAI_BASE_URL": "https://api.openai.com/v1",
        "MEM0_MODEL": "gpt-4o-mini"
      }
    }
  }
}
```

## 🧠 Using Memento

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