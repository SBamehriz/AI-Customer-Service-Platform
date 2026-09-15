"""In process publish and subscribe for live updates."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class Hub:
    """Fan out of JSON events to every socket watching a workspace."""

    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def join(self, workspace_id: str, socket: WebSocket) -> None:
        async with self._lock:
            self._rooms[workspace_id].add(socket)

    async def leave(self, workspace_id: str, socket: WebSocket) -> None:
        async with self._lock:
            self._rooms[workspace_id].discard(socket)
            if not self._rooms[workspace_id]:
                self._rooms.pop(workspace_id, None)

    async def publish(self, workspace_id: str, event: str, data: Any = None) -> None:
        """Send an event to a workspace. Dead sockets are dropped, not raised."""
        async with self._lock:
            sockets = list(self._rooms.get(workspace_id, ()))
        if not sockets:
            return
        payload = {"event": event, "data": data}
        stale: list[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_json(payload)
            except Exception:  # noqa: BLE001, a closed peer must not stop the others
                stale.append(socket)
        if stale:
            async with self._lock:
                for socket in stale:
                    self._rooms.get(workspace_id, set()).discard(socket)


hub = Hub()
