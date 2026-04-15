import os
import stat


def _find_git_root(start_dir: str) -> str | None:
    d = os.path.abspath(start_dir)
    while True:
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def install_pre_commit_hook(workspace_root: str) -> str:
    repo_root = _find_git_root(workspace_root)
    if repo_root is None:
        raise ValueError("workspace_root is not inside a git repository")

    hooks_dir = os.path.join(repo_root, ".git", "hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    hook_path = os.path.join(hooks_dir, "pre-commit")

    script = """#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
PYTHONPATH="$ROOT" python3 -m memento.active_coercion_hook
"""

    with open(hook_path, "w") as f:
        f.write(script)

    st = os.stat(hook_path)
    os.chmod(hook_path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return hook_path
