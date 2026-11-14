from __future__ import annotations

import datetime as dt
import logging
import threading
import time

import pandas as pd

from app.core.config import Settings
from app.db.models import Forecast
from app.db.session import session_scope

log = logging.getLogger(__name__)


class ForecastService:
    def __init__(self, settings: Settings, publisher, hub, notifier=None):
        self.s = settings
        self.publisher = publisher
        self.hub = hub
        self.notifier = notifier
        self._fc = None
        self.lock = threading.Lock()
        self.last_run: dict | None = None

    def forecaster(self):
        if self._fc is None:
            from aiot_ml.forecast_infer import Forecaster
            self._fc = Forecaster(self.s.ml_registry)
        return self._fc

    def reload(self):
        self._fc = None

    def _open_meteo_recent(self):
        from aiot_ml import features as fe
        from aiot_ml.fetch_open_meteo import fetch_recent
        om = fetch_recent(past_days=4, lat=self.s.station_lat, lon=self.s.station_lon)
        now_local = pd.Timestamp.now(tz=self.s.station_tz).tz_localize(None).floor("h")
        return fe.open_meteo_to_canonical(om.loc[:now_local])

    def build_input(self):
        """Đầu vào dự báo luôn là quan trắc Open-Meteo (các giờ đã qua) tại toạ độ trạm.

        Số đo của trạm KHÔNG dùng làm đầu vào: trạm đặt trong nhà / ở mặt đất và chỉ ra ngoài trời từng đợt ngắn,
        nên chỉ dùng để đối chiếu dự báo với thực tế (dashboard, trang Dự báo).
        """
        if not self.s.use_open_meteo:
            return None
        try:
            om = self._open_meteo_recent()
        except Exception as e:
            log.warning("Không lấy được Open-Meteo: %s", e)
            return None
        if len(om[["temp", "hum", "pres"]].dropna()) < self.forecaster().min_hours():
            log.warning("Open-Meteo trả về quá ít giờ (%d)", len(om))
            return None
        return om

    def run_once(self, device_id: str | None = None) -> dict:
        device_id = device_id or self.s.default_device_id
        with self.lock:
            t0 = time.perf_counter()
            source = "open-meteo"
            om = self.build_input()
            if om is None:
                log.warning("Bỏ qua lượt dự báo %s: không có dữ liệu Open-Meteo", device_id)
                self.last_run = {"device_id": device_id, "source": "unavailable", "items": [],
                                 "elapsed_ms": (time.perf_counter() - t0) * 1000}
                return self.last_run
            t_local, items = self.forecaster().predict(om, source=source)
            issued = pd.Timestamp(t_local).tz_localize(self.s.station_tz).tz_convert("UTC").to_pydatetime()
            now = dt.datetime.now(dt.timezone.utc)
            with session_scope() as s:
                for it in items:
                    s.add(Forecast(device_id=device_id, created_at=now, issued_for=issued, horizon=it.horizon,
                                   target=it.target, value=it.value, lower=it.lower, upper=it.upper,
                                   model_ver=it.model_ver, source=it.extra.get("source", source)))
            payload = self.payload(device_id, issued, items, source)
            self.publisher.forecast(device_id, payload)
            self.hub.publish_threadsafe("forecast", payload)
            payload["elapsed_ms"] = (time.perf_counter() - t0) * 1000
            self.last_run = payload
            log.info("Forecast %s (%s, %d mục, %.0f ms)", device_id, source, len(items), payload["elapsed_ms"])
            return payload

    @staticmethod
    def payload(device_id, issued, items, source):
        get = {(i.target, i.horizon): i for i in items}
        parts = []
        if ("temp", 1) in get:
            parts.append(f"1h {get[('temp', 1)].value:.1f}C")
        if ("temp", 3) in get:
            parts.append(f"3h {get[('temp', 3)].value:.1f}C")
        if ("rain_prob", 3) in get:
            parts.append(f"Mua3h {get[('rain_prob', 3)].value * 100:.0f}%")
        return {"device_id": device_id, "ts": int(issued.timestamp()), "source": source,
                "items": [{"target": i.target, "h": i.horizon, "value": round(i.value, 3),
                           "lower": None if i.lower is None else round(i.lower, 3),
                           "upper": None if i.upper is None else round(i.upper, 3), "model_ver": i.model_ver}
                          for i in items],
                "summary": " ".join(parts)[:60]}

    def daily_summary(self, device_id: str | None = None):
        device_id = device_id or self.s.default_device_id
        p = self.run_once(device_id)
        it = {(i["target"], i["h"]): i for i in p["items"]}
        lines = ["☀️ <b>Dự báo thời tiết sáng nay — VKU, Đà Nẵng</b>"]
        for h in (1, 3, 6):
            t, hu, r = it.get(("temp", h)), it.get(("hum", h)), it.get(("rain_prob", h))
            if t:
                lines.append(f"+{h}h: {t['value']:.1f}°C, ẩm {hu['value']:.0f}%" if hu else f"+{h}h: {t['value']:.1f}°C")
                if r:
                    lines[-1] += f", mưa {r['value'] * 100:.0f}%"
        if not p["items"]:
            lines.append("Chưa có dự báo: không lấy được dữ liệu Open-Meteo.")
        lines.append(f"Nguồn dữ liệu: {p['source']}")
        if self.notifier:
            self.notifier.telegram("\n".join(lines))
        return "\n".join(lines)
