import asyncio
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class RetrievalResult:
    id: str
    memory: str
    score: float
    tier: str
    relations: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class ReflectionReport:
    query: str
    confidence: float
    strategy: str
    result_count: int
    self_healed: bool
    recommendation: str

class MetacognitiveReflector:
    """
    Monitors retrieval confidence and triggers self-healing when uncertainty is high.
    Implements the Monitor -> Evaluate -> Regulate cycle (inspired by Metagent-P).
    """
    CONFIDENCE_THRESHOLD = 0.6

    def __init__(self, provider=None, hdc_encoder=None):
        self.provider = provider
        self.hdc = hdc_encoder
        self._retrieval_history: List[ReflectionReport] = []
        self._strategy = "standard"

    async def reflect(
        self,
        query: str,
        results: List[RetrievalResult],
        confidence: float
    ) -> ReflectionReport:
        report = ReflectionReport(
            query=query,
            confidence=confidence,
            strategy=self._strategy,
            result_count=len(results),
            self_healed=False,
            recommendation=""
        )

        if confidence < self.CONFIDENCE_THRESHOLD:
            report.self_healed = True
            report.strategy = "self_healed"
            self._strategy = "expanded"

            if self.hdc and results:
                expanded = await self._expand_with_hdc(query, results)
                report.result_count = len(expanded)
                report.recommendation = f"HDC expanded from {len(results)} to {len(expanded)} results"
            else:
                report.recommendation = "Low confidence but no HDC encoder available"
        else:
            self._strategy = "standard"
            report.recommendation = "Confidence acceptable, using standard retrieval"

        self._retrieval_history.append(report)
        return report

    async def _expand_with_hdc(
        self,
        query: str,
        results: List[RetrievalResult]
    ) -> List[RetrievalResult]:
        if not self.hdc or not results:
            return results

        try:
            expanded: List[RetrievalResult] = []
            seen_ids = {r.id for r in results}
            expanded.extend(results)

            for result in results:
                try:
                    words = result.memory.lower().split()
                    for word in words[:3]:
                        if len(word) < 4:
                            continue
                        related = self.hdc.decode_relation(
                            self.hdc.concept(word), top_k=5
                        )
                        for name, sim_score in related:
                            if sim_score > 0.7 and name != word:
                                new_result = RetrievalResult(
                                    id=f"hdc-{name}",
                                    memory=f"HDC related: {name}",
                                    score=sim_score * 0.8,
                                    tier="hdc_expanded"
                                )
                                if new_result.id not in seen_ids:
                                    expanded.append(new_result)
                                    seen_ids.add(new_result.id)
                except Exception:
                    continue

            return expanded
        except Exception as e:
            logger.warning(f"HDC expansion failed: {e}")
            return results

    async def evaluate_confidence(
        self,
        results: List[RetrievalResult],
        query: str
    ) -> float:
        if not results:
            return 0.0

        avg_score = sum(r.score for r in results) / len(results)
        score_variance = sum((r.score - avg_score) ** 2 for r in results) / len(results)
        diversity = len(set(r.memory.lower()[:20] for r in results)) / len(results)
        consistency = 1.0 - min(1.0, score_variance)

        confidence = (avg_score * 0.5) + (diversity * 0.3) + (consistency * 0.2)
        return min(1.0, max(0.0, confidence))

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_reflections": len(self._retrieval_history),
            "self_healed_count": sum(1 for r in self._retrieval_history if r.self_healed),
            "current_strategy": self._strategy,
            "avg_confidence": (
                sum(r.confidence for r in self._retrieval_history) / len(self._retrieval_history)
                if self._retrieval_history else 0.0
            )
        }
