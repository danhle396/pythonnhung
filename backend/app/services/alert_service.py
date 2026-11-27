from __future__ import annotations

import datetime as dt
import logging
import threading
import time

import numpy as np
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import Alert, Device, Notification, Telemetry
from app.db.session import as_utc, session_scope

log = logging.getLogger(__name__)


def _slope_per_min(ts: np.ndarray, y: np.ndarray) -> float:
    if len(y) < 3:
        return 0.0
    t = (ts - ts[0]) / 60.0
    tc = t - t.mean()
    den = float(np.dot(tc, tc))
    return float(np.dot(tc, y - y.mean()) / den) if den > 0 else 0.0


class AlertService:
    def __init__(self, settings: Settings, notifier, publisher, hub):
        self.s = settings
        self.notifier = notifier
        self.publisher = publisher
        self.hub = hub
        self.lock = threading.RLock()
        self.last_notify: dict[tuple, float] = {}
        self.edge_level: dict[str, int] = {}
        self.cloud_level: dict[str, int] = {}

    def on_edge_alert(self, a, recv_t: float | None = None):
        with self.lock, session_scope() as s:
            if a.seq is not None:
                dup = s.scalars(select(Alert).where(Alert.device_id == a.device_id, Alert.seq == a.seq,
                                                    Alert.ts == a.ts)).first()
                if dup:
                    return dup
            row = Alert(device_id=a.device_id, ts=a.ts, seq=a.seq, type=a.type, level=a.level,
                        prev_level=a.prev_level, cause=a.cause, gas_ppm=a.gas_ppm, source="edge",
                        message=", ".join(a.action) if a.action else None)
            s.add(row)
            s.flush()
            if a.type in ("gas", "test"):
                self.edge_level[a.device_id] = a.level
                if a.level == 0:
                    self.cloud_level[a.device_id] = 0
                    for o in s.scalars(select(Alert).where(Alert.device_id == a.device_id,
                                                           Alert.resolved_at.is_(None), Alert.level > 0,
                                                           Alert.type.in_(["gas", "test"]))):
                        o.resolved_at = dt.datetime.now(dt.timezone.utc)
            s.expunge(row)
        self.hub.publish_threadsafe("alert", self.to_dict(row))
        self.dispatch(row, recv_t=recv_t)
        return row

    def dispatch(self, a: Alert, reminder=False, force=False, recv_t: float | None = None):
        channels = []
        if a.type == "test":
            return []
        if a.type in ("device_offline", "sensor_fault"):
            channels = ["telegram"]
        elif a.level >= 3:
            channels = ["telegram", "email"]
        elif a.level == 2:
            channels = ["telegram"]
        elif a.level == 0 and (a.prev_level or 0) >= 2:
            channels = ["telegram"]
        if not channels:
            return []
        key = (a.device_id, a.type, a.level)
        now = time.time()
        if not (reminder or force):
            last = self.last_notify.get(key)
            escalated = (a.prev_level or 0) < a.level
            if last and now - last < self.s.notify_cooldown_s and not escalated:
                return []
        self.last_notify[key] = now
        text = self.notifier.format_alert(a, reminder=reminder)
        sent = []
        for ch in channels:
            t0 = time.time()
            if ch == "telegram":
                ok = self.notifier.telegram(text, alert_id=a.id if a.level >= 2 else None)
            else:
                ok = self.notifier.email(f"[AIoT VKU] Cấp {a.level} — {a.device_id}", text.replace("\n", "<br>"))
            ts = as_utc(a.ts)
            e2e_ms = (time.time() - ts.timestamp()) * 1000 if ts else None
            with session_scope() as s:
                s.add(Notification(alert_id=a.id, channel=ch, ok=ok, latency_ms=e2e_ms, text=text[:2000]))
                al = s.get(Alert, a.id)
                if al:
                    al.notified_at = dt.datetime.now(dt.timezone.utc)
                    al.notify_count = (al.notify_count or 0) + 1
            log.info("Thông báo %s cấp %s qua %s (ok=%s, %.0f ms gửi, e2e %.0f ms)", a.device_id, a.level, ch, ok,
                     (time.time() - t0) * 1000, e2e_ms or -1)
            sent.append(ch)
        return sent

    def ack(self, alert_id: int, by: str) -> bool:
        now = dt.datetime.now(dt.timezone.utc)
        with session_scope() as s:
            a = s.get(Alert, alert_id)
            if a is None:
                return False
            for o in s.scalars(select(Alert).where(Alert.device_id == a.device_id, Alert.ack_ts.is_(None),
                                                   Alert.ts <= a.ts)):
                o.acknowledged_by, o.ack_ts = by, now
            a.acknowledged_by, a.ack_ts = by, now
            dev = a.device_id
        self.hub.publish_threadsafe("ack", {"alert_id": alert_id, "by": by, "device_id": dev})
        return True

    def reminders(self):
        now = dt.datetime.now(dt.timezone.utc)
        with session_scope() as s:
            rows = s.scalars(select(Alert).where(Alert.level >= 3, Alert.ack_ts.is_(None), Alert.type != "test",
                                                 Alert.notify_count < 60)).all()
            due = [r for r in rows if r.notified_at is None
                   or (now - as_utc(r.notified_at)).total_seconds() >= self.s.reminder_every_s]
            for r in due:
                s.expunge(r)
        for r in due:
            self.dispatch(r, reminder=True)
        return len(due)

    def evaluate(self, device_id: str, now: dt.datetime | None = None) -> int:
        now = now or dt.datetime.now(dt.timezone.utc)
        since = now - dt.timedelta(minutes=max(self.s.escalation_window_min, 60))
        with session_scope() as s:
            rows = s.execute(select(Telemetry.ts, Telemetry.gas_ppm, Telemetry.edge_risk, Telemetry.temp_dht,
                                    Telemetry.hum).where(Telemetry.device_id == device_id, Telemetry.ts >= since,
                                                         Telemetry.ts <= now).order_by(Telemetry.ts)).all()
        rows = [r for r in rows if r.gas_ppm is not None]
        if len(rows) < 20:
            return 0
        ts = np.array([as_utc(r.ts).timestamp() for r in rows])
        ppm = np.array([r.gas_ppm for r in rows], dtype=float)
        edge = int(rows[-1].edge_risk or 0)
        win = ts >= (now.timestamp() - self.s.escalation_window_min * 60)
        cause, level = [], 0
        if win.sum() >= 20:
            tw, pw = ts[win], ppm[win]
            half = len(tw) // 2
            s_all = _slope_per_min(tw, pw)
            s1, s2 = _slope_per_min(tw[:half], pw[:half]), _slope_per_min(tw[half:], pw[half:])
            thr = self.s.escalation_slope_ppm_min
            if s_all >= thr and s1 > 0.3 * thr and s2 > 0.3 * thr:
                if edge >= 1:
                    level = min(edge + 1, 3)
                elif pw[-1] >= 150:
                    level = 1
                cause.append(f"ppm_rising_{s_all:.0f}ppm/min_{self.s.escalation_window_min}min")
        prev_cloud = self.cloud_level.get(device_id, 0)
        if level > edge and level > prev_cloud:
            self.cloud_level[device_id] = level
            self._raise_cloud(device_id, level, edge, cause, float(ppm[-1]), now)
            return level
        if edge == 0 and level == 0:
            self.cloud_level[device_id] = 0
        return 0

    def _raise_cloud(self, device_id, level, edge, cause, ppm, now):
        with session_scope() as s:
            row = Alert(device_id=device_id, ts=now, type="gas", level=level, prev_level=edge, cause=cause,
                        gas_ppm=ppm, source="cloud", message="Cloud xác nhận/leo thang theo ngữ cảnh dài hạn")
            s.add(row)
            s.flush()
            s.expunge(row)
        self.publisher.cmd(device_id, "escalate", level=level)
        log.warning("Cloud leo thang %s: cấp %d -> %d (%s)", device_id, edge, level, cause)
        self.hub.publish_threadsafe("alert", self.to_dict(row))
        self.dispatch(row, force=True)

    def mark_seen(self, device_ids):
        pass

    def device_offline(self, device_id, reason=""):
        now = dt.datetime.now(dt.timezone.utc)
        with session_scope() as s:
            row = Alert(device_id=device_id, ts=now, type="device_offline", level=1, prev_level=None,
                        cause=["no_data" if not reason else "lwt"], source="cloud", message=reason or None)
            s.add(row)
            s.flush()
            s.expunge(row)
        self.hub.publish_threadsafe("alert", self.to_dict(row))
        self.dispatch(row)

    def check_offline(self):
        now = dt.datetime.now(dt.timezone.utc)
        lim = now - dt.timedelta(seconds=self.s.offline_after_s)
        newly = []
        with session_scope() as s:
            for d in s.scalars(select(Device).where(Device.status == "online")):
                if d.last_seen is not None and as_utc(d.last_seen) < lim:
                    d.status = "offline"
                    newly.append(d.id)
        for dev in newly:
            self.device_offline(dev, reason=f"Không nhận dữ liệu > {self.s.offline_after_s} s")
        return newly

    @staticmethod
    def to_dict(a: Alert) -> dict:
        return {c.name: getattr(a, c.name) for c in Alert.__table__.columns}
