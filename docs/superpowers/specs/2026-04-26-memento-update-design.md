# `memento update` (Self-Update) Design

**Goal:** Add a single-command UX (`memento update`) that updates the installed Memento MCP package to the latest version via pip, using the same Python environment that runs `memento`.

**Non-goal:** Guarantee updating all IDEs automatically. (Different IDEs may run different Python interpreters/venvs. This command updates only the environment in which it is executed.)

---

## User Experience

### Commands

- `memento update`
- `memento update --dry-run`
- `memento update --restart` (best-effort)

### Example output (success)

```
Memento update
  Python: /path/to/python
  Detected package: memento-mcp
  Current version: 0.1.0
  Upgrading via pip...
  New version: 0.1.1

Next steps:
  - Restart your IDE MCP server (Trae/Cursor/VSCode) to load the new code.
  - Or run: memento-mcp (if you launch it manually)
```

### Example output (multiple environments)

The command prints a hint when it detects the code is loaded from a different location than expected (e.g. namespace package / multiple paths), and reminds the user to run `memento update` in the same environment used by the IDE.

---

## Behavior

### Package detection (auto-detect)

`memento update` attempts updates in this order:

1. `memento-mcp`
2. `memento`

Detection is done via `importlib.metadata`:

- If `importlib.metadata.version("memento-mcp")` works: treat package name as `memento-mcp`
- Else if `importlib.metadata.version("memento")` works: treat package name as `memento`
- Else: fall back to trying `pip install -U memento-mcp`, and if that fails, try `pip install -U memento`

The command always uses `sys.executable -m pip ...` to ensure it updates the active interpreter environment.

### Upgrade command

- Default: `python -m pip install -U <package>`
- No extras by default.
- If user passes extras in the future, use a dedicated flag (not part of this spec).

### Restart (best-effort, opt-in)

`--restart` attempts a conservative local restart:

- It does not edit IDE config files.
- It can attempt to terminate processes whose command line matches `memento-mcp` / `memento.mcp_server` and are owned by the current user.
- If no process is found or termination fails, it prints manual restart instructions.

Rationale: automatic restarts across IDE boundaries are not reliably possible and should remain opt-in.

---

## Safety and Security

- Never logs or prints secrets (reuse existing `redact_secrets()` for any command output that might embed tokens).
- Never runs `pip` with `--extra-index-url` or custom package sources by default.
- Never uses `sudo`.
- Uses a timeout for subprocess calls to avoid hanging.
- Does not modify files outside the current Python environment’s site-packages.

---

## Implementation Plan (high-level decomposition)

### Code units

- `memento/cli.py`
  - Add `update` subcommand to argparse.
  - Implement async handler `_handle_update(args)`.

- `memento/updater.py` (new)
  - `detect_installed_package() -> str | None`
  - `get_installed_version(pkg: str) -> str | None`
  - `pip_upgrade(pkg: str, *, dry_run: bool) -> tuple[bool, str]` (success, output)
  - `restart_best_effort() -> dict` (optional, only with `--restart`)
  - `format_report(...) -> str`

### External dependencies

- No new dependencies. Use stdlib (`subprocess`, `sys`, `importlib.metadata`, `shlex`, `os`, `time`).

---

## Tests

Unit tests should cover:

- Package detection precedence: `memento-mcp` before `memento`
- Dry-run does not execute pip (subprocess mocked)
- pip failure on first package triggers fallback to second package (subprocess mocked)
- Output includes old/new versions when available

Restart tests:
- Keep minimal and mock-based (do not kill real processes in CI).

---

## Acceptance Criteria

- `memento update` runs in the user’s terminal and upgrades the package via pip using the same interpreter.
- Works when either `memento-mcp` or `memento` is installed (auto-detect + fallback).
- Does not crash when neither package metadata is present; still attempts upgrade and returns actionable errors.
- `--dry-run` prints the exact commands it would run.
- `--restart` is best-effort and never fails the update step if restart fails.

