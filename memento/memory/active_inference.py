import logging
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class Prediction:
    content: str
    expected_outcome: str
    confidence: float

@dataclass
class PredictionResult:
    actual: str
    expected: str
    prediction_error: float
    is_surprise: bool
    timestamp: str

class ActiveInferenceEngine:
    """
    Implements surprise-guided memory retention via the Free Energy Principle.
    Only events with high prediction error (surprise) are consolidated into memory.
    This prevents memory bloat from predictable, redundant events.
    """
    SURPRISE_THRESHOLD = 0.5

    def __init__(self, predictor_fn: Optional[Callable[[str], Prediction]] = None):
        self._predictor_fn = predictor_fn
        self._predictions: Dict[str, Prediction] = {}
        self._history: List[PredictionResult] = []

    def register_predictor(self, fn: Callable[[str], Prediction]) -> None:
        self._predictor_fn = fn

    async def predict(self, event: str) -> Prediction:
        if self._predictor_fn:
            pred = await self._predictor_fn(event)
        else:
            pred = Prediction(
                content=event,
                expected_outcome=event.lower(),
                confidence=0.5
            )
        self._predictions[event] = pred
        return pred

    async def evaluate(self, event: str, actual_outcome: str) -> PredictionResult:
        pred = self._predictions.get(event)
        if not pred:
            pred = await self.predict(event)

        error = self._compute_prediction_error(pred.expected_outcome, actual_outcome)
        is_surprise = error > self.SURPRISE_THRESHOLD

        result = PredictionResult(
            actual=actual_outcome,
            expected=pred.expected_outcome,
            prediction_error=error,
            is_surprise=is_surprise,
            timestamp=datetime.now().isoformat()
        )
        self._history.append(result)
        return result

    def _compute_prediction_error(self, expected: str, actual: str) -> float:
        if expected == actual:
            return 0.0
        exp_words = set(expected.lower().split())
        act_words = set(actual.lower().split())
        if not exp_words:
            return 1.0
        overlap = len(exp_words & act_words)
        return 1.0 - (overlap / max(len(exp_words), len(act_words)))

    def should_consolidate(self, result: PredictionResult) -> bool:
        return result.is_surprise

    def get_stats(self) -> Dict[str, Any]:
        total = len(self._history)
        surprises = sum(1 for r in self._history if r.is_surprise)
        avg_error = (
            sum(r.prediction_error for r in self._history) / total
            if total > 0 else 0.0
        )
        return {
            "total_events": total,
            "surprises": surprises,
            "predictable": total - surprises,
            "surprise_rate": round(surprises / max(total, 1), 3),
            "avg_prediction_error": round(avg_error, 3),
        }

    def clear_history(self) -> None:
        self._history.clear()
        self._predictions.clear()
