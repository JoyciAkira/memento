from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable

logger = logging.getLogger(__name__)
_MAX_REGEX_LENGTH = 1024


@dataclass(frozen=True)
class HardRule:
    id: str
    path_globs: tuple[str, ...]
    kind: str
    regex: str | None
    language: str | None
    query: str | None
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
    line: int | None = None
    column: int | None = None


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
        kind = _as_str(item.get("kind")) or "regex"
        regex = _as_str(item.get("regex"))
        language = _as_str(item.get("language"))
        query = _as_str(item.get("query"))
        message = _as_str(item.get("message")) or ""
        severity = _as_str(item.get("severity")) or "block"
        enabled = _as_bool(item.get("enabled"), True)
        override_token = _as_str(item.get("override_token")) or default_override_token

        if kind not in {"regex", "tree-sitter"}:
            continue

        if rule_id is None or path_globs is None:
            continue
        if kind == "regex":
            if regex is None:
                continue
            if len(regex) > _MAX_REGEX_LENGTH:
                continue
            try:
                re.compile(regex)
            except re.error:
                continue
        else:
            if language is None or query is None:
                continue

        if severity not in {"block", "warn"}:
            severity = "block"

        rules.append(
            HardRule(
                id=rule_id,
                path_globs=tuple(path_globs),
                kind=kind,
                regex=regex,
                language=language,
                query=query,
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


_ts_cache: dict[str, tuple[Any, Any]] = {}

def _get_tree_sitter(language_name: str) -> tuple[Any, Any]:
    cached = _ts_cache.get(language_name)
    if cached is not None:
        return cached

    from tree_sitter import Language, Parser

    if language_name == "python":
        import tree_sitter_python as tspython
        lang = Language(tspython.language())
    elif language_name in {"javascript", "js"}:
        import tree_sitter_javascript as tsjavascript
        lang = Language(tsjavascript.language())
    elif language_name in {"typescript", "ts"}:
        import tree_sitter_typescript as tstypescript
        lang = Language(tstypescript.language_typescript())
    else:
        raise ValueError(f"Unsupported tree-sitter language: {language_name}")

    parser = Parser(lang)
    _ts_cache[language_name] = (parser, lang)
    return parser, lang


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
        if rule.kind == "regex":
            if not rule.regex:
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
            continue

        line = None
        column = None
        try:
            from tree_sitter import Query, QueryCursor
            parser, language = _get_tree_sitter(rule.language or "")
            tree = parser.parse(content.encode("utf-8", errors="replace"))
            query = Query(language, rule.query or "")
            cursor = QueryCursor(query)
            captures = cursor.captures(tree.root_node)
            node = None
            if isinstance(captures, dict):
                for nodes in captures.values():
                    if nodes:
                        node = nodes[0]
                        break
            elif isinstance(captures, list) and captures:
                node = captures[0][0]
            if node is None:
                continue
            if hasattr(node, "start_point"):
                line = int(node.start_point[0]) + 1
                column = int(node.start_point[1]) + 1
        except Exception:
            continue
        violations.append(
            Violation(
                rule_id=rule.id,
                file=file_path,
                message=rule.message,
                severity=rule.severity,
                line=line,
                column=column,
            )
        )

    return violations
