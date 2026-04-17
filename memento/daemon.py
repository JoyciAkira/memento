import asyncio
import logging
from typing import Callable, Awaitable, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)

class PreCognitiveDaemon:
    def __init__(
        self,
        workspace_path: str,
        callback: Callable[[str, str], Awaitable],
        debounce_seconds: float = 5.0,
        retrieval_pipeline: Optional[Callable[[str], Awaitable]] = None,
    ):
        self.workspace_path = workspace_path
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self.retrieval_pipeline = retrieval_pipeline
        self._timers = {}
        self.observer = None
        self.is_running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the event loop to use for scheduling callbacks."""
        self._loop = loop

    async def handle_file_change(self, filepath: str, content: str):
        if filepath in self._timers:
            self._timers[filepath].cancel()

        async def _trigger():
            try:
                if self.retrieval_pipeline:
                    await self.retrieval_pipeline(filepath)
                await self.callback(filepath, content)
            except Exception as e:
                logger.error(f"Daemon callback error: {e}")

        target_loop = self._loop
        if target_loop is None:
            try:
                target_loop = asyncio.get_event_loop()
            except RuntimeError:
                pass

        if target_loop and target_loop.is_running():
            self._timers[filepath] = target_loop.call_later(
                self.debounce_seconds,
                lambda: asyncio.run_coroutine_threadsafe(_trigger(), target_loop),
            )

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.observer = Observer()

        class Handler(FileSystemEventHandler):
            def __init__(self, daemon_instance):
                self.daemon = daemon_instance

            def on_modified(self, event):
                if event.is_directory:
                    return
                try:
                    with open(event.src_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = None

                    if loop and loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self.daemon.handle_file_change(event.src_path, content),
                            loop
                        )
                except Exception as e:
                    logger.error(f"Error reading modified file {event.src_path}: {e}")

        handler = Handler(self)
        self.observer.schedule(handler, self.workspace_path, recursive=True)
        self.observer.start()

    def stop(self):
        self.is_running = False
        for timer in self._timers.values():
            timer.cancel()
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
