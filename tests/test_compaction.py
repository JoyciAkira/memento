"""Tests for the token-friendly compaction engine (memento.compaction)."""

from memento.compaction import (
    compact,
    estimate_tokens,
    STRATEGIES,
)


def test_strategies_exist():
    assert set(STRATEGIES) == {"truncate", "caveman", "graphify", "ponytail"}


def test_empty_and_none():
    assert compact("") == ""
    assert compact("   ") == ""


def test_truncate_respects_budget():
    text = "word " * 200
    out = compact(text, strategy="truncate", max_tokens=20)
    assert estimate_tokens(out) <= 20


def test_caveman_strips_articles_and_filler():
    text = "The authentication middleware is actually failing because of the token expiry check."
    out = compact(text, strategy="caveman", max_tokens=200)
    assert "actually" not in out
    assert "the " not in out.lower() or "the token" not in out.lower()
    # technical substance preserved
    assert "authentication" in out.lower()
    assert "token" in out.lower()
    assert "expiry" in out.lower()


def test_caveman_preserves_code_blocks():
    text = "You should wrap the call in useMemo like this:\n```js\nconst x = compute();\n```"
    out = compact(text, strategy="caveman", max_tokens=200)
    assert "```js" in out
    assert "const x = compute();" in out


def test_caveman_preserves_urls_and_paths():
    text = "See https://example.com/docs/api and the file /src/auth/middleware.py for details."
    out = compact(text, strategy="caveman", max_tokens=200)
    assert "https://example.com/docs/api" in out
    assert "/src/auth/middleware.py" in out


def test_graphify_compacts_to_entity_sketch():
    text = "The React component re-renders because the inline object creates a new reference each render."
    out = compact(text, strategy="graphify", max_tokens=60)
    assert out.startswith("▸")
    # entity sketch should be shorter than the source
    assert len(out) < len(text)


def test_ponytail_keeps_tail():
    text = "First we analyzed the auth flow. The bug is in the token expiry comparison using < instead of <=."
    out = compact(text, strategy="ponytail", max_tokens=120)
    # tail sentence preserved
    assert "token expiry" in out.lower()


def test_unknown_strategy_falls_back_safe():
    text = "Hello world this is a test of the fallback path."
    out = compact(text, strategy="does-not-exist", max_tokens=50)
    assert isinstance(out, str)


def test_caveman_reduces_tokens_vs_plain():
    text = (
        "Actually, I would recommend that you should basically ensure that "
        "the component does not re-render unnecessarily because of the inline object."
    )
    plain = compact(text, strategy="truncate", max_tokens=200)
    cav = compact(text, strategy="caveman", max_tokens=200)
    assert estimate_tokens(cav) < estimate_tokens(plain)
