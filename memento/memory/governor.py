from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class MemorySignal:
    memory_id: str
    strength: float
    semantic_similarity: float = 0.0
    vsa_resonance: float = 0.0
    recency: float = 0.0
    hit_frequency: float = 0.0
    surprise: float = 0.0
    redundancy_penalty: float = 0.0
    staleness_penalty: float = 0.0


@dataclass(frozen=True)
class TriggerDecision:
    should_inject: bool
    should_prefetch: bool
    should_consolidate: bool
    should_notify: bool
    reason: str
    strength: float


class MemoryGovernor:
    """Scores memories and decides when background memory work is worth spending budget."""

    def __init__(
        self,
        inject_threshold: float = 0.85,
        prefetch_threshold: float = 0.60,
        consolidate_threshold: float = 0.72,
        notify_threshold: float = 0.90,
    ):
        self.inject_threshold = inject_threshold
        self.prefetch_threshold = prefetch_threshold
        self.consolidate_threshold = consolidate_threshold
        self.notify_threshold = notify_threshold

    def score(
        self,
        *,
        memory_id: str,
        semantic_similarity: float = 0.0,
        vsa_resonance: float = 0.0,
        created_at: str | None = None,
        last_accessed_at: str | None = None,
        hit_count: int = 0,
        surprise: float = 0.0,
        redundancy: float = 0.0,
    ) -> MemorySignal:
        recency = self._recency_score(last_accessed_at or created_at)
        hit_frequency = min(1.0, math.log1p(max(0, hit_count)) / math.log(16))
        staleness = max(0.0, 1.0 - recency) * 0.15
        redundancy_penalty = min(0.25, max(0.0, redundancy) * 0.25)
        strength = (
            0.30 * self._clamp(semantic_similarity)
            + 0.30 * self._clamp(vsa_resonance)
            + 0.15 * recency
            + 0.15 * hit_frequency
            + 0.15 * self._clamp(surprise)
            - redundancy_penalty
            - staleness
        )
        return MemorySignal(
            memory_id=memory_id,
            strength=self._clamp(strength),
            semantic_similarity=self._clamp(semantic_similarity),
            vsa_resonance=self._clamp(vsa_resonance),
            recency=recency,
            hit_frequency=hit_frequency,
            surprise=self._clamp(surprise),
            redundancy_penalty=redundancy_penalty,
            staleness_penalty=staleness,
        )

    def decide(self, signal: MemorySignal, *, novelty: float = 0.0, conflict: float = 0.0) -> TriggerDecision:
        should_inject = signal.strength >= self.inject_threshold
        should_prefetch = signal.strength >= self.prefetch_threshold
        should_consolidate = (
            signal.strength >= self.consolidate_threshold
            or signal.surprise >= 0.65
            or novelty >= 0.75
        )
        should_notify = signal.strength >= self.notify_threshold or conflict >= 0.70
        reason = "low_signal"
        if should_notify:
            reason = "notify"
        elif should_inject:
            reason = "inject"
        elif should_consolidate:
            reason = "consolidate"
        elif should_prefetch:
            reason = "prefetch"
        return TriggerDecision(
            should_inject=should_inject,
            should_prefetch=should_prefetch,
            should_consolidate=should_consolidate,
            should_notify=should_notify,
            reason=reason,
            strength=signal.strength,
        )

    def annotate_results(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        annotated: list[dict[str, Any]] = []
        for r in results:
            signal = self.score(
                memory_id=str(r.get("id", "")),
                semantic_similarity=float(r.get("score", 0.0) or 0.0),
                vsa_resonance=float(r.get("vsa_score", 0.0) or 0.0),
                created_at=r.get("created_at"),
                hit_count=int(r.get("hit_count", 0) or 0),
                surprise=float(r.get("prediction_error", 0.0) or 0.0),
            )
            decision = self.decide(signal)
            nr = dict(r)
            nr["strength"] = signal.strength
            nr["memory_signal"] = signal.__dict__
            nr["trigger"] = decision.__dict__
            annotated.append(nr)
        return sorted(annotated, key=lambda x: x.get("strength", 0.0), reverse=True)

    def _recency_score(self, iso: str | None) -> float:
        if not iso:
            return 0.0
        try:
            dt = datetime.fromisoformat(str(iso))
        except Exception:
            return 0.0
        age_hours = max(0.0, (datetime.now() - dt).total_seconds() / 3600)
        return float(math.exp(-age_hours / (24 * 14)))

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, float(value)))
