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
    memento gc --prune-stale                        # archive decayed memories
    memento gc --prune-stale --dry-run              # preview without archiving
    memento tiers                                   # tier distribution and decay state
    memento sync                                    # record file events and rebuild the cache
    memento sync --replay-only                     # rebuild the cache from the ledger only
    memento index                                   # update the code symbol index
    memento hooks --install                         # install the pre-commit sync hook
    memento sync --watch                            # keep ledger and index updated live
    memento graph --symbol handle_sync              # show definitions and references
    memento ground                                  # link memories to indexed symbols
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


async def _handle_recall(args: argparse.Namespace) -> None:
    """Best-effort context recall for client hooks (e.g. Claude Code
    UserPromptSubmit). Prints a concise Markdown block of the top relevant
    memories so the hook can inject it into the conversation. On no match or
    any error it prints nothing and exits 0 — a hook must never block or noise
    up the prompt."""
    query = (args.query or "").strip()
    if not query:
        return
    limit = getattr(args, "limit", None) or 5
    try:
        ctx = await _get_provider()
        results: List[Dict[str, Any]] = await ctx.provider.search(
            query=query, user_id="default", limit=limit
        )
    except Exception:
        return
    if not results:
        return

    lines = ["## Relevant memory (Memento)"]
    for r in results[:limit]:
        text = (r.get("memory") or r.get("text") or "").strip().replace("\n", " ")
        if not text:
            continue
        if len(text) > 240:
            text = text[:237] + "..."
        tier = r.get("memory_tier") or r.get("tier")
        prefix = f"[{tier}] " if tier else ""
        lines.append(f"- {prefix}{text}")
    if len(lines) == 1:  # header only, no usable rows
        return
    print("\n".join(lines))


async def _handle_gc(args: argparse.Namespace) -> None:
    """Archive memories whose decay score fell below the threshold."""
    if not args.prune_stale and not args.dry_run:
        print("Error: specify --prune-stale, or --dry-run to preview candidates.")
        sys.exit(1)

    ctx = await _get_provider()
    result = await ctx.provider.forget_decayed(
        min_age_days=args.min_age_days,
        decay_threshold=args.threshold,
        user_id=args.user,
        dry_run=args.dry_run,
    )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    mode = "dry run" if result.get("dry_run") else "pruned"
    print(
        f"GC ({mode}): {result.get('candidates', 0)} candidate(s), "
        f"{result.get('deleted', 0)} archived "
        f"(min_age_days={result.get('min_age_days')}, threshold={result.get('threshold')})"
    )


async def _handle_tiers(args: argparse.Namespace) -> None:
    """Report tier distribution, decayed memories, and next GC candidates."""
    ctx = await _get_provider()
    report = await ctx.provider.tier_report(
        user_id=args.user,
        min_age_days=args.min_age_days,
        decay_threshold=args.threshold,
        limit=args.limit,
    )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    print(f"Memory tiers (user={report['user_id']}, total={report['total']})")
    for row in report["distribution"]:
        print(f"  {row['tier']:<10} {row['total']:>7}  ({row['deleted']} archived)")

    print(f"\nDecay: {report['decaying']} memories below full weight")
    print(
        f"Next GC candidates: {report['candidates']} "
        f"(threshold={report['threshold']}, min_age_days={report['min_age_days']})"
    )
    for candidate in report["next"]:
        print(
            f"  {candidate['id'][:8]}  {candidate['tier']:<9} "
            f"score={candidate['score']:.4f}  age={candidate['age_days']}d"
        )


def _handle_sync(args: argparse.Namespace) -> None:
    """Record file events, rebuild the cache, and update the code index."""
    if getattr(args, "watch", False):
        if args.replay_only:
            print("Error: --watch cannot be combined with --replay-only.")
            sys.exit(1)
        from memento.watch import SyncWatcher

        watcher = SyncWatcher(
            os.getcwd(),
            interval=args.interval,
            debounce=args.debounce,
            ground=not args.no_ground,
            ground_interval=args.ground_interval,
        )

        def report_cycle(report: Dict[str, Any]) -> None:
            if args.json:
                print(json.dumps(report, ensure_ascii=False), flush=True)
                return
            if args.quiet:
                return
            grounding = report.get("grounding") or {}
            if grounding.get("memories_scanned"):
                print(
                    f"grounded: {grounding['memories_linked']} memories, "
                    f"{grounding['links']} link(s), "
                    f"{grounding['kg_triples']} KG triple(s)",
                    flush=True,
                )
            if report.get("trigger") == "grounding":
                return
            index = report.get("index", {})
            print(
                f"synced: {report['events_appended']} event(s), "
                f"{index.get('indexed', 0)} indexed, "
                f"{index.get('symbols', 0)} symbol(s)",
                flush=True,
            )

        watcher.run(max_cycles=args.max_cycles, on_report=report_cycle)
        return

    from memento.ledger import FileLedger

    ledger = FileLedger(os.getcwd())
    report = ledger.sync(scan=not args.replay_only)

    if getattr(args, "compact", False):
        report["compaction"] = ledger.compact()

    if not getattr(args, "no_index", False):
        from memento.code_index import CodeIndex

        report["index"] = CodeIndex(os.getcwd(), ledger=ledger).update()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    action = "replayed" if args.replay_only else "synced"
    print(
        f"Ledger {action}: {report['events_appended']} new event(s), "
        f"{report['cache_files']} file(s) in cache"
    )
    print(
        f"  ledger : {report['ledger_dir']} ({'git' if report['git_backed'] else 'no git'})"
    )
    print(f"  cache  : {report['cache_path']}")
    if not args.replay_only:
        print(
            f"  scanned: {report['scanned']} file(s) — {report['added']} added, "
            f"{report['modified']} modified, {report['deleted']} deleted"
        )
    if "index" in report:
        index = report["index"]
        print(
            f"  index  : {index['indexed']} indexed, {index['removed']} removed, "
            f"{index['symbols']} symbol(s), {index['references']} reference(s) "
            f"[{index['parser']}]"
        )
    if report.get("compaction", {}).get("compacted"):
        print(f"  compact: snapshot {report['compaction']['snapshot_files']} file(s)")


def _handle_index(args: argparse.Namespace) -> None:
    """Update the tree-sitter code index using the ledger's file hashes."""
    from memento.code_index import CodeIndex

    report = CodeIndex(os.getcwd()).update(rebuild=args.rebuild)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    print(
        f"Code index: {report['indexed']} indexed, {report['removed']} removed, "
        f"{report['unchanged']} unchanged, {report['skipped']} skipped "
        f"({report['symbols']} symbols, {report['references']} references, "
        f"{report['parser']})"
    )
    print(f"  cache: {report['cache_path']}")
    if report["scanned"] == 0:
        print("  No ledger cache yet: run 'memento sync' first.")


def _handle_hooks(args: argparse.Namespace) -> None:
    """Inspect or install the Memento pre-commit hook."""
    from memento.git_hooks import hook_status, install_pre_commit_hook

    if args.install:
        path = install_pre_commit_hook(os.getcwd())
        if args.json:
            print(json.dumps({"installed": True, "path": path}, indent=2))
        else:
            print(f"Installed pre-commit hook: {path}")
        return

    status = hook_status(os.getcwd())
    if args.json:
        print(json.dumps(status, indent=2, ensure_ascii=False))
        return

    if not status["installed"]:
        detail = status.get("reason") or status.get("path") or "not installed"
        print(f"No pre-commit hook installed ({detail})")
        return
    print(f"pre-commit hook: {status['path']}")
    print(f"  coercion: {'yes' if status['coercion'] else 'no'}")
    print(f"  ledger  : {'yes' if status['ledger'] else 'no'}")


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

    # Check 2b: Database integrity (self-heal awareness)
    from memento.db_guard import is_corrupted, ensure_healthy_db

    memory_ok = not is_corrupted(db_path)
    _print_check("Memory DB integrity", memory_ok, "ok" if memory_ok else "CORRUPTED")
    kg_path = os.path.join(memento_dir, "neurograph_kg.sqlite")
    if os.path.isfile(kg_path):
        kg_ok = not is_corrupted(kg_path)
        _print_check("KG DB integrity", kg_ok, "ok" if kg_ok else "CORRUPTED")

    # Optional repair: back up corrupted DBs; next Memento start recreates fresh.
    if getattr(_args, "repair", False):
        ensure_healthy_db(db_path, label="memory")
        if os.path.isfile(kg_path):
            ensure_healthy_db(kg_path, label="kg")
        print(
            "\n[repair] corrupted DBs backed up; fresh store will be recreated on next Memento start."
        )

    # Check 3: Settings
    has_settings = os.path.isfile(settings_path)
    _print_check(
        "Settings file", has_settings, settings_path if has_settings else "not found"
    )

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
    _print_check(
        "Active Coercion",
        True,
        f"{'enabled' if coercion_enabled else 'disabled'}, {rules_count} rules",
    )

    # Check 7: Pre-commit hook
    git_dir = os.path.join(project_root, ".git")
    hook_path = os.path.join(git_dir, "hooks", "pre-commit")
    has_hook = os.path.isfile(hook_path)
    if has_hook:
        try:
            with open(hook_path, "r") as f:
                hook_content = f.read()
            is_memento = "memento" in hook_content
            _print_check(
                "Pre-commit hook",
                is_memento,
                "Memento hook installed" if is_memento else "Non-Memento hook found",
            )
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
        print(
            "Tip: Run 'memento capture --text \"hello\"' to initialize the .memento directory."
        )
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
        by_id = {
            r.get("id"): r
            for r in existing_rules
            if isinstance(r, dict) and isinstance(r.get("id"), str)
        }
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


def _handle_graph(args: argparse.Namespace) -> None:
    """Show symbol definitions and reference edges from the code index."""
    from memento.code_index import CodeIndex

    report = CodeIndex(os.getcwd()).graph(
        symbol=args.symbol, file=args.file, limit=args.limit
    )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    stats = report["stats"]
    print(
        f"Code graph: {stats['files']} file(s), {stats['symbols']} symbol(s), "
        f"{stats['references']} reference(s), "
        f"{stats['memory_links']} current memory link(s)"
    )
    if args.symbol:
        print(f"\nSymbol: {args.symbol}")
        for node in report["nodes"]:
            print(
                f"  {node['path']}:{node['start_line']}  {node['kind']} "
                f"{node['name']}  (memories: {node.get('memory_links', 0)})"
            )
        for edge in report["edges"]:
            source = edge["src_symbol"] or edge["path"]
            print(
                f"  {source} --{edge['kind']}--> {edge['target']} "
                f"({edge['path']}:{edge['line']})"
            )
    elif args.file:
        print(f"\nFile: {args.file}")
        for node in report["nodes"]:
            print(f"  {node['start_line']:>4}  {node['kind']:<10} {node['name']}")
        for edge in report["edges"]:
            source = edge["src_symbol"] or "<module>"
            print(
                f"  {source} --{edge['kind']}--> {edge['target']} (line {edge['line']})"
            )
    else:
        print("\nMost referenced targets:")
        for target in report["top_targets"][:20]:
            print(f"  {target['count']:>4}  {target['kind']:<9} {target['target']}")
        print("\nTop symbols:")
        for node in report["nodes"][:20]:
            print(
                f"  {node['path']}:{node['start_line']}  {node['kind']} "
                f"{node['name']} ({node.get('incoming', 0)} refs)"
            )


def _handle_ground(args: argparse.Namespace) -> None:
    """Link memories to indexed code symbols using ledger hashes."""
    import sqlite3

    from memento.code_grounding import MemoryGrounder
    from memento.kg_storage import resolve_kg_db_path
    from memento.knowledge_graph import KnowledgeGraph
    from memento.ledger import FileLedger

    project_root = FileLedger(os.getcwd()).project_root
    db_path = os.path.join(project_root, ".memento", "neurograph_memory.db")
    if not os.path.exists(db_path):
        print(f"Error: memory database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    try:
        sql = (
            "SELECT m.id, m.text FROM memories m "
            "WHERE m.id NOT IN (SELECT id FROM memory_meta WHERE is_deleted = 1)"
        )
        params: tuple = ()
        if args.limit and args.limit > 0:
            sql += " LIMIT ?"
            params = (args.limit,)
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    kg = KnowledgeGraph(resolve_kg_db_path(db_path))
    grounder = MemoryGrounder(project_root)
    report = grounder.link_all(rows, rebuild=args.rebuild, kg=kg)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    if not report.get("index_available"):
        print(f"Error: {report.get('error', 'code index unavailable')}")
        sys.exit(1)
    print(
        f"Grounding: {report['memories_scanned']} memories scanned, "
        f"{report['memories_linked']} linked, {report['links']} link(s), "
        f"{report['kg_triples']} KG triple(s) "
        f"({report['duration_seconds']}s)"
    )
    print(f"  cache: {report['cache_path']}")


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
            print(
                "  No running memento-mcp processes found. Restart your IDE manually."
            )


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

    recall_parser = subparsers.add_parser(
        "recall",
        help="Print top relevant memories as Markdown for client hooks (best-effort).",
    )
    recall_parser.add_argument("query", type=str, help="The query / user prompt.")
    recall_parser.add_argument(
        "--limit", type=int, default=5, help="Max memories to include (default 5)."
    )

    subparsers.add_parser(
        "status",
        help="Show workspace status and configuration.",
    )

    subparsers.add_parser(
        "doctor",
        help="Run environment health check.",
    ).add_argument(
        "--repair",
        action="store_true",
        default=False,
        help="Back up any corrupted DB and recreate a fresh store on next Memento start.",
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

    gc_parser = subparsers.add_parser(
        "gc",
        help="Prune stale memories using exponential temporal decay.",
    )
    gc_parser.add_argument(
        "--prune-stale",
        action="store_true",
        default=False,
        help="Archive memories whose decay score fell below --threshold.",
    )
    gc_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report candidates without archiving them.",
    )
    gc_parser.add_argument(
        "--min-age-days",
        type=float,
        default=30.0,
        help="Never prune memories younger than N days (default 30).",
    )
    gc_parser.add_argument(
        "--threshold",
        type=float,
        default=0.1,
        help="Decay score below which a memory is stale (default 0.1).",
    )
    gc_parser.add_argument(
        "--user",
        type=str,
        default="default",
        help="User/namespace to prune (default 'default').",
    )
    gc_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit a JSON report.",
    )

    tiers_parser = subparsers.add_parser(
        "tiers",
        help="Show tier distribution, decay state, and next GC candidates.",
    )
    tiers_parser.add_argument(
        "--user",
        type=str,
        default=None,
        help="Limit to one user/namespace (default: all).",
    )
    tiers_parser.add_argument(
        "--min-age-days",
        type=float,
        default=30.0,
        help="Minimum age for GC candidacy (default 30).",
    )
    tiers_parser.add_argument(
        "--threshold",
        type=float,
        default=0.1,
        help="Decay score below which a memory is a GC candidate (default 0.1).",
    )
    tiers_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="How many next candidates to print (default 10).",
    )
    tiers_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit a JSON report.",
    )

    sync_parser = subparsers.add_parser(
        "sync",
        help="Record file changes in the shadow ledger and rebuild the SQLite cache.",
    )
    sync_parser.add_argument(
        "--replay-only",
        action="store_true",
        default=False,
        help="Rebuild the cache from existing events without scanning the workspace.",
    )
    sync_parser.add_argument(
        "--no-index",
        action="store_true",
        default=False,
        help="Skip the tree-sitter code index update.",
    )
    sync_parser.add_argument(
        "--compact",
        action="store_true",
        default=False,
        help="Fold pending ledger events into a snapshot after syncing.",
    )
    sync_parser.add_argument(
        "--watch",
        action="store_true",
        default=False,
        help="Keep syncing while workspace files change (Ctrl+C to stop).",
    )
    sync_parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Watch polling interval in seconds (default 0.5).",
    )
    sync_parser.add_argument(
        "--debounce",
        type=float,
        default=0.8,
        help="Quiet period before a watched change is synced (default 0.8).",
    )
    sync_parser.add_argument(
        "--max-cycles",
        type=int,
        default=0,
        help="Stop after N sync cycles (default 0 = run until interrupted).",
    )
    sync_parser.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Suppress per-cycle output in watch mode.",
    )
    sync_parser.add_argument(
        "--no-ground",
        action="store_true",
        default=False,
        help="Skip linking newly created memories to code symbols.",
    )
    sync_parser.add_argument(
        "--ground-interval",
        type=float,
        default=5.0,
        help="Seconds between checks for new memories (default 5).",
    )
    sync_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit a JSON report.",
    )

    index_parser = subparsers.add_parser(
        "index",
        help="Update the tree-sitter code index from ledger hashes.",
    )
    index_parser.add_argument(
        "--rebuild",
        action="store_true",
        default=False,
        help="Drop the existing index and re-parse every supported file.",
    )
    index_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit a JSON report.",
    )

    hooks_parser = subparsers.add_parser(
        "hooks",
        help="Inspect or install the Memento pre-commit hook.",
    )
    hooks_parser.add_argument(
        "--install",
        action="store_true",
        default=False,
        help="Install or refresh the pre-commit hook in the current repository.",
    )
    hooks_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit a JSON report.",
    )

    graph_parser = subparsers.add_parser(
        "graph",
        help="Show symbol definitions and reference edges from the code index.",
    )
    graph_parser.add_argument(
        "--symbol", type=str, default=None, help="Focus on one symbol name."
    )
    graph_parser.add_argument(
        "--file", type=str, default=None, help="Focus on one workspace-relative file."
    )
    graph_parser.add_argument(
        "--limit", type=int, default=50, help="Max nodes/edges to return (default 50)."
    )
    graph_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit a JSON report.",
    )

    ground_parser = subparsers.add_parser(
        "ground",
        help="Link memories to indexed code symbols using ledger hashes.",
    )
    ground_parser.add_argument(
        "--rebuild",
        action="store_true",
        default=False,
        help="Drop all existing memory links and rebuild them.",
    )
    ground_parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only scan the first N memories (default 0 = all).",
    )
    ground_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit a JSON report.",
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


def main(*, hard_exit: bool = True) -> None:
    """Synchronous entry point registered as ``memento`` console script.

    ``hard_exit=False`` lets tests invoke the CLI in-process without
    terminating the interpreter. The console script keeps the default fast
    exit so one-shot hooks never wait on lingering worker threads.
    """
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    handler_map: dict[str, Any] = {
        "capture": _handle_capture,
        "search": _handle_search,
        "recall": _handle_recall,
        "status": _handle_status,
        "doctor": _handle_doctor,
        "coerce": _handle_coerce,
        "gc": _handle_gc,
        "tiers": _handle_tiers,
        "sync": _handle_sync,
        "index": _handle_index,
        "hooks": _handle_hooks,
        "graph": _handle_graph,
        "ground": _handle_ground,
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

    # The CLI is one-shot: the WorkspaceContext opens aiosqlite worker threads
    # (and may arm the autonomous daemon) whose teardown can hang for tens of
    # seconds at interpreter exit. Flush our output and hard-exit to skip it —
    # critical for the recall hook, which must return promptly on every prompt.
    sys.stdout.flush()
    sys.stderr.flush()
    if hard_exit:
        os._exit(0)


if __name__ == "__main__":
    main()
