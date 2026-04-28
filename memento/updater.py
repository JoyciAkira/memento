"""Self-update logic for the Memento CLI.

Provides package detection (memento-mcp / memento fallback), pip upgrade
via subprocess, and best-effort process restart.
"""
from __future__ import annotations

import importlib.metadata
import re
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
