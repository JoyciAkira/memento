#!/usr/bin/env bash
set -euo pipefail
PLUGIN_ROOT="${CODEX_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# Capture stdin (hook input from Codex)
INPUT_FILE=$(mktemp 2>/dev/null || echo "/tmp/mempal-precompact-hook-$$.json")
cat > "$INPUT_FILE"

# Pipe to Python CLI with codex harness
cat "$INPUT_FILE" | python3 -m mempalace hook run --hook precompact --harness codex
EXIT_CODE=$?

# Cleanup
rm -f "$INPUT_FILE" 2>/dev/null
exit $EXIT_CODE
