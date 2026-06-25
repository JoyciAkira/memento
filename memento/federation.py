"""Federation: Unix socket-based push notifications for cross-agent memory events.

When MEMENTO_FEDERATION_SOCKET is set, the server broadcasts write events to all
connected agents via a Unix domain socket instead of the 30s WAL poll.

Architecture:
- FederationServer: runs in the provider process, accepts connections, broadcasts events
- FederationClient: connects to the server socket, receives events, calls callback

Both sides degrade gracefully — if the socket is unavailable, the WAL watcher fallback
in provider.py handles eventual consistency.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

_EVENT_WRITE = "write"
_EVENT_KG_UPDATE = "kg_update"


class FederationServer:
    """Broadcasts memory events to all connected agents via Unix socket."""

    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self._clients: set[asyncio.StreamWriter] = set()
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        if os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except Exception:
                pass
        self._server = await asyncio.start_unix_server(
            self._handle_client, path=self.socket_path
        )
        try:
            os.chmod(self.socket_path, 0o700)
        except Exception:
            pass
        logger.info(f"Federation server listening on {self.socket_path}")

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        for w in list(self._clients):
            try:
                w.close()
            except Exception:
                pass
        self._clients.clear()
        try:
            os.unlink(self.socket_path)
        except Exception:
            pass

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._clients.add(writer)
        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    break
        except Exception:
            pass
        finally:
            self._clients.discard(writer)
            try:
                writer.close()
            except Exception:
                pass

    async def broadcast(self, event_type: str, payload: dict) -> None:
        if not self._clients:
            return
        message = json.dumps({"type": event_type, **payload}) + "\n"
        dead = set()
        for writer in list(self._clients):
            try:
                writer.write(message.encode())
                await writer.drain()
            except Exception:
                dead.add(writer)
        self._clients -= dead


class FederationClient:
    """Connects to a federation server socket and calls callback on events."""

    def __init__(
        self,
        socket_path: str,
        on_write: Callable[[dict], Awaitable[None]],
    ):
        self.socket_path = socket_path
        self._on_write = on_write
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.ensure_future(self._listen())

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _listen(self) -> None:
        while True:
            try:
                reader, _ = await asyncio.open_unix_connection(self.socket_path)
                logger.info(f"Federation client connected to {self.socket_path}")
                async for line in reader:
                    try:
                        event = json.loads(line.decode().strip())
                        if event.get("type") in (_EVENT_WRITE, _EVENT_KG_UPDATE):
                            await self._on_write(event)
                    except Exception:
                        pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Federation client disconnected: {e}")
                await asyncio.sleep(5)
