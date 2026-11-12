"""Publish xuống thiết bị: cmd / config (retain) / forecast (retain)."""
from __future__ import annotations

import json
import logging
import uuid

log = logging.getLogger(__name__)


class Publisher:
    def __init__(self, prefix: str):
        self.prefix = prefix
        self.client = None  # paho client, gán bởi MqttService khi kết nối
        self.published: list[tuple[str, dict, bool]] = []  # lưu lại (dùng cho test / debug)

    def topic(self, device_id, suffix):
        return f"{self.prefix}/{device_id}/{suffix}"

    def publish(self, device_id: str, suffix: str, payload: dict, retain=False, qos=1) -> bool:
        t = self.topic(device_id, suffix)
        self.published.append((t, payload, retain))
        if len(self.published) > 1000:
            del self.published[:500]
        if self.client is None:
            log.info("[mqtt:dev] %s %s", t, payload)
            return False
        info = self.client.publish(t, json.dumps(payload, ensure_ascii=False), qos=qos, retain=retain)
        return info.rc == 0

    def clear_retained(self, device_id: str, suffixes=("forecast", "config", "status", "nowcast")):
        """Xoá bản tin retained của thiết bị trên broker (gửi payload rỗng có cờ retain)."""
        for s in suffixes:
            t = self.topic(device_id, s)
            self.published.append((t, {}, True))
            if self.client is not None:
                self.client.publish(t, b"", qos=1, retain=True)

    def cmd(self, device_id: str, cmd: str, **kw) -> str:
        cid = str(uuid.uuid4())
        self.publish(device_id, "cmd", {"cmd": cmd, "id": cid, **kw}, retain=False, qos=1)
        return cid

    def config(self, device_id: str, cfg: dict):
        return self.publish(device_id, "config", cfg, retain=True, qos=1)

    def forecast(self, device_id: str, payload: dict):
        return self.publish(device_id, "forecast", payload, retain=True, qos=1)
