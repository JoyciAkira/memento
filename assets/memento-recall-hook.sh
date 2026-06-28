#!/usr/bin/env bash
# Memento auto-recall hook for Claude Code (UserPromptSubmit).
#
# Reads the hook payload (JSON) from stdin, extracts the user's prompt, asks
# Memento for the most relevant memories, and emits them as additionalContext
# so they are injected into the conversation BEFORE Claude answers — without the
# agent having to call any tool.
#
# Best-effort by contract: on any problem it exits 0 with no output, so it can
# never block or corrupt the prompt. (Exit 2 would block the prompt — never do that.)
#
# Install: reference this script from .claude/settings.json under
#   hooks.UserPromptSubmit[].hooks[].command
# Override the python/memento invocation with MEMENTO_PY if needed.

set -uo pipefail

# Read the whole stdin payload.
payload="$(cat 2>/dev/null || true)"

# Extract the prompt; tolerate missing jq or malformed JSON.
prompt=""
if command -v jq >/dev/null 2>&1; then
  prompt="$(printf '%s' "$payload" | jq -r '.prompt // empty' 2>/dev/null || true)"
fi
[ -z "$prompt" ] && exit 0

# How to invoke Memento's CLI. Default to the module form; override via env.
MEMENTO_PY="${MEMENTO_PY:-python3 -m memento.cli}"

# Ask Memento for relevant context (best-effort, never fatal).
memory="$($MEMENTO_PY recall "$prompt" --limit 5 2>/dev/null || true)"
[ -z "$memory" ] && exit 0

# Emit as additionalContext (preferred Claude Code injection channel).
if command -v jq >/dev/null 2>&1; then
  jq -cn --arg ctx "$memory" \
    '{hookSpecificOutput:{hookEventName:"UserPromptSubmit",additionalContext:$ctx}}'
else
  # Fallback: plain stdout is also injected on exit 0.
  printf '%s\n' "$memory"
fi
exit 0
