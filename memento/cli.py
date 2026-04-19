"""CLI entry point for Memento — capture, search, and status outside the MCP server.

Provides ``memento capture``, ``memento search``, and ``memento status``
subcommands so users can interact with the local memory store directly from
the terminal without running the MCP server.

Usage::

    memento capture --auto                          # auto git context
    memento capture --text "my note about X"        # free-form note
    memento capture --auto --text "additional note" # both combined
    memento search "query string"                   # search memories
    memento status                                  # workspace info
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


async def _get_provider(workspace_root: str | None = None) -> Any:
    """Bootstrap the provider outside MCP server context.

    Returns the :class:`WorkspaceContext` so callers can access both the
    provider and workspace metadata.
    """
    from memento.workspace_context import get_workspace_context

    root = workspace_root or os.getcwd()
    ctx = get_workspace_context(root)
    await ctx.provider.initialize()
    return ctx


async def _handle_capture(args: argparse.Namespace) -> None:
    parts: list[str] = []

    if args.auto:
        from memento.git_context import build_auto_context

        auto_ctx = build_auto_context(os.getcwd())
        if auto_ctx:
            parts.append(auto_ctx)
        else:
            print("Warning: --auto requested but directory is not a git repository.")

    if args.text:
        from memento.redaction import redact_secrets

        parts.append(redact_secrets(args.text))

    if not parts:
        print("Error: provide --auto, --text, or both. Run 'memento capture --help'.")
        sys.exit(1)

    combined = "\n\n".join(parts)

    # Defence-in-depth: redact even though provider.add() also redacts.
    from memento.redaction import redact_secrets

    combined = redact_secrets(combined)

    ctx = await _get_provider()
    result: Dict[str, Any] = await ctx.provider.add(text=combined, user_id="default")
    print(f"Memory captured. id={result.get('id', 'unknown')}")


async def _handle_search(args: argparse.Namespace) -> None:
    ctx = await _get_provider()
    results: List[Dict[str, Any]] = await ctx.provider.search(
        query=args.query,
        user_id="default",
    )
    print(json.dumps(results, indent=2, default=str))


async def _handle_status(_args: argparse.Namespace) -> None:
    workspace_root = os.getcwd()
    memento_dir = os.path.join(workspace_root, ".memento")

    from memento.tools.utils import find_project_root

    project_root = find_project_root(workspace_root)

    db_path = os.path.join(project_root, ".memento", "neurograph_memory.db")

    print(f"Workspace root : {workspace_root}")
    print(f"Project root   : {project_root}")
    print(f"DB path        : {db_path}")
    print(f".memento dir   : {'exists' if os.path.isdir(memento_dir) else 'not found'}")



def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memento",
        description="Memento CLI — capture, search, and inspect local memories.",
    )
    subparsers = parser.add_subparsers(dest="command", help="available subcommands")

    capture_parser = subparsers.add_parser(
        "capture",
        help="Capture a new memory (auto git context and/or free-form text).",
    )
    capture_parser.add_argument(
        "--auto",
        action="store_true",
        default=False,
        help="Auto-capture git context (branch, commits, diff stats).",
    )
    capture_parser.add_argument(
        "--text",
        type=str,
        default=None,
        help="Free-form text to save as a memory.",
    )

    search_parser = subparsers.add_parser(
        "search",
        help="Search memories by query string.",
    )
    search_parser.add_argument(
        "query",
        type=str,
        help="The search query.",
    )

    subparsers.add_parser(
        "status",
        help="Show workspace status and configuration.",
    )

    return parser




def main() -> None:
    """Synchronous entry point registered as ``memento`` console script."""
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    handler_map: dict[str, Any] = {
        "capture": _handle_capture,
        "search": _handle_search,
        "status": _handle_status,
    }

    handler = handler_map.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    try:
        asyncio.run(handler(args))
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001
        logger.debug("CLI error", exc_info=True)
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
