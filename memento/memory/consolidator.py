import asyncio
import logging
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
from dataclasses import dataclass, field

from memento.memory.active_inference import ActiveInferenceEngine, Prediction, PredictionResult
from memento.memory.orchestrator import MemoryOrchestrator
from memento.memory.l2_episodic import L2EpisodicMemory
from memento.memory.l3_semantic import L3SemanticMemory

logger = logging.getLogger(__name__)

@dataclass
class ConsolidationResult:
    memory_id: str
    content: str
    tier: str
    was_surprising: bool
    prediction_error: float
    timestamp: str

class CognitiveConsolidator:
    """
    Orchestrates the full Active Inference lifecycle:
    predict -> evaluate -> consolidate (only surprising events).

    Runs as a background process that monitors events,
    evaluates prediction errors, and routes surprising events
    to the appropriate memory tier for long-term storage.
    """
    DEFAULT_PREDICTOR_PROMPT = (
        "Given this event: '{event}'. "
        "Predict the most likely outcome in one short sentence. "
        "Be concise and specific."
    )

    def __init__(
        self,
        orchestrator: MemoryOrchestrator,
        predictor_fn: Optional[Callable[[str], Prediction]] = None,
        surprise_threshold: float = 0.5
    ):
        self._orchestrator = orchestrator
        self._engine = ActiveInferenceEngine(predictor_fn=predictor_fn)
        self._surprise_threshold = surprise_threshold
        self._pending_events: List[str] = []
        self._consolidation_log: List[ConsolidationResult] = []
        self._running = False

    async def predict_outcome(self, event: str) -> Prediction:
        return await self._engine.predict(event)

    async def process_event(
        self,
        event: str,
        actual_outcome: Optional[str] = None,
        force_consolidate: bool = False
    ) -> ConsolidationResult:
        """
        Full lifecycle: predict -> evaluate -> consolidate.

        If actual_outcome is None, we only predict (monitoring phase).
        If actual_outcome is provided, we evaluate and potentially consolidate.
        """
        await self._engine.predict(event)

        if actual_outcome is None:
            return ConsolidationResult(
                memory_id="",
                content=event,
                tier="",
                was_surprising=False,
                prediction_error=0.0,
                timestamp=datetime.now().isoformat()
            )

        result = await self._engine.evaluate(event, actual_outcome)
        should_store = force_consolidate or result.is_surprise

        tier = "semantic" if should_store else "working"

        memory_id = ""
        if should_store:
            memory_id = self._orchestrator.add(
                content=f"[SURPRISE] {event} | Expected: {result.expected} | Actual: {result.actual} | Error: {round(result.prediction_error, 3)}",
                metadata={
                    "prediction_error": result.prediction_error,
                    "expected": result.expected,
                    "actual": result.actual,
                    "surprise": result.is_surprise,
                    "event": event,
                },
                tier=tier
            )

        consolidation = ConsolidationResult(
            memory_id=memory_id,
            content=event,
            tier=tier,
            was_surprising=result.is_surprise,
            prediction_error=result.prediction_error,
            timestamp=datetime.now().isoformat()
        )
        self._consolidation_log.append(consolidation)
        return consolidation

    async def batch_process(
        self,
        events: List[Dict[str, str]]
    ) -> List[ConsolidationResult]:
        """
        Process a batch of events. Each event dict should have:
        - 'event': the event description
        - 'actual': the actual outcome (optional)
        """
        results = []
        for item in events:
            result = await self.process_event(
                event=item["event"],
                actual_outcome=item.get("actual"),
                force_consolidate=item.get("force", False)
            )
            results.append(result)
        return results

    def get_consolidation_stats(self) -> Dict[str, Any]:
        ai_stats = self._engine.get_stats()
        return {
            **ai_stats,
            "total_processed": len(self._consolidation_log),
            "stored_to_semantic": sum(
                1 for c in self._consolidation_log if c.tier == "semantic"
            ),
            "stored_to_working": sum(
                1 for c in self._consolidation_log if c.tier == "working"
            ),
            "recent_events": [
                {"content": c.content, "tier": c.tier, "surprise": c.was_surprising}
                for c in self._consolidation_log[-10:]
            ]
        }
