from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict


@dataclass(frozen=True)
class Candidate:
    memory_id: str
    score: float
    lane: str
    evidence: dict[str, Any]


class LaneTrace(TypedDict):
    lane: str
    considered: int
    returned: int
    top: list[dict[str, Any]]


class ContextBundle(TypedDict):
    query: str
    results: list[dict[str, Any]]
    facts: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    traces: list[LaneTrace]
