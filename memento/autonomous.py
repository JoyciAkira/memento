"""Autonomous Agent Loop — Memento's proactive intelligence engine.

Runs a background cognitive loop that observes, reasons, and acts without
external prompting. Governed by a configurable autonomy_level (off, passive,
active, autonomous) stored in workspace settings.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Autonomy levels
# ---------------------------------------------------------------------------

class AutonomyLevel(str, Enum):
    OFF = "off"
    PASSIVE = "passive"
    ACTIVE = "active"
    AUTONOMOUS = "autonomous"


LEVEL_DESCRIPTIONS = {
    AutonomyLevel.OFF: "No autonomous behavior. Memento only responds to explicit tool calls.",
    AutonomyLevel.PASSIVE: "Background observation only. Periodically scans for patterns, stale memories, and health issues. No modifications.",
    AutonomyLevel.ACTIVE: "Proactive intelligence. Consolidates memories, extracts KG, generates insights, detects anomalies, and pre-warms caches. Can modify memory but not code.",
    AutonomyLevel.AUTONOMOUS: "Full autonomy. All ACTIVE capabilities plus autonomous dream synthesis, goal drift detection, auto-task generation, workspace health reports, and proactive notifications. Can write reports and todo files.",
}

DEFAULT_INTERVALS = {
    AutonomyLevel.OFF: 0,
    AutonomyLevel.PASSIVE: 300,    # 5 min
    AutonomyLevel.ACTIVE: 120,     # 2 min
    AutonomyLevel.AUTONOMOUS: 60,  # 1 min
}

# ---------------------------------------------------------------------------
# Decision record
# ---------------------------------------------------------------------------

@dataclass
class AutonomousDecision:
    timestamp: str
    level: str
    action: str
    reason: str
    outcome: str
    confidence: float = 0.0
    duration_ms: float = 0.0

# ---------------------------------------------------------------------------
# The autonomous agent
# ---------------------------------------------------------------------------

class AutonomousAgent:
    """Background agent that observes, reasons, and acts proactively."""

    MAX_DECISION_LOG = 200

    def __init__(self, provider, cognitive_engine, workspace_root: str,
                 notification_manager=None, governor=None):
        self.provider = provider
        self.cognitive_engine = cognitive_engine
        self.workspace_root = workspace_root
        self.notification_manager = notification_manager
        self.governor = governor

        self._level = AutonomyLevel.OFF
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._interval: int = 0
        self._decision_log: List[AutonomousDecision] = []
        self._cycle_count = 0
        self._last_cycle_time: Optional[float] = None
        self._stats: Dict[str, Any] = {
            "total_cycles": 0,
            "actions_taken": 0,
            "errors": 0,
            "last_cycle_duration_ms": 0,
        }

    # --- level management ---

    @property
    def level(self) -> AutonomyLevel:
        return self._level

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def set_level(self, level: AutonomyLevel | str) -> None:
        if isinstance(level, str):
            level = AutonomyLevel(level)
        self._level = level
        self._interval = DEFAULT_INTERVALS.get(level, 0)
        logger.info(f"Autonomous agent level set to: {level.value} (interval={self._interval}s)")

    # --- lifecycle ---

    def start(self) -> bool:
        if self._level == AutonomyLevel.OFF or self._interval <= 0:
            logger.info("Autonomous agent not starting: level is OFF")
            return False
        if self.is_running:
            logger.info("Autonomous agent already running")
            return False
        self._running = True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            self._task = loop.create_task(self._loop())
        else:
            try:
                new_loop = asyncio.new_event_loop()
                self._task = new_loop.create_task(self._loop())
                new_loop.run_until_complete(self._task)
            except Exception:
                self._running = False
                self._task = None
                logger.warning("Could not start autonomous agent: no event loop available")
                return False
        logger.info(f"Autonomous agent started at level: {self._level.value}")
        return True

    def stop(self) -> bool:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None
        logger.info("Autonomous agent stopped")
        return True

    # --- main loop ---

    async def _loop(self) -> None:
        logger.info(f"Autonomous loop entering: level={self._level.value}, interval={self._interval}s")
        while self._running:
            cycle_start = time.monotonic()
            try:
                await self._run_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Autonomous cycle error: {e}\n{traceback.format_exc()}")
                self._stats["errors"] += 1
            elapsed = (time.monotonic() - cycle_start) * 1000
            self._stats["last_cycle_duration_ms"] = round(elapsed, 1)
            self._last_cycle_time = time.time()
            self._cycle_count += 1
            self._stats["total_cycles"] = self._cycle_count

            if self._interval > 0:
                try:
                    await asyncio.wait_for(
                        asyncio.get_event_loop().create_future(),
                        timeout=self._interval,
                    )
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass

    async def _run_cycle(self) -> None:
        """Execute one autonomous cycle. Actions depend on level."""
        level = self._level

        # PASSIVE: observe only
        await self._observe_health()
        await self._observe_patterns()

        if level.value in (AutonomyLevel.ACTIVE.value, AutonomyLevel.AUTONOMOUS.value):
            # ACTIVE+: consolidate, extract KG, warm cache
            await self._auto_consolidate()
            await self._auto_kg_extract()
            await self._auto_cache_warm()
            await self._detect_anomalies()

        if level.value == AutonomyLevel.AUTONOMOUS.value:
            # AUTONOMOUS: dream, goals, tasks, reports
            await self._auto_dream()
            await self._auto_goal_drift_check()
            await self._auto_generate_tasks()
            await self._auto_health_report()
            await self._auto_proactive_notifications()

    # --- PASSIVE actions ---

    async def _observe_health(self) -> None:
        """Observe system health without modifying anything."""
        try:
            all_memories = await self.provider.get_all(user_id="default", limit=5, offset=0)
            if isinstance(all_memories, list):
                self._log_decision(
                    action="observe_health",
                    reason=f"Checked system: {len(all_memories)} recent memories",
                    outcome="observed",
                    confidence=0.9,
                )
        except Exception as e:
            logger.debug(f"Health observation failed: {e}")

    async def _observe_patterns(self) -> None:
        """Detect emerging patterns across recent memories."""
        try:
            recent = await self.provider.search("recent", user_id="default", limit=10)
            results = recent.get("results", []) if isinstance(recent, dict) else recent
            if isinstance(results, list) and len(results) >= 3:
                self._log_decision(
                    action="observe_patterns",
                    reason=f"Analyzed {len(results)} recent memories for patterns",
                    outcome="observed",
                    confidence=0.7,
                )
        except Exception as e:
            logger.debug(f"Pattern observation failed: {e}")

    # --- ACTIVE actions ---

    async def _auto_consolidate(self) -> None:
        """Automatically consolidate similar memories."""
        try:
            if hasattr(self.provider, 'consolidate'):
                result = await self.provider.consolidate(
                    threshold=0.92, min_age_hours=1, batch_size=50
                )
                if result and isinstance(result, dict):
                    merged = result.get("merged", 0)
                    if merged > 0:
                        self._log_decision(
                            action="consolidate",
                            reason=f"Detected {merged} similar memory pairs",
                            outcome=f"Merged {merged} memories",
                            confidence=0.85,
                        )
                        self._stats["actions_taken"] += merged
        except Exception as e:
            logger.debug(f"Auto-consolidate failed: {e}")

    async def _auto_kg_extract(self) -> None:
        """Extract knowledge graph entities from unprocessed memories."""
        try:
            if hasattr(self.provider, 'extract_kg'):
                result = await self.provider.extract_kg()
                if result and isinstance(result, dict):
                    extracted = result.get("triples_extracted", 0)
                    if extracted > 0:
                        self._log_decision(
                            action="kg_extract",
                            reason=f"Found unprocessed memories",
                            outcome=f"Extracted {extracted} triples",
                            confidence=0.8,
                        )
                        self._stats["actions_taken"] += extracted
        except Exception as e:
            logger.debug(f"Auto KG extract failed: {e}")

    async def _auto_cache_warm(self) -> None:
        """Pre-warm predictive cache based on recent workspace context."""
        try:
            if hasattr(self.provider, 'warm_predictive_cache'):
                context = f"workspace:{self.workspace_root}"
                await self.provider.warm_predictive_cache(context)
                self._log_decision(
                    action="cache_warm",
                    reason="Periodic cache warming",
                    outcome="cache_warmed",
                    confidence=0.7,
                )
        except Exception as e:
            logger.debug(f"Auto cache warm failed: {e}")

    async def _detect_anomalies(self) -> None:
        """Detect anomalous patterns using the Governor scoring."""
        try:
            recent = await self.provider.search("*", user_id="default", limit=20)
            results = recent.get("results", []) if isinstance(recent, dict) else recent
            anomalies = []
            if isinstance(results, list) and self.governor:
                for r in results:
                    if not isinstance(r, dict):
                        continue
                    score = float(r.get("score", 0.0) or 0.0)
                    if score < 0.15 and r.get("memory", ""):
                        anomalies.append(r.get("memory", "")[:100])

            if anomalies:
                self._log_decision(
                    action="anomaly_detect",
                    reason=f"Found {len(anomalies)} low-signal memories",
                    outcome=f"Flagged {len(anomalies)} anomalies",
                    confidence=0.6,
                )
                if self.notification_manager:
                    await self.notification_manager.notify(
                        topic="relevance_alert",
                        title=f"{len(anomalies)} anomalous memories detected",
                        body="These memories have very low relevance scores and may need consolidation or pruning.",
                        confidence=0.6,
                    )
        except Exception as e:
            logger.debug(f"Anomaly detection failed: {e}")

    # --- AUTONOMOUS actions ---

    async def _auto_dream(self) -> None:
        """Periodically enter dream state to find hidden patterns."""
        if self._cycle_count % 5 != 0:
            return
        try:
            insight = await self.cognitive_engine.synthesize_dreams(
                context=f"workspace patterns and architecture"
            )
            if insight and "DRAFT_INSIGHT" in insight and "Not enough memories" not in insight:
                self._log_decision(
                    action="dream_synthesis",
                    reason="Periodic dream cycle for hidden pattern discovery",
                    outcome="insight_generated",
                    confidence=0.7,
                )
                self._stats["actions_taken"] += 1
                if self.notification_manager:
                    await self.notification_manager.notify(
                        topic="memory_added",
                        title="Autonomous Dream Insight",
                        body=insight[:500],
                        confidence=0.7,
                    )
        except Exception as e:
            logger.debug(f"Auto dream failed: {e}")

    async def _auto_goal_drift_check(self) -> None:
        """Check if recent work is drifting from active goals."""
        if self._cycle_count % 3 != 0:
            return
        try:
            goals = await self.provider.list_goals(active_only=True, limit=10)
            if not goals or not isinstance(goals, list) or len(goals) == 0:
                return

            recent = await self.provider.search("recent work", user_id="default", limit=5)
            results = recent.get("results", []) if isinstance(recent, dict) else recent
            if not results or not isinstance(results, list):
                return

            goal_texts = [g.get("goal", "") for g in goals if isinstance(g, dict) and g.get("goal")]
            memory_texts = " ".join(
                r.get("memory", "") for r in results[:3] if isinstance(r, dict)
            )

            if goal_texts and memory_texts:
                alignment = await self.cognitive_engine.check_goal_alignment(
                    code_or_plan=memory_texts[:500],
                    context="autonomous drift check",
                )
                if alignment and ("MISALIGNED" in alignment.upper() or "DRIFT" in alignment.upper()):
                    self._log_decision(
                        action="goal_drift",
                        reason="Potential goal drift detected",
                        outcome=alignment[:200],
                        confidence=0.75,
                    )
                    self._stats["actions_taken"] += 1
                    if self.notification_manager:
                        await self.notification_manager.notify(
                            topic="relevance_alert",
                            title="Goal Drift Warning",
                            body=alignment[:300],
                            confidence=0.75,
                        )
        except Exception as e:
            logger.debug(f"Goal drift check failed: {e}")

    async def _auto_generate_tasks(self) -> None:
        """Generate todo file from latent intentions."""
        if self._cycle_count % 10 != 0:
            return
        try:
            result = await self.cognitive_engine.generate_tasks()
            if result and "No latent tasks" not in result:
                self._log_decision(
                    action="generate_tasks",
                    reason="Periodic scan for latent intentions",
                    outcome="todo_file_generated",
                    confidence=0.65,
                )
                self._stats["actions_taken"] += 1
        except Exception as e:
            logger.debug(f"Auto task generation failed: {e}")

    async def _auto_health_report(self) -> None:
        """Generate and store a periodic health report."""
        if self._cycle_count % 7 != 0:
            return
        try:
            report_lines = [
                f"Memento Autonomous Health Report — {datetime.now().isoformat()}",
                f"Level: {self._level.value}",
                f"Cycles: {self._cycle_count}",
                f"Actions taken: {self._stats['actions_taken']}",
                f"Errors: {self._stats['errors']}",
            ]

            if hasattr(self.provider, 'get_memory_stats'):
                stats = await self.provider.get_memory_stats(user_id="default")
                if isinstance(stats, dict):
                    report_lines.append(f"Total memories: {stats.get('total_count', 'N/A')}")

            report_text = "\n".join(report_lines)

            await self.provider.add(
                text=f"[AUTO-REPORT] {report_text}",
                user_id="system",
                metadata={"type": "autonomous_health_report", "level": self._level.value},
            )
            self._log_decision(
                action="health_report",
                reason="Periodic health report",
                outcome="report_stored",
                confidence=0.9,
            )
        except Exception as e:
            logger.debug(f"Auto health report failed: {e}")

    async def _auto_proactive_notifications(self) -> None:
        """Generate proactive notifications based on workspace state."""
        if not self.notification_manager:
            return
        try:
            pending = self.notification_manager.get_pending_notifications()
            if len(pending) > 10:
                await self.notification_manager.notify(
                    topic="relevance_alert",
                    title="High notification backlog",
                    body=f"There are {len(pending)} pending notifications. Consider reviewing them.",
                    confidence=0.5,
                )
        except Exception as e:
            logger.debug(f"Proactive notification check failed: {e}")

    # --- decision logging ---

    def _log_decision(self, action: str, reason: str, outcome: str,
                      confidence: float = 0.0) -> None:
        elapsed = 0.0
        if self._last_cycle_time:
            elapsed = (time.time() - self._last_cycle_time) * 1000

        decision = AutonomousDecision(
            timestamp=datetime.now().isoformat(),
            level=self._level.value,
            action=action,
            reason=reason,
            outcome=outcome,
            confidence=confidence,
            duration_ms=round(elapsed, 1),
        )
        self._decision_log.append(decision)
        while len(self._decision_log) > self.MAX_DECISION_LOG:
            self._decision_log.pop(0)

    # --- public API ---

    def get_status(self) -> Dict[str, Any]:
        return {
            "level": self._level.value,
            "level_description": LEVEL_DESCRIPTIONS.get(self._level, ""),
            "running": self.is_running,
            "interval_seconds": self._interval,
            "cycle_count": self._cycle_count,
            "last_cycle_time": self._last_cycle_time,
            "stats": dict(self._stats),
            "recent_decisions": [
                {
                    "timestamp": d.timestamp,
                    "action": d.action,
                    "reason": d.reason,
                    "outcome": d.outcome,
                    "confidence": d.confidence,
                }
                for d in self._decision_log[-10:]
            ],
        }

    def get_decision_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [
            {
                "timestamp": d.timestamp,
                "level": d.level,
                "action": d.action,
                "reason": d.reason,
                "outcome": d.outcome,
                "confidence": d.confidence,
                "duration_ms": d.duration_ms,
            }
            for d in self._decision_log[-limit:]
        ]
