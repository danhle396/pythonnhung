"""Ingestion service: subscribe vku/aiot/+/{telemetry,alert,status,nowcast,ack}, validate (Pydantic),
chống trùng theo (device_id, seq), ghi DB theo lô và đẩy realtime sang WebSocket.

Luồng: thread paho (on_message) -> queue -> worker thread: alert xử lý ngay (độ trễ thấp),
telemetry gom lô (≤ 200 bản ghi hoặc 0.5 s) rồi INSERT ... ON CONFLICT DO NOTHING.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import queue
import threading
import time
from collections import OrderedDict

import paho.mqtt.client as mqtt
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import Command, Device, DeviceConfig, Nowcast, Telemetry
from app.db.session import session_scope
from app.schemas.payloads import AckIn, AlertIn, NowcastIn, StatusIn, TelemetryIn

log = logging.getLogger(__name__)
TELEMETRY_COLS = [c.name for c in Telemetry.__table__.columns if c.name not in ("received_at", "extra")]


def insert_ignore(session, table, rows):
    """INSERT bỏ qua bản ghi trùng khoá — hỗ trợ PostgreSQL và SQLite."""
    if not rows:
        return 0
    dialect = session.bind.dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    res = session.execute(insert(table).values(rows).on_conflict_do_nothing())
    return res.rowcount or 0


class Deduper:
    """LRU các khoá (device_id, seq) đã thấy — chặn trùng nhanh trước khi chạm DB."""

    def __init__(self, maxlen=20000):
        self.seen = OrderedDict()
        self.maxlen = maxlen

    def check_and_add(self, key) -> bool:
        if key in self.seen:
            self.seen.move_to_end(key)
            return False
        self.seen[key] = None
        if len(self.seen) > self.maxlen:
            self.seen.popitem(last=False)
        return True


class MqttService:
    def __init__(self, settings: Settings, publisher, hub, alert_service):
        self.s = settings
        self.publisher = publisher
        self.hub = hub
        self.alerts = alert_service
        self.q: queue.Queue = queue.Queue(maxsize=50000)
        self.dedupe = Deduper()
        self.client: mqtt.Client | None = None
        self.stop_evt = threading.Event()
        self.worker: threading.Thread | None = None
        self.stats = {"received": 0, "telemetry": 0, "duplicates": 0, "invalid": 0, "alerts": 0, "batches": 0,
                      "connected": False, "latency_ms_last": None}

    # ------------------------------------------------------------------ vòng đời
    def start(self):
        self.worker = threading.Thread(target=self._work, name="ingest-worker", daemon=True)
        self.worker.start()
        if not self.s.mqtt_enabled:
            log.info("MQTT bị tắt (MQTT_ENABLED=false)")
            return
        c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                        client_id=f"aiot-backend-{int(time.time())}", clean_session=True)
        if self.s.mqtt_user:
            c.username_pw_set(self.s.mqtt_user, self.s.mqtt_pass)
        c.on_connect = self._on_connect
        c.on_disconnect = self._on_disconnect
        c.on_message = self._on_message
        c.reconnect_delay_set(1, 30)
        c.connect_async(self.s.mqtt_host, self.s.mqtt_port, keepalive=30)
        c.loop_start()
        self.client = c
        self.publisher.client = c

    def stop(self):
        self.stop_evt.set()
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
        if self.worker:
            self.worker.join(timeout=3)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        p = self.s.mqtt_topic_prefix
        for suffix in ("telemetry", "alert", "status", "nowcast", "ack"):
            client.subscribe(f"{p}/+/{suffix}", qos=1)
        self.stats["connected"] = True
        log.info("MQTT đã kết nối %s:%s (rc=%s)", self.s.mqtt_host, self.s.mqtt_port, reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.stats["connected"] = False
        log.warning("MQTT mất kết nối rc=%s", reason_code)

    def _on_message(self, client, userdata, msg):
        try:
            self.q.put_nowait((msg.topic, msg.payload, time.time()))
        except queue.Full:
            log.error("Hàng đợi ingest đầy — bỏ tin")

    # ------------------------------------------------------------------ xử lý
    def handle(self, topic: str, payload: bytes, recv_t: float | None = None):
        """Xử lý đồng bộ 1 tin (dùng trực tiếp trong test). Telemetry trả về dict hàng để gom lô."""
        self.stats["received"] += 1
        parts = topic.split("/")
        if len(parts) < 3:
            return None
        device_id, kind = parts[-2], parts[-1]
        try:
            text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
            data = json.loads(text) if text.strip().startswith("{") else {"state": text.strip()}
        except Exception:
            self.stats["invalid"] += 1
            return None
        data.setdefault("device_id", device_id)
        try:
            if kind == "telemetry":
                t = TelemetryIn.model_validate(data)
                if not self.dedupe.check_and_add((t.device_id, t.seq, int(t.ts.timestamp()))):
                    self.stats["duplicates"] += 1
                    return None
                row = {k: getattr(t, k, None) for k in TELEMETRY_COLS}
                row["extra"] = t.extra_fields() or None
                row["received_at"] = dt.datetime.now(dt.timezone.utc)
                return row
            if kind == "alert":
                a = AlertIn.model_validate(data)
                self.stats["alerts"] += 1
                self.alerts.on_edge_alert(a, recv_t=recv_t)
            elif kind == "status":
                self._on_status(device_id, StatusIn.model_validate(data))
            elif kind == "nowcast":
                n = NowcastIn.model_validate(data)
                with session_scope() as s:
                    s.add(Nowcast(device_id=n.device_id, ts=n.ts, code=n.code, text=n.text, trend=n.trend,
                                  trend_3h=n.trend_3h, zambretti=n.zambretti))
                self.hub.publish_threadsafe("nowcast", n.model_dump(mode="json"))
            elif kind == "ack":
                self._on_ack(device_id, AckIn.model_validate(data))
        except ValidationError as e:
            self.stats["invalid"] += 1
            log.warning("Payload không hợp lệ %s: %s", topic, e.errors()[:2])
        return None

    def flush(self, rows: list[dict]):
        if not rows:
            return 0
        now = dt.datetime.now(dt.timezone.utc)
        with session_scope() as s:
            n = insert_ignore(s, Telemetry.__table__, rows)
            self.stats["duplicates"] += len(rows) - n
            last = {}
            for r in rows:
                last[r["device_id"]] = r
            for dev_id, r in last.items():
                d = s.get(Device, dev_id) or Device(id=dev_id, name=dev_id)
                d.last_seen = now
                if d.status != "online":
                    d.status = "online"
                d.fw = r.get("fw") or d.fw
                d.model_ver = r.get("model_ver") or d.model_ver
                s.merge(d)
        self.stats["telemetry"] += n
        self.stats["batches"] += 1
        for r in rows:
            self.hub.publish_threadsafe("telemetry", r)
        self.alerts.mark_seen(list({r["device_id"] for r in rows}))
        return n

    def _work(self):
        batch, last_flush = [], time.time()
        while not self.stop_evt.is_set():
            try:
                topic, payload, recv_t = self.q.get(timeout=0.2)
                row = self.handle(topic, payload, recv_t)
                if row is not None:
                    batch.append(row)
            except queue.Empty:
                pass
            except Exception:
                log.exception("Lỗi xử lý tin MQTT")
            if batch and (len(batch) >= 200 or time.time() - last_flush > 0.5):
                try:
                    self.flush(batch)
                except Exception:
                    log.exception("Lỗi ghi lô telemetry")
                batch, last_flush = [], time.time()

    def _on_status(self, device_id, st: StatusIn):
        now = dt.datetime.now(dt.timezone.utc)
        with session_scope() as s:
            d = s.get(Device, device_id) or Device(id=device_id, name=device_id)
            prev = d.status
            d.status = "offline" if st.state == "offline" else "online"
            if st.state != "offline":
                d.last_seen = now
            d.rssi = st.rssi if st.rssi is not None else d.rssi
            d.fw = st.fw or d.fw
            d.model_ver = st.model_ver or d.model_ver
            d.last_status = st.model_dump(mode="json")
            s.merge(d)
        if st.state == "offline" and prev != "offline":
            self.alerts.device_offline(device_id, reason="LWT: broker báo mất kết nối")
        elif st.state != "offline":
            self.alerts.mark_seen([device_id])
        self.hub.publish_threadsafe("status", {"device_id": device_id, **st.model_dump(mode="json")})

    def _on_ack(self, device_id, ack: AckIn):
        now = dt.datetime.now(dt.timezone.utc)
        with session_scope() as s:
            if ack.ref == "config":
                cfg = s.scalars(select(DeviceConfig).where(DeviceConfig.device_id == device_id)
                                .order_by(DeviceConfig.version.desc())).first()
                if cfg and ack.ok:
                    cfg.acked, cfg.acked_at = True, now
            elif ack.id:
                c = s.get(Command, ack.id)
                if c:
                    c.acked, c.acked_at, c.ack_msg = ack.ok, now, ack.msg
        self.hub.publish_threadsafe("ack", {"device_id": device_id, **ack.model_dump(mode="json")})
