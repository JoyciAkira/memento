"""Pre-commit entry point that keeps the ledger and code index in sync.

The hook must never block a commit: any failure is reported on stderr and turns
into a zero exit code. Set ``MEMENTO_SKIP_LEDGER_HOOK=1`` to bypass it and
``MEMENTO_LEDGER_QUIET=1`` to silence its output.
"""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    if os.environ.get("MEMENTO_SKIP_LEDGER_HOOK", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return 0
    try:
        repo_root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return 0
    if not repo_root:
        return 0

    quiet = os.environ.get("MEMENTO_LEDGER_QUIET") == "1"
    try:
        from memento.code_index import CodeIndex
        from memento.ledger import FileLedger

        ledger = FileLedger(repo_root)
        report = ledger.sync()
        index_report = CodeIndex(repo_root, ledger=ledger).update()
        if not quiet:
            print(
                f"[memento] ledger: {report['events_appended']} new event(s), "
                f"{report['cache_files']} file(s); index: {index_report['indexed']} "
                f"indexed, {index_report['removed']} removed"
            )
    except Exception as exc:  # never block a commit on ledger/index failures
        if not quiet:
            print(f"[memento] ledger sync skipped: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
