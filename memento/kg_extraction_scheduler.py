"""Background scheduler for KG auto-extraction."""

import asyncio
import logging

logger = logging.getLogger(__name__)


class KGExtractionScheduler:
    def __init__(
        self,
        extraction_fn,
        interval_minutes: float = 60.0,
        initial_delay_minutes: float = 10.0,
    ):
        self.extraction_fn = extraction_fn
        self.interval_minutes = interval_minutes
        self.initial_delay_minutes = initial_delay_minutes
        self._task: asyncio.Task | None = None
        self._running = False

    async def _loop(self):
        try:
            await asyncio.sleep(self.initial_delay_minutes * 60)
        except asyncio.CancelledError:
            return

        while self._running:
            try:
                result = await self.extraction_fn()
                logger.info(f"KG extraction cycle: {result}")
            except Exception as e:
                logger.error(f"KG extraction error: {e}")
            try:
                await asyncio.sleep(self.interval_minutes * 60)
            except asyncio.CancelledError:
                break
        self._running = False

    def start(self, loop: asyncio.AbstractEventLoop | None = None):
        if self._running:
            return
        self._running = True
        target_loop = loop or asyncio.get_event_loop()
        self._task = target_loop.create_task(self._loop())

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    @property
    def is_running(self) -> bool:
        return self._running
