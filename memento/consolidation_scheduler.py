"""
consolidation_scheduler.py — Background scheduler for memory consolidation.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


class ConsolidationScheduler:
    """Background scheduler that periodically runs memory consolidation."""

    def __init__(
        self,
        consolidate_fn,
        interval_minutes: float = 30.0,
        initial_delay_minutes: float = 5.0,
    ):
        self.consolidate_fn = consolidate_fn
        self.interval_minutes = interval_minutes
        self.initial_delay_minutes = initial_delay_minutes
        self._task: asyncio.Task | None = None
        self._running = False

    async def _loop(self):
        """Run consolidation loop with initial delay."""
        try:
            logger.info(
                f"Consolidation scheduler started: initial delay={self.initial_delay_minutes}m, "
                f"interval={self.interval_minutes}m"
            )
            await asyncio.sleep(self.initial_delay_minutes * 60)

            while self._running:
                try:
                    result = await self.consolidate_fn()
                    logger.info(f"Consolidation cycle result: {result}")
                except Exception as e:
                    logger.error(f"Consolidation error: {e}")

                # Wait for next cycle
                try:
                    await asyncio.sleep(self.interval_minutes * 60)
                except asyncio.CancelledError:
                    break
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            logger.info("Consolidation scheduler stopped")

    def start(self, loop: asyncio.AbstractEventLoop | None = None):
        """Start the scheduler in the given event loop."""
        if self._running:
            return
        self._running = True
        target_loop = loop or asyncio.get_event_loop()
        self._task = target_loop.create_task(self._loop())
        logger.info("Consolidation scheduler scheduled")

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    @property
    def is_running(self) -> bool:
        return self._running
