"""Canonical workspace path resolution.

The CLI and the MCP server must agree on the workspace root.  Keeping this in
one small module avoids the previous split where the CLI used ``cwd`` while the
provider used ``MEMENTO_DIR`` for metadata.
"""

from __future__ import annotations

import os


def resolve_workspace_root(workspace_root: str | None = None) -> str:
    """Return the canonical root for a workspace.

    Precedence is explicit argument, ``MEMENTO_DIR``, then the current working
    directory.  The result is absolute and resolves symlinks, so aliases such as
    a symlinked project and its target share one workspace context.
    """

    explicit = str(workspace_root).strip() if workspace_root is not None else ""
    env_root = os.environ.get("MEMENTO_DIR", "").strip()
    raw = explicit or env_root or os.getcwd()
    return os.path.realpath(os.path.abspath(os.path.expanduser(raw)))


def workspace_cache_key(workspace_root: str) -> str:
    """Return a case-normalized key for the in-process context cache."""

    return os.path.normcase(resolve_workspace_root(workspace_root))
