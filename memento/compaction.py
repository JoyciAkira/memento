"""Token-friendly context compaction for Memento's proactive injection.

This module compresses natural-language text (typically retrieved memories that
Memento injects into the agent context on every tool call) so the injected block
stays small in tokens while preserving technical substance (code, URLs, paths).

It is intentionally dependency-free and deterministic. The ``caveman`` strategy
ports the *rule-based* cleanup rules from the MIT-licensed
``caveman-compress`` skill (https://github.com/JuliusBrussee/caveman,
Copyright (c) 2026 Julius Brussee, MIT License): it strips articles/filler/
hedging/politeness/connective fluff and collapses redundant phrasing, while
leaving code, URLs and file paths byte-for-byte intact.

``graphify`` and ``ponytail`` are native Memento heuristics. Upstream they are
"compression primitives" from the caveman.so ecosystem (same team behind Caveman,
per the caveman.so meta description) and are deterministic — **no LLM required**,
matching the user's expectation. Their exact public spec is not available (the
caveman.so/graphify and /ponytail routes 404 and there is no public source),
so these are reasonable token-light approximations that can be refined later.

The optional ``caveman-llm`` mode (full LLM compression) is intentionally NOT
implemented here: it would add one LLM call per injection (latency + cost +
API-key dependency) on a hot path that must stay offline. It can be added later
as an opt-in strategy that reuses ``MEM0_MODEL``.
"""

from __future__ import annotations

import re
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Token estimation (cheap heuristic: ~4 chars / token for English code+prose)
# ---------------------------------------------------------------------------
def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Span protection: keep code / URLs / paths byte-exact
# ---------------------------------------------------------------------------
_PLACEHOLDER = "\x00{idx}\x00"


def _protect_spans(text: str) -> Tuple[str, List[str]]:
    spans: List[str] = []

    def stash(match: re.Match) -> str:
        spans.append(match.group(0))
        return _PLACEHOLDER.format(idx=len(spans) - 1)

    # fenced code blocks  ```...```
    text = re.sub(r"```[\s\S]*?```", stash, text)
    # inline code  `...`
    text = re.sub(r"`[^`]*`", stash, text)
    # URLs
    text = re.sub(r"https?://\S+", stash, text)
    # file paths: /a/b, ./x, ../x, C:\x
    text = re.sub(r"(?:/|\./|\.\/|[A-Za-z]:\\)[\w./\\-]+", stash, text)
    return text, spans


def _restore_spans(text: str, spans: List[str]) -> str:
    def repl(match: re.Match) -> str:
        idx = int(match.group(1))
        return spans[idx] if 0 <= idx < len(spans) else match.group(0)

    return re.sub(r"\x00(\d+)\x00", repl, text)


# ---------------------------------------------------------------------------
# caveman: deterministic rule-based tersification (MIT caveman-compress rules)
# ---------------------------------------------------------------------------
# Phrase-level collapses (applied before word stripping).
_CAVEMAN_PHRASES = {
    "in order to": "to",
    "so as to": "to",
    "make sure to": "ensure",
    "the reason is because": "because",
    "due to the fact that": "because",
    "in spite of the fact that": "although",
    "for the purpose of": "to",
    "with regard to": "about",
    "in the event that": "if",
    "a number of": "some",
    "the vast majority of": "most",
}

# Standalone filler / hedge / politeness words removed when they are their own token.
_CAVEMAN_WORDS = {
    "a",
    "an",
    "the",
    "just",
    "really",
    "basically",
    "actually",
    "simply",
    "essentially",
    "generally",
    "certainly",
    "sure",
    "perhaps",
    "maybe",
    "possibly",
    "however",
    "furthermore",
    "additionally",
    "moreover",
    "in addition",
    "therefore",
    "thus",
    "hence",
    "namely",
    "specifically",
    "overall",
    "please",
    "thank",
    "thanks",
    "hi",
    "hello",
    "ok",
    "okay",
    "note",
    "noted",
    "also",
    "too",
    "very",
    "quite",
    "rather",
}

# Multi-word pleasantries collapsed to empty.
_CAVEMAN_PHRASES_EMPTY = {
    "happy to",
    "i'd recommend",
    "i would recommend",
    "of course",
    "it might be worth",
    "you could consider",
    "it would be good to",
    "i think",
    "i believe",
    "in my opinion",
    "as you know",
    "as a reminder",
}


def _caveman_text(body: str) -> str:
    # Remove empty-collapsing multi-word pleasantries first.
    for phrase in _CAVEMAN_PHRASES_EMPTY:
        body = re.sub(re.escape(phrase), "", body, flags=re.IGNORECASE)

    # Collapse redundant phrases.
    for phrase, repl in _CAVEMAN_PHRASES.items():
        body = re.sub(re.escape(phrase), repl, body, flags=re.IGNORECASE)

    # Strip standalone filler words (word boundaries, no partial matches).
    # Process lowercased for matching but keep original casing of survivors.
    tokens = re.split(r"(\s+)", body)
    out_tokens: List[str] = []
    for tok in tokens:
        if re.match(r"\s+$", tok):
            out_tokens.append(tok)
            continue
        bare = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", tok).lower()
        if bare in _CAVEMAN_WORDS:
            continue
        out_tokens.append(tok)
    body = "".join(out_tokens)

    # Trim spaces left by removals.
    body = re.sub(r"\s{2,}", " ", body).strip()
    return body


# ---------------------------------------------------------------------------
# graphify: compact entity/relation sketch (native heuristic)
# ---------------------------------------------------------------------------
_STOP = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "your",
    "you",
    "are",
    "was",
    "were",
    "has",
    "have",
    "had",
    "but",
    "not",
    "can",
    "will",
    "when",
    "where",
    "which",
    "while",
    "because",
    "then",
    "than",
    "out",
    "use",
}


def _graphify_text(body: str) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", body.lower())
    ents = [w for w in words if w not in _STOP]
    # de-dup preserving order, keep top 8 entities
    seen = set()
    uniq: List[str] = []
    for w in ents:
        if w not in seen:
            seen.add(w)
            uniq.append(w)
        if len(uniq) >= 5:
            break
    if not uniq:
        return body.strip()
    return "▸ " + " · ".join(uniq)


# ---------------------------------------------------------------------------
# ponytail: keep the tail/essence (native heuristic)
# ---------------------------------------------------------------------------
def _ponytail_text(body: str) -> str:
    # Split into sentences; prefer the last substantive sentence + first entity.
    sentences = re.split(r"(?<=[.!?])\s+", body.strip())
    sentences = [s for s in sentences if len(s) > 3]
    if not sentences:
        return body.strip()
    tail = sentences[-1]
    # Prepend a compact entity hint if the tail alone is thin.
    if len(tail) < 40:
        head_ents = _graphify_text(" ".join(sentences[:-1]))
        if head_ents:
            return f"{head_ents} → {tail}"
    return tail


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
STRATEGIES = ("truncate", "caveman", "graphify", "ponytail")


def compact(text: str, strategy: str = "caveman", max_tokens: int = 60) -> str:
    """Compress ``text`` in-place-safe, keeping it within ``max_tokens``.

    ``strategy``:
      - ``truncate``: hard cut at the token budget (legacy behaviour, refined).
      - ``caveman``:  rule-based tersification (MIT caveman-compress rules).
      - ``graphify``: compact entity sketch (native heuristic).
      - ``ponytail``: keep the tail essence (native heuristic).

    Code blocks, URLs and file paths are always preserved verbatim.
    """
    if not text:
        return ""

    protected, spans = _protect_spans(text)

    if strategy == "truncate":
        body = protected.strip()
    elif strategy == "caveman":
        body = _caveman_text(protected)
    elif strategy == "graphify":
        body = _graphify_text(protected)
    elif strategy == "ponytail":
        body = _ponytail_text(protected)
    else:
        body = protected.strip()

    # Hard token budget (approx). +1 token slack for restored spans.
    budget_chars = max(8, (max_tokens - 1) * 4)
    if estimate_tokens(body) > max_tokens:
        body = body[:budget_chars].rstrip()
        # Avoid cutting mid-token: drop a trailing partial word.
        if " " in body:
            body = body[: body.rfind(" ")]

    return _restore_spans(body, spans).strip()


def compact_memory(text: str, strategy: str = "caveman", max_tokens: int = 60) -> str:
    """Convenience wrapper used by the proactive injection path."""
    return compact(text, strategy=strategy, max_tokens=max_tokens)
