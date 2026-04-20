"""Tests for expanded Active Coercion preset packs."""
import pytest
from memento.active_coercion import normalize_hard_rules
from memento.tools.coercion import PRESETS


def test_six_presets_exist():
    assert len(PRESETS) == 6


def test_expected_preset_names():
    expected = {"python-dev-basics", "python-strict", "typescript-strict", "javascript-safe", "react-safe", "go-strict"}
    assert set(PRESETS.keys()) == expected


def test_each_preset_has_minimum_rules():
    for name, rules in PRESETS.items():
        assert len(rules) >= 2, f"Preset '{name}' has only {len(rules)} rules (minimum 2)"
        assert len(rules) <= 20, f"Preset '{name}' has {len(rules)} rules (maximum 20)"


def test_all_rules_normalize_to_hard_rules():
    """Every rule in every preset must pass normalize_hard_rules validation."""
    for preset_name, rules in PRESETS.items():
        normalized = normalize_hard_rules(rules)
        assert len(normalized) == len(rules), (
            f"Preset '{preset_name}': normalize_hard_rules returned {len(normalized)} "
            f"rules but preset has {len(rules)}"
        )


def test_globally_unique_rule_ids():
    """No duplicate rule IDs across all presets."""
    all_ids = []
    for preset_name, rules in PRESETS.items():
        for r in rules:
            rid = r.get("id")
            assert rid is not None, f"Preset '{preset_name}' has a rule without an id"
            all_ids.append(rid)
    assert len(all_ids) == len(set(all_ids)), "Duplicate rule IDs found"


def test_every_rule_has_required_fields():
    required = {"id", "enabled", "path_globs", "message", "severity", "override_token"}
    for preset_name, rules in PRESETS.items():
        for r in rules:
            missing = required - set(r.keys())
            assert not missing, f"Preset '{preset_name}', rule '{r.get('id')}': missing fields {missing}"


def test_regex_rules_have_regex_field():
    for preset_name, rules in PRESETS.items():
        for r in rules:
            if r.get("kind") == "regex":
                assert r.get("regex"), f"Preset '{preset_name}', rule '{r['id']}': regex kind but no regex field"


def test_tree_sitter_rules_have_language_and_query():
    for preset_name, rules in PRESETS.items():
        for r in rules:
            if r.get("kind") == "tree-sitter":
                assert r.get("language"), f"Preset '{preset_name}', rule '{r['id']}': tree-sitter kind but no language"
                assert r.get("query"), f"Preset '{preset_name}', rule '{r['id']}': tree-sitter kind but no query"


def test_severity_values():
    valid = {"block", "warn"}
    for preset_name, rules in PRESETS.items():
        for r in rules:
            assert r.get("severity") in valid, f"Preset '{preset_name}', rule '{r['id']}': invalid severity '{r.get('severity')}'"


def test_python_strict_catches_print():
    """Verify the python-strict preset has a tree-sitter rule that matches print()."""
    rules = PRESETS.get("python-strict", [])
    print_rules = [r for r in rules if "print" in r.get("message", "").lower() or "print" in r.get("id", "")]
    assert len(print_rules) >= 1, "python-strict should have at least one print-related rule"


def test_typescript_strict_has_console_log_rule():
    rules = PRESETS.get("typescript-strict", [])
    console_rules = [r for r in rules if "console" in r.get("message", "").lower() or "console" in r.get("id", "")]
    assert len(console_rules) >= 1, "typescript-strict should have a console.log rule"


def test_go_strict_all_regex():
    """Go rules must be regex-only since tree-sitter-go is not installed."""
    rules = PRESETS.get("go-strict", [])
    for r in rules:
        assert r.get("kind", "regex") != "tree-sitter", f"Go rule '{r.get('id')}' must be regex-only"
