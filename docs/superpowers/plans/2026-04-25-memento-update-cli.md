# `memento update` CLI Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- []`) syntax for tracking.

**Goal:** Add a `memento update` subcommand that upgrades the installed Memento package via pip, auto-detecting whether `memento-mcp` or `memento` is installed, with `--dry-run` and `--restart` flags.

**Architecture:** New module `memento/updater.py` contains pure functions for package detection, pip upgrade (subprocess), and best-effort process restart. CLI handler in `memento/cli.py` is synchronous (subprocess pip calls) — no asyncio needed. All subprocess calls use `sys.executable` to target the current interpreter.

**Tech Stack:** Python stdlib only: `subprocess`, `sys`, `importlib.metadata`, `shlex`, `os`, `re`. No new dependencies.

---

## File Map

| File | Responsibility |
|------|---------------|
| `memento/updater.py` | **(new)** Package detection, pip upgrade, restart logic, report formatting |
| `memento/cli.py` | **(modify)** Add `update` subparser + `_handle_update` handler (sync) |
| `tests/test_updater.py` | **(new)** Unit tests for updater module (mocked subprocess) |
| `tests/test_cli.py` | **(modify)** Add CLI-level update smoke test |

---

### Task 1: Create `memento/updater.py` — Core logic

**Files:**
- Create: `memento/updater.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_updater.py`:

```python
"""Tests for memento/updater.py — package detection, pip upgrade, restart."""
from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch, call

import pytest


class TestDetectInstalledPackage:
    def test_detects_memento_mcp_first(self):
        with patch("memento.updater._get_version") as mock_ver:
            mock_ver.side_effect = lambda pkg: "1.0.0" if pkg == "memento-mcp" else None
            from memento.updater import detect_installed_package
            assert detect_installed_package() == "memento-mcp"

    def test_falls_back_to_memento(self):
        with patch("memento.updater._get_version") as mock_ver:
            mock_ver.side_effect = lambda pkg: "1.0.0" if pkg == "memento" else None
            from memento.updater import detect_installed_package
            assert detect_installed_package() == "memento"

    def test_returns_none_when_neither_found(self):
        with patch("memento.updater._get_version", return_value=None):
            from memento.updater import detect_installed_package
            assert detect_installed_package() is None


class TestGetInstalledVersion:
    def test_returns_version_string(self):
        with patch("importlib.metadata.version", return_value="1.2.3"):
            from memento.updater import _get_version
            assert _get_version("memento-mcp") == "1.2.3"

    def test_returns_none_on_package_not_found(self):
        with patch("importlib.metadata.version", side_effect=Exception("not found")):
            from memento.updater import _get_version
            assert _get_version("memento-mcp") is None


class TestPipUpgrade:
    def test_success_returns_true_and_output(self):
        fake_output = "Successfully installed memento-mcp-1.3.0"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=fake_output, stderr="")
            from memento.updater import pip_upgrade
            ok, out = pip_upgrade("memento-mcp", dry_run=False)
            assert ok is True
            assert fake_output in out

    def test_dry_run_does_not_execute_pip(self):
        with patch("subprocess.run") as mock_run:
            from memento.updater import pip_upgrade
            ok, out = pip_upgrade("memento-mcp", dry_run=True)
            mock_run.assert_not_called()
            assert ok is True
            assert "dry-run" in out.lower()

    def test_failure_returns_false_and_output(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="ERROR: Could not find")
            from memento.updater import pip_upgrade
            ok, out = pip_upgrade("memento-mcp", dry_run=False)
            assert ok is False
            assert "ERROR" in out


class TestUpgradeWithFallback:
    def test_primary_succeeds_no_fallback(self):
        with patch("memento.updater.pip_upgrade", return_value=(True, "ok")) as mock_pip:
            from memento.updater import upgrade_with_fallback
            ok, pkg, out = upgrade_with_fallback(dry_run=False)
            assert ok is True
            assert pkg == "memento-mcp"
            mock_pip.assert_called_once()

    def test_primary_fails_fallback_succeeds(self):
        with patch("memento.updater.pip_upgrade", side_effect=[
            (False, "fail"),
            (True, "ok memento"),
        ]) as mock_pip:
            from memento.updater import upgrade_with_fallback
            ok, pkg, out = upgrade_with_fallback(dry_run=False)
            assert ok is True
            assert pkg == "memento"
            assert mock_pip.call_count == 2

    def test_both_fail(self):
        with patch("memento.updater.pip_upgrade", side_effect=[
            (False, "fail1"),
            (False, "fail2"),
        ]):
            from memento.updater import upgrade_with_fallback
            ok, pkg, out = upgrade_with_fallback(dry_run=False)
            assert ok is False
            assert pkg == "memento"


class TestFormatReport:
    def test_success_report(self):
        from memento.updater import format_report
        report = format_report(
            python_path="/usr/bin/python3",
            package="memento-mcp",
            old_version="1.0.0",
            new_version="1.1.0",
            success=True,
            pip_output="Successfully installed",
        )
        assert "memento-mcp" in report
        assert "1.0.0" in report
        assert "1.1.0" in report
        assert "/usr/bin/python3" in report

    def test_failure_report(self):
        from memento.updater import format_report
        report = format_report(
            python_path="/usr/bin/python3",
            package="memento-mcp",
            old_version="1.0.0",
            new_version=None,
            success=False,
            pip_output="ERROR: blah",
        )
        assert "ERROR" in report or "Failed" in report

    def test_dry_run_report(self):
        from memento.updater import format_report
        report = format_report(
            python_path="/usr/bin/python3",
            package="memento-mcp",
            old_version="1.0.0",
            new_version=None,
            success=True,
            pip_output="Would run: pip install -U memento-mcp",
            dry_run=True,
        )
        assert "dry-run" in report.lower()


class TestRestartBestEffort:
    def test_no_matching_processes(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            from memento.updater import restart_best_effort
            result = restart_best_effort()
            assert result["killed"] == 0

    def test_kills_matching_processes(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="  1234  python -m memento.mcp_server\n")
            from memento.updater import restart_best_effort
            result = restart_best_effort()
            assert result["killed"] >= 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_updater.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write `memento/updater.py` implementation**

```python
"""Self-update logic for the Memento CLI.

Provides package detection (memento-mcp / memento fallback), pip upgrade
via subprocess, and best-effort process restart.
"""
from __future__ import annotations

import importlib.metadata
import subprocess
import sys
from typing import Optional


CANDIDATE_PACKAGES = ("memento-mcp", "memento")
_SUBPROCESS_TIMEOUT = 120


def _get_version(package: str) -> Optional[str]:
    try:
        return importlib.metadata.version(package)
    except Exception:
        return None


def detect_installed_package() -> Optional[str]:
    for pkg in CANDIDATE_PACKAGES:
        if _get_version(pkg) is not None:
            return pkg
    return None


def pip_upgrade(package: str, *, dry_run: bool = False) -> tuple[bool, str]:
    if dry_run:
        cmd = f"{sys.executable} -m pip install -U {package}"
        return True, f"[dry-run] Would run: {cmd}"

    cmd = [sys.executable, "-m", "pip", "install", "-U", package]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, f"pip upgrade timed out after {_SUBPROCESS_TIMEOUT}s"
    except Exception as exc:
        return False, str(exc)


def upgrade_with_fallback(*, dry_run: bool = False) -> tuple[bool, str, str]:
    last_output = ""
    for pkg in CANDIDATE_PACKAGES:
        ok, out = pip_upgrade(pkg, dry_run=dry_run)
        if ok:
            return True, pkg, out
        last_output = out
    return False, CANDIDATE_PACKAGES[-1], last_output


def _extract_version(pip_output: str) -> Optional[str]:
    import re

    match = re.search(r"Successfully installed\s+\S+-(\S+)", pip_output)
    if match:
        return match.group(1).strip()
    return None


def format_report(
    *,
    python_path: str,
    package: str,
    old_version: Optional[str],
    new_version: Optional[str],
    success: bool,
    pip_output: str,
    dry_run: bool = False,
) -> str:
    lines = [
        "Memento update",
        f"  Python: {python_path}",
        f"  Detected package: {package}",
    ]
    if old_version:
        lines.append(f"  Current version: {old_version}")

    if dry_run:
        lines.append("  Mode: dry-run (no changes made)")
        lines.append("")
        lines.append("Command that would be run:")
        lines.append(f"  {sys.executable} -m pip install -U {package}")
        return "\n".join(lines)

    if success and new_version:
        lines.append(f"  New version: {new_version}")
        lines.append("")
        lines.append("Update successful!")
    elif success:
        lines.append("")
        lines.append("Update completed (could not determine new version).")
    else:
        lines.append("")
        lines.append("Update FAILED.")
        lines.append(f"  {pip_output.strip()}")

    lines.append("")
    lines.append("Next steps:")
    lines.append("  - Restart your IDE MCP server (Trae/Cursor/VSCode) to load the new code.")
    return "\n".join(lines)


def restart_best_effort() -> dict:
    killed = 0
    try:
        result = subprocess.run(
            ["pgrep", "-f", "memento.mcp_server"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        pids = [p.strip() for p in result.stdout.strip().splitlines() if p.strip()]
        for pid in pids:
            try:
                subprocess.run(
                    ["kill", pid],
                    capture_output=True,
                    timeout=5,
                )
                killed += 1
            except Exception:
                pass
    except Exception:
        pass

    return {"killed": killed}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_updater.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add memento/updater.py tests/test_updater.py
git commit -m "feat(updater): add package detection, pip upgrade, and restart logic"
```

---

### Task 2: Wire `update` subcommand into CLI

**Files:**
- Modify: `memento/cli.py:284-350` (parser) + `memento/cli.py:356-385` (main)
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI test**

Add to `tests/test_cli.py`:

```python
class TestCLIUpdateHelp:
    def test_update_help(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["memento", "update", "--help"])
        with pytest.raises(SystemExit) as exc_info:
            from memento.cli import main
            main()
        assert exc_info.value.code == 0

    def test_update_dry_run(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["memento", "update", "--dry-run"])
        from memento.cli import main
        main()
        captured = capsys.readouterr()
        assert "dry-run" in captured.out.lower() or "dry_run" in captured.out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cli.py::TestCLIUpdateHelp -v`
Expected: FAIL (update subcommand not found)

- [ ] **Step 3: Add `update` subparser and handler to `memento/cli.py`**

In `_build_parser()`, add after the `coerce_parser` block:

```python
    update_parser = subparsers.add_parser(
        "update",
        help="Update Memento to the latest version via pip.",
    )
    update_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would be done without actually upgrading.",
    )
    update_parser.add_argument(
        "--restart",
        action="store_true",
        default=False,
        help="Best-effort: kill running memento-mcp processes after update.",
    )
```

Add handler function (synchronous, not async):

```python
def _handle_update(args: argparse.Namespace) -> None:
    from memento.updater import (
        detect_installed_package,
        upgrade_with_fallback,
        format_report,
        restart_best_effort,
    )
    from memento.redaction import redact_secrets

    dry_run = getattr(args, "dry_run", False)
    do_restart = getattr(args, "restart", False)

    detected = detect_installed_package()
    old_version = None
    if detected:
        from memento.updater import _get_version
        old_version = _get_version(detected)

    success, pkg_used, pip_output = upgrade_with_fallback(dry_run=dry_run)
    pip_output = redact_secrets(pip_output)

    new_version = None
    if success and not dry_run:
        from memento.updater import _extract_version
        new_version = _extract_version(pip_output)

    report = format_report(
        python_path=sys.executable,
        package=pkg_used,
        old_version=old_version,
        new_version=new_version,
        success=success,
        pip_output=pip_output,
        dry_run=dry_run,
    )
    print(report)

    if success and do_restart and not dry_run:
        result = restart_best_effort()
        if result["killed"] > 0:
            print(f"  Restarted {result['killed']} memento-mcp process(es).")
        else:
            print("  No running memento-mcp processes found. Restart your IDE manually.")
```

Update `main()` handler_map to include `"update": _handle_update`. Since `_handle_update` is synchronous and other handlers are async, the dispatch needs to handle both. Change the `main()` dispatch:

```python
    try:
        if asyncio.iscoroutinefunction(handler):
            asyncio.run(handler(args))
        else:
            handler(args)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        logger.debug("CLI error", exc_info=True)
        print(f"Error: {exc}")
        sys.exit(1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_cli.py -v`
Expected: ALL PASS (including new update tests)

- [ ] **Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -v --timeout=30`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add memento/cli.py tests/test_cli.py
git commit -m "feat(cli): add 'memento update' subcommand with --dry-run and --restart"
```

---

### Task 3: Manual verification

- [ ] **Step 1: Verify help output**

Run: `python3 -m memento.cli update --help`
Expected: Shows update subcommand help with `--dry-run` and `--restart` flags

- [ ] **Step 2: Verify dry-run**

Run: `python3 -m memento.cli update --dry-run`
Expected: Prints dry-run report with the pip command it would run, no actual changes

- [ ] **Step 3: Final commit push**

```bash
git push origin main
```
