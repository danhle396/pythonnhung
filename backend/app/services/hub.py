from __future__ import annotations

import asyncio
import json
import logging

log = logging.getLogger(__name__)


class Hub:
    def __init__(self):
        self.loop: asyncio.AbstractEventLoop | None = None
        self.clients: set[asyncio.Queue] = set()

    def attach_loop(self, loop):
        self.loop = loop

    def register(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self.clients.add(q)
        return q

    def unregister(self, q):
        self.clients.discard(q)

    def _fanout(self, text: str):
        for q in list(self.clients):
            try:
                q.put_nowait(text)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(text)
                except Exception:
                    pass

    def publish_threadsafe(self, kind: str, data: dict):
        if self.loop is None or not self.clients:
            return
        text = json.dumps({"type": kind, "data": data}, default=str, ensure_ascii=False)
        try:
            self.loop.call_soon_threadsafe(self._fanout, text)
        except RuntimeError:
            pass
