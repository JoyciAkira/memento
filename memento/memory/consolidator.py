import asyncio
import logging
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
from dataclasses import dataclass, field

from memento.memory.active_inference import ActiveInferenceEngine, Prediction, PredictionResult
from memento.memory.orchestrator import MemoryOrchestrator
from memento.llm_client import get_llm_client

logger = logging.getLogger(__name__)

@dataclass
class ConsolidationResult:
    memory_id: str
    content: str
    tier: str
    was_surprising: bool
    prediction_error: float
    timestamp: str

class LLMPredictor:
    """
    Uses an LLM to generate semantically meaningful predictions.
    Wraps the event in context and asks for likely outcomes.
    """
    PREDICTOR_PROMPT = (
        "You are a predictor. Given an event, predict the most likely outcome. "
        "Reply ONLY with a brief prediction (1 sentence). Be specific and concise.\n\n"
        "Event: {event}\nPrediction:"
    )

    def __init__(self, llm_client=None, model: str = "openai/gpt-4o-mini"):
        self._llm = llm_client
        self._model = model

    def set_client(self, llm_client) -> None:
        self._llm = llm_client

    async def predict(self, event: str) -> Prediction:
        if not self._llm:
            return Prediction(content=event, expected_outcome=event.lower(), confidence=0.5)

        try:
            response = await self._llm.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": self.PREDICTOR_PROMPT.format(event=event)}],
                max_tokens=64,
                temperature=0.3,
            )
            expected = response.choices[0].message.content.strip()
            return Prediction(content=event, expected_outcome=expected, confidence=0.8)
        except Exception as e:
            logger.warning(f"LLM predictor failed: {e}, falling back to dummy")
            return Prediction(content=event, expected_outcome=event.lower(), confidence=0.3)


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
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._llm_predictor = LLMPredictor()

    def set_llm_client(self, llm_client) -> None:
        self._llm_predictor.set_client(llm_client)

    async def predict_outcome(self, event: str) -> Prediction:
        return await self._llm_predictor.predict(event)

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
        pred = await self._llm_predictor.predict(event)
        self._engine._predictions[event] = pred

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

    async def start_streaming(self) -> None:
        """Start background processing of queued events."""
        self._running = True
        asyncio.create_task(self._process_queue())

    async def stop_streaming(self) -> None:
        self._running = False

    async def enqueue_event(
        self,
        event: str,
        actual_outcome: Optional[str] = None
    ) -> None:
        """Add an event to the processing queue."""
        await self._event_queue.put((event, actual_outcome))

    async def _process_queue(self) -> None:
        """Background worker that processes queued events."""
        while self._running:
            try:
                event, actual = await asyncio.wait_for(
                    self._event_queue.get(), timeout=1.0
                )
                await self.process_event(event, actual)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing queued event: {e}")

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
            "queue_depth": self._event_queue.qsize(),
            "streaming_active": self._running,
            "recent_events": [
                {"content": c.content, "tier": c.tier, "surprise": c.was_surprising}
                for c in self._consolidation_log[-10:]
            ]
        }
