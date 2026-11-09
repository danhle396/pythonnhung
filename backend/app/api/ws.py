"""WS /ws/live — đẩy telemetry, alert, status, forecast realtime cho dashboard."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.runtime import rt

router = APIRouter()


@router.websocket("/ws/live")
async def live(ws: WebSocket):
    await ws.accept()
    hub = rt().hub
    q = hub.register()
    try:
        await ws.send_json({"type": "hello", "data": {"msg": "connected"}})
        while True:
            try:
                text = await asyncio.wait_for(q.get(), timeout=20)
                await ws.send_text(text)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.unregister(q)
