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
    memento doctor                                  # environment health check
    memento update                                  # update to latest version
    memento update --dry-run                        # preview update
    memento update --restart                        # update + best-effort restart
    memento coerce --list                           # list preset packs
    memento coerce --apply typescript-strict        # apply a preset
    memento coerce --status                         # show active rules
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


def _print_check(name: str, ok: bool, detail: str) -> None:
    status = "[OK]" if ok else "[WARN]"
    print(f"  {status} {name}: {detail}")


async def _handle_doctor(_args: argparse.Namespace) -> None:
    from memento.tools.utils import find_project_root
    from memento.local_embeddings import is_fastembed_available

    workspace_root = os.getcwd()
    project_root = find_project_root(workspace_root)
    memento_dir = os.path.join(project_root, ".memento")
    settings_path = os.path.join(memento_dir, "settings.json")
    db_path = os.path.join(memento_dir, "neurograph_memory.db")

    print("Memento Doctor — Environment Check")
    print("=" * 40)

    # Check 1: .memento directory
    has_dir = os.path.isdir(memento_dir)
    _print_check(".memento directory", has_dir, memento_dir)

    # Check 2: Database
    has_db = os.path.isfile(db_path)
    _print_check("Database file", has_db, db_path if has_db else "not found")

    # Check 3: Settings
    has_settings = os.path.isfile(settings_path)
    _print_check("Settings file", has_settings, settings_path if has_settings else "not found")

    # Check 4: Embedding backend
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    explicit_backend = os.environ.get("MEMENTO_EMBEDDING_BACKEND", "").strip().lower()

    if explicit_backend:
        backend = explicit_backend
    elif api_key:
        backend = "openai"
    elif is_fastembed_available():
        backend = "local (fastembed)"
    else:
        backend = "none"
    _print_check("Embedding backend", True, backend)

    # Check 5: LLM config
    has_llm = bool(api_key) or "localhost" in base_url or "127.0.0.1" in base_url
    llm_detail = base_url if has_llm else "not configured"
    _print_check("LLM config", has_llm, llm_detail)

    # Check 6: Coercion rules
    rules_count = 0
    coercion_enabled = False
    if has_settings:
        try:
            with open(settings_path, "r") as f:
                data = json.load(f)
            coercion = data.get("active_coercion", {})
            coercion_enabled = coercion.get("enabled", False)
            rules_count = len(coercion.get("rules", []))
        except Exception:
            pass
    _print_check("Active Coercion", True, f"{'enabled' if coercion_enabled else 'disabled'}, {rules_count} rules")

    # Check 7: Pre-commit hook
    git_dir = os.path.join(project_root, ".git")
    hook_path = os.path.join(git_dir, "hooks", "pre-commit")
    has_hook = os.path.isfile(hook_path)
    if has_hook:
        try:
            with open(hook_path, "r") as f:
                hook_content = f.read()
            is_memento = "memento" in hook_content
            _print_check("Pre-commit hook", is_memento, "Memento hook installed" if is_memento else "Non-Memento hook found")
        except Exception:
            _print_check("Pre-commit hook", False, "unable to read")
    else:
        _print_check("Pre-commit hook", False, "not installed")

    # Check 8: Version
    try:
        import memento
        version = getattr(memento, "__version__", "unknown")
    except Exception:
        version = "unknown"
    _print_check("Version", True, version)

    print()
    if not has_dir:
        print("Tip: Run 'memento capture --text \"hello\"' to initialize the .memento directory.")
    if not has_hook and has_dir:
        print("Tip: Install pre-commit hook via MCP tool 'memento_install_git_hooks'.")


async def _handle_coerce(args: argparse.Namespace) -> None:
    from memento.tools.coercion import PRESETS

    if args.list_presets:
        if not PRESETS:
            print("No presets available.")
            return
        print("Available coercion presets:")
        for name, rules in sorted(PRESETS.items()):
            print(f"  {name} ({len(rules)} rules)")
        return

    if args.status:
        workspace_root = os.getcwd()
        from memento.tools.utils import find_project_root
        project_root = find_project_root(workspace_root)
        settings_path = os.path.join(project_root, ".memento", "settings.json")
        if not os.path.isfile(settings_path):
            print("No settings file found. Apply a preset first.")
            return
        try:
            with open(settings_path, "r") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading settings: {e}")
            return
        coercion = data.get("active_coercion", {})
        enabled = coercion.get("enabled", False)
        rules = coercion.get("rules", [])
        print(f"Active Coercion: {'ENABLED' if enabled else 'DISABLED'}")
        print(f"Active rules: {len(rules)}")
        for r in rules:
            rid = r.get("id", "unknown")
            severity = r.get("severity", "?")
            globs = ", ".join(r.get("path_globs", []))
            print(f"  [{severity}] {rid}: {globs}")
        return

    if args.apply:
        preset = args.apply
        if preset not in PRESETS:
            print(f"Unknown preset: {preset}")
            print(f"Available: {', '.join(sorted(PRESETS.keys()))}")
            sys.exit(1)

        workspace_root = os.getcwd()
        from memento.tools.utils import find_project_root
        project_root = find_project_root(workspace_root)
        memento_dir = os.path.join(project_root, ".memento")
        os.makedirs(memento_dir, exist_ok=True)
        settings_path = os.path.join(memento_dir, "settings.json")

        existing_data = {}
        if os.path.isfile(settings_path):
            try:
                with open(settings_path, "r") as f:
                    existing_data = json.load(f)
            except Exception:
                existing_data = {}

        coercion = existing_data.get("active_coercion", {})
        existing_rules = coercion.get("rules", [])
        if not isinstance(existing_rules, list):
            existing_rules = []

        # Merge by rule ID (same logic as MCP tool)
        by_id = {r.get("id"): r for r in existing_rules if isinstance(r, dict) and isinstance(r.get("id"), str)}
        for r in PRESETS[preset]:
            if isinstance(r, dict) and isinstance(r.get("id"), str):
                by_id[r["id"]] = r

        coercion["rules"] = list(by_id.values())
        coercion["enabled"] = True
        existing_data["active_coercion"] = coercion

        with open(settings_path, "w") as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)

        print(f"Applied preset '{preset}'. Total rules: {len(coercion['rules'])}")
        print(f"Settings saved to: {settings_path}")
        return

    print("Use --apply PRESET, --list, or --status. Run 'memento coerce --help'.")


def _handle_update(args: argparse.Namespace) -> None:
    from memento.redaction import redact_secrets
    from memento.updater import (
        detect_installed_package,
        upgrade_with_fallback,
        format_report,
        restart_best_effort,
        _get_version,
        _extract_version,
    )

    dry_run = getattr(args, "dry_run", False)
    do_restart = getattr(args, "restart", False)

    detected = detect_installed_package()
    old_version = None
    if detected:
        old_version = _get_version(detected)

    success, pkg_used, pip_output = upgrade_with_fallback(dry_run=dry_run)
    pip_output = redact_secrets(pip_output)

    new_version = None
    if success and not dry_run:
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

    subparsers.add_parser(
        "doctor",
        help="Run environment health check.",
    )

    coerce_parser = subparsers.add_parser(
        "coerce",
        help="Manage Active Coercion preset packs.",
    )
    coerce_group = coerce_parser.add_mutually_exclusive_group(required=True)
    coerce_group.add_argument(
        "--apply",
        type=str,
        metavar="PRESET",
        help="Apply a coercion preset pack.",
    )
    coerce_group.add_argument(
        "--list",
        action="store_true",
        dest="list_presets",
        help="List available preset packs.",
    )
    coerce_group.add_argument(
        "--status",
        action="store_true",
        help="Show active coercion rules.",
    )

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
        "doctor": _handle_doctor,
        "coerce": _handle_coerce,
        "update": _handle_update,
    }

    handler = handler_map.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    try:
        if asyncio.iscoroutinefunction(handler):
            asyncio.run(handler(args))
        else:
            handler(args)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001
        logger.debug("CLI error", exc_info=True)
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
