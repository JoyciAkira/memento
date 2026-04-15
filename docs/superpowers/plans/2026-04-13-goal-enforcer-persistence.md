# Goal Enforcer Persistence (Hybrid Rules File) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the Goal Enforcer tri-state (`level1/level2/level3`) across MCP restarts and keep it synchronized with a user-editable workspace file `.memento.rules.md` (hybrid persistence).

**Architecture:** Store the canonical runtime state in `.memento/settings.json` (machine state) and mirror it into a human-editable `.memento.rules.md` in the workspace root. On startup, load defaults → settings.json → rules file (rules file overrides). When the config changes (tool call), write both, updating only a delimited block inside the rules markdown so user notes are preserved.

**Tech Stack:** Python stdlib (json, os, pathlib), pytest, ruff.

---

### Task 1: Introduce a dedicated rules file module (parse + render + upsert)

**Files:**
- Create: `memento/enforcement_rules.py`
- Test: `tests/test_enforcement_rules.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_enforcement_rules.py`:

```python
import textwrap

from memento.enforcement_rules import (
    extract_goal_enforcer_config_from_rules_md,
    upsert_goal_enforcer_block,
)


def test_extract_goal_enforcer_config_from_rules_md_defaults_to_empty():
    assert extract_goal_enforcer_config_from_rules_md("") == {}


def test_extract_goal_enforcer_config_from_rules_md_reads_block():
    content = textwrap.dedent(
        """
        # Memento Rules

        some user notes

        <!-- memento:goal-enforcer:start -->
        level1: true
        level2: false
        level3: true
        <!-- memento:goal-enforcer:end -->
        """
    ).strip()
    assert extract_goal_enforcer_config_from_rules_md(content) == {
        "level1": True,
        "level2": False,
        "level3": True,
    }


def test_upsert_goal_enforcer_block_creates_block_if_missing_and_preserves_notes():
    original = "# Notes\n\nUser wants strict mode.\n"
    updated = upsert_goal_enforcer_block(
        original,
        {"level1": True, "level2": False, "level3": False},
    )
    assert "User wants strict mode." in updated
    assert "<!-- memento:goal-enforcer:start -->" in updated
    assert "level1: true" in updated


def test_upsert_goal_enforcer_block_updates_existing_block_in_place():
    original = textwrap.dedent(
        """
        # Memento Rules
        <!-- memento:goal-enforcer:start -->
        level1: false
        level2: false
        level3: false
        <!-- memento:goal-enforcer:end -->
        """
    ).strip()
    updated = upsert_goal_enforcer_block(
        original,
        {"level1": False, "level2": True, "level3": False},
    )
    assert "level2: true" in updated
    assert "level2: false" not in updated
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_enforcement_rules.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'memento.enforcement_rules'`.

- [ ] **Step 3: Implement `memento/enforcement_rules.py`**

Create `memento/enforcement_rules.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


GOAL_ENFORCER_BLOCK_START = "<!-- memento:goal-enforcer:start -->"
GOAL_ENFORCER_BLOCK_END = "<!-- memento:goal-enforcer:end -->"


def _parse_bool(val: str) -> bool | None:
    normalized = val.strip().lower()
    if normalized in ("true", "yes", "on", "1"):
        return True
    if normalized in ("false", "no", "off", "0"):
        return False
    return None


def extract_goal_enforcer_config_from_rules_md(content: str) -> dict[str, bool]:
    if not content:
        return {}

    start = content.find(GOAL_ENFORCER_BLOCK_START)
    end = content.find(GOAL_ENFORCER_BLOCK_END)
    if start == -1 or end == -1 or end <= start:
        return {}

    block = content[start + len(GOAL_ENFORCER_BLOCK_START) : end]
    parsed: dict[str, bool] = {}
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key not in ("level1", "level2", "level3"):
            continue
        b = _parse_bool(value)
        if b is None:
            continue
        parsed[key] = b
    return parsed


def render_goal_enforcer_block(config: dict[str, bool]) -> str:
    def as_line(key: str) -> str:
        val = "true" if config.get(key, False) else "false"
        return f"{key}: {val}"

    lines = [
        GOAL_ENFORCER_BLOCK_START,
        as_line("level1"),
        as_line("level2"),
        as_line("level3"),
        GOAL_ENFORCER_BLOCK_END,
    ]
    return "\n".join(lines) + "\n"


def upsert_goal_enforcer_block(existing: str, config: dict[str, bool]) -> str:
    if existing is None:
        existing = ""

    block = render_goal_enforcer_block(config)

    start = existing.find(GOAL_ENFORCER_BLOCK_START)
    end = existing.find(GOAL_ENFORCER_BLOCK_END)

    if start != -1 and end != -1 and end > start:
        end_inclusive = end + len(GOAL_ENFORCER_BLOCK_END)
        before = existing[:start].rstrip("\n")
        after = existing[end_inclusive:].lstrip("\n")
        stitched = "\n\n".join([p for p in (before, block.strip("\n"), after) if p])
        return stitched.rstrip("\n") + "\n"

    base = existing.rstrip("\n")
    if base:
        base += "\n\n"
    base += "# Memento Rules\n\n"
    base += "## Goal Enforcer\n\n"
    base += block
    return base.rstrip("\n") + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python -m pytest tests/test_enforcement_rules.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add memento/enforcement_rules.py tests/test_enforcement_rules.py
git commit -m "feat: add markdown rules file parser for goal enforcer"
```

---

### Task 2: Implement hybrid persistence in `memento/mcp_server.py` (settings.json + `.memento.rules.md`)

**Files:**
- Modify: `memento/mcp_server.py`
- Test: `tests/test_goal_enforcer_persistence.py`

- [ ] **Step 1: Write failing integration tests (restart simulation via reload)**

Create `tests/test_goal_enforcer_persistence.py`:

```python
import importlib
import os
import tempfile

import pytest


@pytest.mark.asyncio
async def test_enforcement_config_persists_via_settings_json(monkeypatch):
    with tempfile.TemporaryDirectory() as ws:
        monkeypatch.setenv("MEMENTO_DIR", ws)

        import memento.mcp_server as ms
        importlib.reload(ms)

        await ms.call_tool(
            "memento_configure_enforcement",
            {"level1": True, "level2": True, "level3": False},
        )

        importlib.reload(ms)
        assert ms.ENFORCEMENT_CONFIG["level1"] is True
        assert ms.ENFORCEMENT_CONFIG["level2"] is True
        assert ms.ENFORCEMENT_CONFIG["level3"] is False


def test_rules_file_overrides_settings_json(monkeypatch):
    with tempfile.TemporaryDirectory() as ws:
        monkeypatch.setenv("MEMENTO_DIR", ws)

        settings_dir = os.path.join(ws, ".memento")
        os.makedirs(settings_dir, exist_ok=True)
        with open(os.path.join(settings_dir, "settings.json"), "w") as f:
            f.write('{"enforcement_config": {"level1": false, "level2": false, "level3": false}}')

        with open(os.path.join(ws, ".memento.rules.md"), "w") as f:
            f.write(
                "\\n".join(
                    [
                        "# Memento Rules",
                        "<!-- memento:goal-enforcer:start -->",
                        "level1: true",
                        "level2: false",
                        "level3: true",
                        "<!-- memento:goal-enforcer:end -->",
                        "",
                    ]
                )
            )

        import memento.mcp_server as ms
        importlib.reload(ms)
        assert ms.ENFORCEMENT_CONFIG["level1"] is True
        assert ms.ENFORCEMENT_CONFIG["level3"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_goal_enforcer_persistence.py -v
```

Expected: FAIL because `.memento.rules.md` is not loaded from workspace root (and/or no override precedence).

- [ ] **Step 3: Update `memento/mcp_server.py` to support the new rules location + backwards compatibility**

Make these changes in `memento/mcp_server.py`:

1) Import helpers:

```python
from memento.enforcement_rules import (
    extract_goal_enforcer_config_from_rules_md,
    upsert_goal_enforcer_block,
)
```

2) Standardize paths:

```python
def _settings_path() -> str:
    return os.path.join(workspace, ".memento", "settings.json")


def _rules_paths() -> list[str]:
    return [
        os.path.join(workspace, ".memento.rules.md"),
        os.path.join(workspace, ".memento", "memento.rules.md"),  # legacy
    ]
```

3) Replace current rules parsing in `load_enforcement_config()` with:

```python
def load_enforcement_config():
    global ENFORCEMENT_CONFIG

    settings_path = _settings_path()
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r") as f:
                data = json.load(f)
                config = data.get("enforcement_config", {})
                if isinstance(config, dict):
                    ENFORCEMENT_CONFIG.update(
                        {k: bool(v) for k, v in config.items() if k in ENFORCEMENT_CONFIG}
                    )
        except Exception as e:
            logger.error(f"Failed to load enforcement config from {settings_path}: {e}")

    for rules_path in _rules_paths():
        if not os.path.exists(rules_path):
            continue
        try:
            with open(rules_path, "r") as f:
                parsed = extract_goal_enforcer_config_from_rules_md(f.read())
                ENFORCEMENT_CONFIG.update(parsed)
            break
        except Exception as e:
            logger.error(f"Failed to load rules file: {e}")
```

4) Extend `save_enforcement_config()` to also upsert the rules file in workspace root:

```python
def save_enforcement_config():
    settings_path = _settings_path()
    try:
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        data: dict[str, Any] = {}
        if os.path.exists(settings_path):
            with open(settings_path, "r") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = {}
        data["enforcement_config"] = ENFORCEMENT_CONFIG
        with open(settings_path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save enforcement config to {settings_path}: {e}")

    rules_path = os.path.join(workspace, ".memento.rules.md")
    try:
        existing = ""
        if os.path.exists(rules_path):
            with open(rules_path, "r") as f:
                existing = f.read()
        updated = upsert_goal_enforcer_block(existing, ENFORCEMENT_CONFIG)
        with open(rules_path, "w") as f:
            f.write(updated)
    except Exception as e:
        logger.error(f"Failed to save rules file to {rules_path}: {e}")
```

5) Update `memento_status` to show `.memento.rules.md` in workspace root and legacy file separately:

```python
rules_path = os.path.join(workspace, ".memento.rules.md")
legacy_rules_path = os.path.join(workspace, ".memento", "memento.rules.md")
status_lines.append(f"- .memento.rules.md: {rules_path} ({'present' if os.path.exists(rules_path) else 'missing'})")
status_lines.append(f"- legacy rules: {legacy_rules_path} ({'present' if os.path.exists(legacy_rules_path) else 'missing'})")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python -m pytest tests/test_goal_enforcer_persistence.py -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run:

```bash
python -m pytest tests/ -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add memento/mcp_server.py tests/test_goal_enforcer_persistence.py
git commit -m "feat: persist goal enforcer config with workspace .memento.rules.md"
```

---

### Task 3: Make persistence observable + safe defaults (status + docs)

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a short documentation section**

Add to `README.md` a section describing:

```markdown
### Goal Enforcer persistence

Memento persists the Goal Enforcer tri-state in:

- `.memento/settings.json` (machine state)
- `.memento.rules.md` (human-editable rules file, workspace root)

On startup Memento loads defaults → settings.json → rules file (rules file overrides).
```

- [ ] **Step 2: Run formatting + lint**

Run:

```bash
ruff format .
ruff check .
```

Expected: no issues.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document goal enforcer persistence and rules file"
```

---

## Self-review checklist (plan author)

- Coverage: handles restart persistence, user-editable file, override precedence, and backward compatibility for legacy rules path.
- No placeholder scan: every task contains explicit code blocks, exact commands, and expected outcomes.
- Type consistency: `ENFORCEMENT_CONFIG` is always `dict[str, bool]` and updated through a single parser/upserter module.
