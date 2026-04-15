# Release Readiness (Public v0.1)

## Goals
- Make the repository immediately credible and easy to adopt (identity, licensing, docs, CI).
- Reduce security footguns for local usage (UI escaping, redaction invariants).
- Improve packaging ergonomics (lean runtime deps, test extras, reproducible installs).
- Keep changes incremental and fully covered by the existing test suite.

## Non-Goals
- Rewriting core architecture (RRF, graph provider, workspace router).
- Adding complex auth/multi-user features.
- Breaking public APIs without a migration path.

## Scope

### 1) Repo Polish
- Ensure licensing and project identity are consistent across:
  - README, LICENSE, CONTRIBUTING
  - `pyproject.toml` metadata
  - `.claude-plugin` metadata/config
- Remove remaining stale references to the old project name and nonexistent paths (e.g. CODEOWNERS).

### 2) Security Hardening
- UI server must escape memory content before rendering to HTML (avoid XSS via stored memory).
- Standardize redaction expectations: secrets must not be persisted in long-term memory “by accident” when possible.

### 3) Packaging & Release Hygiene
- Move test-only dependencies out of runtime dependencies:
  - Provide extras, e.g. `pip install memento-mcp[test]`
- Keep installation instructions consistent with `uv` usage.

### 4) CI Fixes
- Fix GitHub Actions versions to real, supported releases.
- Keep CI running `pytest` and producing coverage artifact (existing pattern).

## Deliverables (PR)
- Code and documentation changes implementing the scope above.
- Updated `.gitignore` to ensure no local `.memento/` data can be committed.
- All tests passing (`uv run pytest`).

## Acceptance Criteria
- `README.md`, `CONTRIBUTING.md`, `LICENSE`, `.claude-plugin/plugin.json`, `pyproject.toml` show consistent project name and license.
- UI server renders memory strings safely (no raw HTML injection).
- `pyproject.toml` runtime deps do not include pytest tooling; tests run via an extra.
- CI uses existing, valid action versions and passes in GitHub Actions.
- `uv run pytest` passes locally.

## Implementation Plan (Tasks)
1. Identity/licensing/docs cleanup (including CODEOWNERS fixes).
2. CI workflow fixes (actions versions + minor hardening).
3. Packaging cleanup (extras for tests, docs update).
4. UI escaping + redaction invariants (tests).

