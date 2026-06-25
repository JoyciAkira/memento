# Changelog

All notable changes to Memento are documented here.

## [1.0.0] — 2026-06-24

### G001 — Audit Cleanup
- `registry.execute()`: `PermissionError` caught and returned as structured `TextContent`
- `provider.py`: all env var reads consolidated through `settings` singleton (single source of truth)

### G002 — v0.6 Quality
- `provider.forget_decayed()`: soft-delete memories whose decay score < threshold after N days
- `knowledge_graph.add_causal_triple()`: typed causal predicates (`caused_by`, `fixed_by`, `introduced_by`, `blocked_by`, `depends_on`)
- `knowledge_graph.query_causal()`: filter triples by causal predicate
- `memento_health action=memory`: enriched with per-memory decay scores, healthy/degraded counts
- `memento_cognitive action=forget`: trigger `forget_decayed` via MCP
- `memento_kg action=add_causal/query_causal`: causal KG operations via MCP

### G003 — v0.7 Structured Ingestion
- `memento/git_ingestion.py`: `ingest_commit()` + `ingest_test_failure()` — structured L3/L2 memories with KG causal triples
- `memento_remember action=ingest_commit/ingest_test_failure`: MCP actions for structured ingestion
- `memento_audit_dependencies`: now populates KG with orphan/ghost dependency triples

### G004 — v0.8 Intent-aware Proactive Injection
- `_build_intent_phrase()`: maps `(tool, action)` pairs to natural language intent templates
- Replaces raw keyword concatenation with semantically rich intent phrases for better embedding recall

### G005 — v1.0 Federation
- `memento/federation.py`: `FederationServer` + `FederationClient` — Unix socket push notifications replace 30s WAL polling
- `MEMENTO_SHARED_KG_PATH`: share a single KG SQLite file across multiple workspaces
- `MEMENTO_FEDERATION_SOCKET`: enable push-based cross-agent notifications (first instance = server, others = clients)
- `provider.add()` broadcasts write events to all connected federation clients
- 19 env vars fully documented in README

## [0.5.0] — 2026-06-24

### Security
- **Prompt injection mitigation**: proactive context injection is now wrapped in `<!-- memento:proactive-context -->` delimiters and stripped of instruction-hijacking patterns
- **`.memento/` directory permissions**: created with `mode=0o700` (owner-only) to prevent local process snooping
- **Access manager enforcement**: proactive injection respects lockdown state
- **Extended redaction**: Anthropic key format (`sk-ant-api03-...`), DSNs (`postgres://user:pass@host`), `CLIENT_SECRET`, `DB_PASSWORD`, Bearer tokens

### Performance
- `datetime.now()` hoisted outside the decay loop (400× fewer calls per search)
- `MEMENTO_WRITE_SEARCH_TRACE` default flipped to `0` — JSON trace write disabled in production
- New index `idx_memory_meta_created_at_desc` for O(1) `MAX(created_at)` resolution (WAL watcher + migration v011)

### Added
- **KG retrieval lane**: fifth RRF lane — entity match in KG → source memory IDs → boosted in ranking (weight 0.8)
- **L1 importance wiring**: `MemoryGovernor.score()` signal now flows into `L1WorkingMemory.add(importance=...)` on every `provider.add()` call
- **Provider `close()`**: clean shutdown cancels the WAL watcher task and closes DB connections; guards against multiple watcher spawns
- **Settings `reload()`**: allows test isolation after `monkeypatch.setenv`
- **Startup warning**: logs warning when embedding backend resolves to `none`
- **Environment variables fully documented** in README (17 vars, with defaults)

### Fixed
- `test_tools_smoke.py`: added `action` payloads for all 12 unified tools
- `conftest.py`: autouse `_cleanup_workspace_contexts` fixture clears `_contexts` between tests; `settings.reload()` on each test setup/teardown

### Changed
- `_decay_score()` accepts optional `now: datetime` parameter to avoid repeated `datetime.now()` calls

## [0.4.0] — 2026-06-24

### Added
- **Temporal decay**: retrieval score = RRF × e^(−λ×age_days) per tier. Defaults: semantic λ=0.005 (~200d half-life), episodic λ=0.02 (~50d), working λ=0.05 (~14d). Configurable via `MEMENTO_DECAY_SEMANTIC/EPISODIC/WORKING`.
- **L1 LRU+importance eviction**: replaces FIFO with `last_accessed + 0.3×importance` eviction policy. High-importance memories survive longer in working memory.
- **Proactive context injection**: every tool call automatically prepends relevant memories to the response. Skip with `MEMENTO_PROACTIVE_INJECT=0`, tune with `MEMENTO_PROACTIVE_TOP_K` (default 3).
- **Cross-agent WAL watcher**: background task polls `memory_meta` every 30s to detect writes from other Memento instances sharing the same `MEMENTO_DIR`. Invalidates L1 cache on external write.

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
