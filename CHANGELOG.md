# Changelog

All notable changes to Memento are documented here.

## [0.3.1] — 2026-05-06

### Fixed
- Deprecated tools are now hidden from the MCP tool list. Clients see 14 active tools instead of 73.

## [0.3.0] — 2026-05-06

### Breaking Change — Unified Tool API
The MCP tool surface has been consolidated from 62 granular tools to 14 action-based unified tools. All old tools remain functional but are marked `[DEPRECATED]` and hidden from the tool list.

New unified tools:
- `memento_project` — project state and goals (replaces 6 tools)
- `memento_session` — session management (replaces 5 tools)
- `memento_graph` — Project Memory Graph (replaces 5 tools)
- `memento_search` — unified search with basic/advanced/explain modes (replaces 3 tools)
- `memento_remember` — memory write operations (replaces 5 tools)
- `memento_configure` — all configuration (replaces 9 tools)
- `memento_cognitive` — cognitive engine (replaces 4 tools)
- `memento_health` — diagnostics (replaces 9 tools)
- `memento_coercion` — Active Coercion CRUD (replaces 7 tools)
- `memento_kg` — Knowledge Graph operations (replaces 4 tools)
- `memento_notifications` — notification management (replaces 3 tools)

### Added
- **Auto-resume**: L1 working memory automatically restores from previous session checkpoint.
- **Project State Graph**: Structured storage for vision, milestones, blockers, tech_debt, decisions.
- **Project Memory Graph**: Semantic entity-relationship graph with impact analysis.
- **Goal-driven middleware**: Lightweight per-tool-call goal alignment check.
- **Session progress report**: Periodic evaluation of goal coverage during sessions.
- **Session diff**: Delta computation between current and previous session snapshots.
- **Project state in handoff**: Checkpoints include project state summary.

## [0.2.0] — 2026-04-26

### Added
- Autonomous agent with four levels (off, passive, active, autonomous).
- Cognitive engine with dream synthesis, spider-sense warnings, task generation.
- Active Coercion system with deterministic regex/tree-sitter rules.
- Consolidation engine for memory deduplication.
- Knowledge Graph auto-extraction.
- Predictive cache for proactive context warming.
- Quality metrics and relevance tracking.
- Cross-workspace memory sharing.
- Notification system.
- Session management with checkpoints and handoff prompts.
- vNext retrieval pipeline with multi-lane routing.
- Workspace isolation via `MEMENTO_DIR` and dynamic router.
- CLI: `memento capture --auto` and `memento search`.

## [0.1.0] — 2026-04-13

### Added
- Initial release.
- SQLite FTS5 + vector embedding hybrid search with RRF.
- Tri-State Goal Enforcer (L1, L2, L3).
- MCP server with stdio transport.
- Basic memory add/search via MCP.
