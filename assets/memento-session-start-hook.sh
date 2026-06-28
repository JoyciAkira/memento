#!/usr/bin/env bash
# Memento session-start hook for Claude Code (SessionStart).
#
# Runs once at session start/resume and injects a concise workspace summary
# (status + relevant project memory) as additionalContext, giving Claude stable
# orientation without any tool call. Best-effort: exits 0 with no output on any
# problem so it never blocks session start.
#
# Install: reference from .claude/settings.json under
#   hooks.SessionStart[].hooks[].command

set -uo pipefail

MEMENTO_PY="${MEMENTO_PY:-python3 -m memento.cli}"

# Pull a small, high-signal recall seeded by the workspace itself. Using the
# project directory name as the query keeps this cheap and generic.
seed="${PWD##*/} project goals overview"
memory="$($MEMENTO_PY recall "$seed" --limit 5 2>/dev/null || true)"
[ -z "$memory" ] && exit 0

if command -v jq >/dev/null 2>&1; then
  jq -cn --arg ctx "$memory" \
    '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$ctx}}'
else
  printf '%s\n' "$memory"
fi
exit 0
