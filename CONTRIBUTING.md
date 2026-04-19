# Contributing to Memento

Thanks for wanting to help. Memento is open source and we welcome contributions of all sizes — from typo fixes to new features.

## Getting Started

1. Fork the repo
2. Clone your fork:
```bash
git clone https://github.com/JoyciAkira/memento.git
cd memento
uv sync
```

## Running Tests

We use `pytest`. To run the suite:
```bash
uv run pytest tests/ -v
```

All tests must pass before submitting a PR. Tests should run without API keys or network access (use `tests/conftest.py` fixtures).

**MCP / gate rigidi (subset veloce + smoke + contratti):**

```bash
uv run python benchmarks/run_benchmarks.py
```

Questo comando esegue `tests/test_mcp_benchmarks.py` (prestazioni e B6 offline esteso), `tests/test_mcp_tool_contracts.py` (roundtrip JSON/trace) e `tests/test_tools_smoke.py` (tutti i tool + validazione strutturale sui tool con contratto definito in `tests/mcp_contract_helpers.py`). La suite completa di benchmark include caricamenti massivi (migliaia di `add`) e può richiedere diversi minuti.

## Project Structure

```
memento/          ← core package
  tools/        ← MCP tool implementations
  retrieval/    ← search pipeline (FTS, dense, recency lanes)
  migrations/  ← SQLite schema versioning
  prompts/      ← LLM prompt templates
tests/            ← unit and integration tests
docs/            ← design documents
```

## PR Guidelines

1. Fork the repo and create a feature branch: `git checkout -b feat/my-thing`
2. Write your code
3. Add or update tests if applicable
4. Run `uv run pytest tests/ -v` — everything must pass
5. Commit with a clear message following [conventional commits](https://www.conventionalcommits.org/):
   - `feat: add Notion export format`
   - `fix: handle empty transcript files`
   - `docs: update MCP tool descriptions`
6. Push to your fork and open a PR against `main`

## Code Style

- **Formatting**: [Ruff](https://docs.astral.sh/ruff/) with 100-char line limit (configured in `pyproject.toml`)
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes
- **Type hints**: where they improve readability
- **Dependencies**: minimize. Don't add new deps without discussion.

## Finding Things to Work On

Check the [Issues](https://github.com/JoyciAkira/memento/issues) tab. Great starting points:

- **New retrieval lanes**: Add hybrid BM25 + dense lane improvements
- **Tests**: Increase coverage — especially for `knowledge_graph.py` and `tools/`
- **Docs**: Improve examples, add tutorials
- **Performance**: ANN vector search via sqlite-vss or FAISS

## Architecture Decisions

If you're planning a significant change, open an issue first to discuss the approach. Key principles:

- **Verbatim first**: Never summarize user content. Store exact words.
- **Local first**: Everything runs on the user's machine. No cloud dependencies.
- **Zero API by default**: Core features must work without any API key.
- **Hybrid search**: FTS5 + semantic retrieval fused via Reciprocal Rank Fusion.

## License

AGPL-3.0 — your contributions will be released under the same license.
