# Changelog

All notable changes to this project will be documented in this file.

## [0.1.1] - 2026-04-17

### Security
- **CRITICAL**: Added regex timeout (2s) to Active Coercion engine to prevent ReDoS via crafted regex patterns
- **CRITICAL**: Added authorization check on coercion rule add/remove MCP tools (gated by `MEMENTO_RULE_CONFIRMATION` env var)
- **CRITICAL**: Added path traversal validation in pre-commit hook — paths with `..` component are rejected
- Added bearer token authentication to UI server (`MEMENTO_UI_AUTH_TOKEN` env var)
- Removed dummy API key `sk-dummy` — embedding backend now disables itself when no key is present
- Sanitized OpenAI error messages in CognitiveEngine to prevent API key leakage

### Performance
- Added migration v007 with performance indexes on embeddings, memory_meta, consolidation_log, and kg_extraction_log
- Replaced N+1 KG queries with batch `query_entities_batch()` method — single SQL query for all search results
- Added thread safety to KnowledgeGraph via `threading.Lock` on all write operations
- Centralized OpenAI client into `llm_client.py` singleton — eliminates duplicate client with conflicting defaults
- Added retry with exponential backoff for all OpenAI API calls (3 retries, configurable)

### Architecture
- Extracted `GoalStore` class from provider.py (~100 lines removed from the God Object)
- Extracted `math_utils.py` with shared `cosine_similarity()` — eliminated 4x duplication
- Extracted `llm_client.py` with centralized OpenAI client factory and retry logic
- Extracted `settings.py` with centralized Settings class for all env vars
- Added `memento.goal_store` module for first-class goal management

### Code Quality
- Fixed 17 silent `pass` blocks — replaced with `logger.debug()` for discoverable failures
- Narrowed exception handling in provider.py and cognitive_engine.py
- Fixed incorrect `Optional` type annotations in `knowledge_graph.py` and `provider.py`
- Standardized typing style to modern Python 3.10+ syntax across touched modules
- Added `_MAX_REGEX_LENGTH` validation (1024 chars) in Active Coercion rule normalization
- Added watchdog exclusion logging in daemon

### Testing
- Added `tests/conftest.py` with shared `tmp_workspace` fixture and `autouse` OpenAI disable
- Added `tests/test_redaction.py` — 6 tests for secret redaction patterns
- Added `tests/test_registry.py` — 3 tests for ToolRegistry register/execute/get_tools
- Added `tests/test_math_utils.py` — 8 tests for cosine_similarity edge cases
- Added `tests/test_llm_client.py` — 5 tests for retry logic classification
- Added `tests/test_goal_store.py` — 5 tests for GoalStore CRUD operations
- Added `tests/test_active_coercion_hook.py` — 3 tests for pre-commit hook enforcement
- Extended MCP coverage: `tests/mcp_contract_helpers.py`, `tests/test_mcp_tool_contracts.py` (offline trace + vNext JSON), stricter `tests/test_tools_smoke.py`, wider `test_b6_offline_mcp_tools_callable`; `benchmarks/run_benchmarks.py` includes the contracts file
