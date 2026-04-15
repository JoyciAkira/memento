from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable


@dataclass(frozen=True)
class HardRule:
    id: str
    path_globs: tuple[str, ...]
    regex: str
    message: str
    severity: str
    enabled: bool
    override_token: str


@dataclass(frozen=True)
class Violation:
    rule_id: str
    file: str
    message: str
    severity: str


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _as_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _as_list_of_str(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    out: list[str] = []
    for v in value:
        s = _as_str(v)
        if s is None:
            return None
        out.append(s)
    return out


def normalize_hard_rules(raw_rules: Any, *, default_override_token: str = "memento-override") -> list[HardRule]:
    if raw_rules is None:
        return []
    if not isinstance(raw_rules, list):
        return []

    rules: list[HardRule] = []
    for item in raw_rules:
        if not isinstance(item, dict):
            continue
        rule_id = _as_str(item.get("id"))
        path_globs = _as_list_of_str(item.get("path_globs"))
        regex = _as_str(item.get("regex"))
        message = _as_str(item.get("message")) or ""
        severity = _as_str(item.get("severity")) or "block"
        enabled = _as_bool(item.get("enabled"), True)
        override_token = _as_str(item.get("override_token")) or default_override_token

        if rule_id is None or path_globs is None or regex is None:
            continue

        try:
            re.compile(regex)
        except re.error:
            continue

        if severity not in {"block", "warn"}:
            severity = "block"

        rules.append(
            HardRule(
                id=rule_id,
                path_globs=tuple(path_globs),
                regex=regex,
                message=message,
                severity=severity,
                enabled=enabled,
                override_token=override_token,
            )
        )

    return rules


def file_matches_globs(file_relpath: str, globs: Iterable[str]) -> bool:
    normalized = file_relpath.replace(os.sep, "/")
    path = PurePosixPath(normalized)
    for g in globs:
        candidates = [g]
        cur = g
        while "**/" in cur:
            cur = cur.replace("**/", "", 1)
            candidates.append(cur)
        for c in candidates:
            if path.match(c):
                return True
    return False


def check_text_against_rules(
    *,
    workspace_root: str,
    rules: Iterable[HardRule],
    file_path: str,
    content: str,
) -> list[Violation]:
    rel = os.path.relpath(file_path, workspace_root)
    rel_norm = rel.replace(os.sep, "/")

    violations: list[Violation] = []
    for rule in rules:
        if not rule.enabled:
            continue
        if not file_matches_globs(rel_norm, rule.path_globs):
            continue
        if rule.override_token and rule.override_token in content:
            continue
        if re.search(rule.regex, content, flags=re.MULTILINE) is None:
            continue
        violations.append(
            Violation(
                rule_id=rule.id,
                file=file_path,
                message=rule.message,
                severity=rule.severity,
            )
        )

    return violations
