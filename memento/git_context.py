"""Extract git context (branch, commits, diff stats) from a working directory.

Provides pure functions that invoke git via subprocess and return structured
strings suitable for composing auto-contextualized memories.  Every function
degrades gracefully — if git is unavailable or the path is not a repository,
the caller receives an empty string or ``None`` instead of an exception.
"""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)


def _run_git(args: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    """Execute a git command and return the CompletedProcess."""
    return subprocess.run(  # noqa: S603
        ["git", *args],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=cwd,
    )


def is_git_repo(path: str) -> bool:
    """Return ``True`` if *path* is inside a git repository."""
    try:
        result = _run_git(["rev-parse", "--is-inside-work-tree"], path)
        return result.returncode == 0 and "true" in result.stdout.strip().lower()
    except Exception:
        logger.debug("is_git_repo check failed for %s", path, exc_info=True)
        return False


def get_current_branch(path: str) -> str | None:
    """Return the current branch name, or ``None`` on failure."""
    try:
        result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], path)
        if result.returncode == 0:
            branch = result.stdout.strip()
            return branch if branch else None
        return None
    except Exception:
        logger.debug("get_current_branch failed for %s", path, exc_info=True)
        return None


def get_recent_commits(path: str, count: int = 5) -> list[str]:
    """Return the last *count* commit messages in one-line format.

    Each entry looks like ``"abc1234 commit message"``.
    """
    try:
        result = _run_git(
            ["log", f"--max-count={count}", "--pretty=format:%h %s"],
            path,
        )
        if result.returncode == 0:
            lines = [line for line in result.stdout.strip().splitlines() if line]
            return lines
        return []
    except Exception:
        logger.debug("get_recent_commits failed for %s", path, exc_info=True)
        return []


def get_staged_diff_stat(path: str) -> str:
    """Return ``git diff --stat --cached`` output (staged changes summary)."""
    try:
        result = _run_git(["diff", "--stat", "--cached"], path)
        if result.returncode == 0:
            output = result.stdout.strip()
            return output if output else "None"
        return "None"
    except Exception:
        logger.debug("get_staged_diff_stat failed for %s", path, exc_info=True)
        return "None"


def get_unstaged_diff_stat(path: str) -> str:
    """Return ``git diff --stat`` output (unstaged changes summary)."""
    try:
        result = _run_git(["diff", "--stat"], path)
        if result.returncode == 0:
            output = result.stdout.strip()
            return output if output else "None"
        return "None"
    except Exception:
        logger.debug("get_unstaged_diff_stat failed for %s", path, exc_info=True)
        return "None"


def build_auto_context(path: str) -> str:
    """Compose all git context into a single formatted string.

    The output is designed to be saved directly as a memory and includes the
    current branch, recent commits, and both staged and unstaged diff stats.
    Returns an empty string when *path* is not a git repository.
    """
    if not is_git_repo(path):
        return ""

    branch = get_current_branch(path) or "unknown"
    commits = get_recent_commits(path)
    staged = get_staged_diff_stat(path)
    unstaged = get_unstaged_diff_stat(path)

    commit_lines = "\n".join(f"  - {c}" for c in commits) if commits else "  (none)"

    return (
        "[Memento Auto-Capture]\n"
        f"Branch: {branch}\n"
        "\n"
        "Recent commits:\n"
        f"{commit_lines}\n"
        "\n"
        "Staged changes:\n"
        f"{staged}\n"
        "\n"
        "Unstaged changes:\n"
        f"{unstaged}\n"
    )
