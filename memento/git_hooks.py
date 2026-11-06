import os
import shlex
import stat
import subprocess
import sys


def _find_git_root(start_dir: str) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start_dir,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if out:
            return out
    except Exception:
        pass

    d = os.path.abspath(start_dir)
    while True:
        git_path = os.path.join(d, ".git")
        if os.path.isdir(git_path) or os.path.isfile(git_path):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _hooks_dir(repo_root: str) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--git-path", "hooks"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if out:
            return out if os.path.isabs(out) else os.path.join(repo_root, out)
    except Exception:
        pass
    return os.path.join(repo_root, ".git", "hooks")


def install_pre_commit_hook(workspace_root: str) -> str:
    repo_root = _find_git_root(workspace_root)
    if repo_root is None:
        raise ValueError("workspace_root is not inside a git repository")

    hooks_dir = _hooks_dir(repo_root)
    os.makedirs(hooks_dir, exist_ok=True)
    hook_path = os.path.join(hooks_dir, "pre-commit")

    previous_hook_path = os.path.join(hooks_dir, "pre-commit.memento.previous")
    if os.path.exists(hook_path):
        try:
            with open(hook_path, "r") as f:
                existing = f.read()
        except Exception:
            existing = ""
        if "memento.active_coercion_hook" not in existing:
            try:
                if os.path.exists(previous_hook_path):
                    os.remove(previous_hook_path)
                os.replace(hook_path, previous_hook_path)
            except Exception:
                pass

    python = shlex.quote(sys.executable)
    script = f"""#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$(git rev-parse --git-path hooks)"
PREV="$HOOKS_DIR/pre-commit.memento.previous"
if [ -x "$PREV" ]; then
  "$PREV" "$@"
fi
PYTHONPATH="$ROOT" {python} -m memento.active_coercion_hook
PYTHONPATH="$ROOT" {python} -m memento.ledger_hook || true
"""

    with open(hook_path, "w") as f:
        f.write(script)

    st = os.stat(hook_path)
    os.chmod(hook_path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return hook_path


def hook_status(workspace_root: str) -> dict:
    repo_root = _find_git_root(workspace_root)
    if repo_root is None:
        return {
            "installed": False,
            "path": None,
            "coercion": False,
            "ledger": False,
            "reason": "not a git repository",
        }

    hook_path = os.path.join(_hooks_dir(repo_root), "pre-commit")
    if not os.path.exists(hook_path):
        return {
            "installed": False,
            "path": hook_path,
            "coercion": False,
            "ledger": False,
        }

    try:
        with open(hook_path, "r") as f:
            content = f.read()
    except Exception:
        content = ""

    return {
        "installed": True,
        "path": hook_path,
        "coercion": "memento.active_coercion_hook" in content,
        "ledger": "memento.ledger_hook" in content,
    }
