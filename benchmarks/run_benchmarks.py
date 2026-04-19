#!/usr/bin/env python3
"""
Esegue i benchmark MCP rigidi (pytest): latenza in ms, correttezza retrieval, layout storage
KG dedicato (B7), contratti JSON offline, smoke tool con assert di forma.

Uso dalla root del repo:
  uv run python benchmarks/run_benchmarks.py

Exit code = exit code di pytest (0 = tutti i gate superati).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    tests = [
        "tests/test_mcp_benchmarks.py",
        "tests/test_mcp_tool_contracts.py",
        "tests/test_tools_smoke.py",
    ]
    cmd = [sys.executable, "-m", "pytest", *tests, "-q", "--tb=short"]
    return subprocess.call(cmd, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
