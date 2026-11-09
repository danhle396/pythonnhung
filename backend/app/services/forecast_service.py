"""Forecast service (task.md 7.4): chạy mỗi 10–15 phút, lấy dữ liệu gần nhất, tạo feature, gọi model
(mlcore, nạp từ model registry), lưu bảng forecasts, publish `.../forecast` (retain) cho OLED.

Nguồn đầu vào theo thứ tự ưu tiên:
  1. dữ liệu trạm (≥ 30 giờ hợp lệ) + bias correction trạm → Open-Meteo;
  2. Open-Meteo vài ngày gần nhất (khi trạm mới chạy / mất dữ liệu);
  3. persistence (giá trị hiện tại) hoặc nowcast tại edge.
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
import time

import pandas as pd
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import Forecast, Nowcast, Telemetry
from app.db.session import session_scope

log = logging.getLogger(__name__)


class ForecastService:
    def __init__(self, settings: Settings, publisher, hub, notifier=None):
        self.s = settings
        self.publisher = publisher
        self.hub = hub
        self.notifier = notifier
        self._fc = None
        self._bias = None
        self._bias_at = 0.0
        self.lock = threading.Lock()
        self.last_run: dict | None = None

    def forecaster(self):
        if self._fc is None:
            from aiot_ml.forecast_infer import Forecaster
            self._fc = Forecaster(self.s.ml_registry)
        return self._fc

    def reload(self):
        self._fc = None

    def _station_frame(self, device_id, hours=60) -> pd.DataFrame:
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
        cols = [Telemetry.ts, Telemetry.temp_dht, Telemetry.temp_bmp, Telemetry.hum, Telemetry.pressure,
                Telemetry.pressure_msl, Telemetry.lux, Telemetry.rain_level]
        with session_scope() as s:
            rows = s.execute(select(*cols).where(Telemetry.device_id == device_id, Telemetry.ts >= since)
                             .order_by(Telemetry.ts)).all()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=[c.key for c in cols])
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(self.s.station_tz).dt.tz_localize(None)
        return df.set_index("ts").astype(float)

    def _open_meteo_recent(self):
        from aiot_ml import features as fe
        from aiot_ml.fetch_open_meteo import fetch_recent
        om = fetch_recent(past_days=4, lat=self.s.station_lat, lon=self.s.station_lon)
        now_local = pd.Timestamp.now(tz=self.s.station_tz).tz_localize(None).floor("h")
        return fe.open_meteo_to_canonical(om.loc[:now_local])

    def build_input(self, device_id):
        from aiot_ml import features as fe
        fc = self.forecaster()
        tel = self._station_frame(device_id)
        if len(tel):
            can = fe.station_to_canonical(tel, alt_m=self.s.station_alt_m)
            valid = can[["temp", "hum", "pres"]].dropna()
            if len(valid) >= fc.min_hours():
                bias = self._get_bias(can)
                return can, bias, "station"
        if self.s.use_open_meteo_fallback:
            try:
                return self._open_meteo_recent(), None, "open-meteo"
            except Exception as e:
                log.warning("Không lấy được Open-Meteo: %s", e)
        return (tel if len(tel) else None), None, "fallback"

    def _get_bias(self, station_can):
        if self._bias is not None and time.time() - self._bias_at < 6 * 3600:
            return self._bias
        try:
            from aiot_ml.forecast_infer import BiasCorrector
            self._bias = BiasCorrector().fit(station_can, self._open_meteo_recent())
            self._bias_at = time.time()
            log.info("Bias correction trạm→Open-Meteo: %s", self._bias.coef)
        except Exception as e:
            log.warning("Không fit được bias correction: %s", e)
        return self._bias

    def run_once(self, device_id: str | None = None) -> dict:
        device_id = device_id or self.s.default_device_id
        with self.lock:
            t0 = time.perf_counter()
            from aiot_ml.forecast_infer import persistence_fallback
            can, bias, source = self.build_input(device_id)
            items, issued = [], dt.datetime.now(dt.timezone.utc)
            try:
                if source in ("station", "open-meteo"):
                    t_local, items = self.forecaster().predict(can, bias=bias, source=source)
                    issued = pd.Timestamp(t_local).tz_localize(self.s.station_tz).tz_convert("UTC").to_pydatetime()
                else:
                    raise RuntimeError("không đủ dữ liệu")
            except Exception as e:
                log.warning("Forecast dùng persistence (%s)", e)
                def lastv(*cols):
                    for c in cols:
                        if can is not None and c in can and can[c].notna().any():
                            return float(can[c].dropna().iloc[-1])
                    return None
                items = persistence_fallback({"temp": lastv("temp", "temp_dht", "temp_bmp"), "hum": lastv("hum"),
                                              "pres": lastv("pres", "pressure_msl")})
                source = "fallback"
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
        """Tin tóm tắt thời tiết 6h sáng (task.md 10)."""
        device_id = device_id or self.s.default_device_id
        p = self.run_once(device_id)
        it = {(i["target"], i["h"]): i for i in p["items"]}
        with session_scope() as s:
            nc = s.scalars(select(Nowcast).where(Nowcast.device_id == device_id).order_by(Nowcast.ts.desc())).first()
        lines = ["☀️ <b>Dự báo thời tiết sáng nay — VKU, Đà Nẵng</b>"]
        for h in (1, 3, 6):
            t, hu, r = it.get(("temp", h)), it.get(("hum", h)), it.get(("rain_prob", h))
            if t:
                lines.append(f"+{h}h: {t['value']:.1f}°C, ẩm {hu['value']:.0f}%" if hu else f"+{h}h: {t['value']:.1f}°C")
                if r:
                    lines[-1] += f", mưa {r['value'] * 100:.0f}%"
        if nc:
            lines.append(f"Nowcast tại trạm: {nc.text}")
        lines.append(f"Nguồn dữ liệu: {p['source']}")
        if self.notifier:
            self.notifier.telegram("\n".join(lines))
        return "\n".join(lines)
