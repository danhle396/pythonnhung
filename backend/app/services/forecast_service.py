from __future__ import annotations

import datetime as dt
import logging
import threading
import time

import pandas as pd

from app.core.config import Settings
from sqlalchemy import select

from app.db.models import Forecast, GoogleRainObs, Telemetry
from app.db.session import session_scope

log = logging.getLogger(__name__)


class ForecastService:
    def __init__(self, settings: Settings, publisher, hub, notifier=None):
        self.s = settings
        self.publisher = publisher
        self.hub = hub
        self.notifier = notifier
        self._fc = None
        self._calib = None
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
        """Đầu vào mô hình nhiệt/ẩm (và mưa dự phòng) là quan trắc Open-Meteo (các giờ đã qua) tại toạ độ trạm.

        Nhiệt độ/độ ẩm của trạm KHÔNG dùng làm đầu vào: trạm đặt trong nhà / sát mặt đất và chỉ ra ngoài trời từng đợt
        ngắn. Riêng mức mưa YL-83 mới nhất được dùng để hiệu chỉnh xác suất mưa (ensemble_rain).
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

    # ------------------------------------------------------------------ xác suất mưa (miễn phí)
    def _ensemble_members(self):
        from aiot_ml import rain_ensemble as re_
        return re_.fetch_members(self.s.station_lat, self.s.station_lon, self.s.station_tz, forecast_days=3)

    def calibration(self) -> dict:
        if self._calib is None:
            from aiot_ml import rain_ensemble as re_
            self._calib = re_.load_calibration(self.s.rain_calib_path)
        return self._calib

    def station_rain_level(self, device_id: str) -> int | None:
        """Mức mưa YL-83 mới nhất của trạm nếu số đo còn mới (≤ station_fresh_min phút), ngược lại None."""
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=self.s.station_fresh_min)
        with session_scope() as s:
            return s.scalars(select(Telemetry.rain_level).where(Telemetry.device_id == device_id, Telemetry.ts >= since)
                             .order_by(Telemetry.ts.desc()).limit(1)).first()

    def ensemble_rain(self, device_id: str, t_local: pd.Timestamp):
        """Mưa từng giờ +1/+3/+6 h = ensemble đã hiệu chỉnh theo Google + điều chỉnh trạm (≤ rain_max_dev_pct)."""
        if not self.s.use_rain_ensemble:
            return None
        from aiot_ml import rain_ensemble as re_
        from aiot_ml.forecast_infer import ForecastItem
        try:
            members = self._ensemble_members()
        except Exception as e:
            log.warning("Không lấy được Open-Meteo Ensemble: %s", e)
            return None
        calib = self.calibration()
        level = self.station_rain_level(device_id)
        out = []
        for h in (1, 3, 6):
            f = re_.features_at(members, t_local + pd.Timedelta(hours=h))
            base = re_.predict_pct(f, calib) if f else None
            if base is None:
                continue
            adj, why = re_.station_adjustment(h, level)
            v = re_.blend(base, adj, self.s.rain_max_dev_pct)
            out.append(ForecastItem("rain_prob", h, v / 100, None, None, f"{calib['version']}+station",
                                    "Ensemble + trạm", {"source": "ensemble", "base": base / 100, "adj": adj,
                                                        "reason": why, "station_rain_level": level}))
            out.append(ForecastItem("rain_ens", h, base / 100, None, None, calib["version"], "Ensemble",
                                    {"source": "ensemble"}))
        return out or None

    def record_google(self, entries, user: str | None = None) -> dict:
        """Lưu số Google nhập tay [(giờ địa phương, %)] kèm đặc trưng ensemble của đúng giờ đó, chụp ngay lúc nhập."""
        from aiot_ml import rain_ensemble as re_
        members = self._ensemble_members()
        saved, skipped = [], []
        now = dt.datetime.now(dt.timezone.utc)
        with session_scope() as s:
            for t, pct in entries:
                t = pd.Timestamp(t)
                f = re_.features_at(members, t)
                if not f:
                    skipped.append(t.isoformat())
                    continue
                valid = t.tz_localize(self.s.station_tz).tz_convert("UTC").to_pydatetime()
                s.add(GoogleRainObs(entered_at=now, valid_at=valid, google_pct=float(pct), features=f, entered_by=user))
                saved.append(t.isoformat())
        return {"saved": saved, "skipped": skipped}

    def google_comparison(self, limit: int = 200) -> dict:
        """Số Google đã nhập so với dự báo ensemble (hiệu chỉnh hiện tại) và cấu hình mặc định."""
        from aiot_ml import rain_ensemble as re_
        calib = self.calibration()
        with session_scope() as s:
            obs = s.scalars(select(GoogleRainObs).order_by(GoogleRainObs.valid_at.desc(), GoogleRainObs.id.desc())).all()
            rows = [{"id": o.id, "entered_at": o.entered_at, "valid_at": o.valid_at, "google_pct": o.google_pct,
                     "pred_pct": re_.predict_pct(o.features or {}, calib),
                     "default_pct": re_.predict_pct(o.features or {}, re_.DEFAULT_CALIB)} for o in obs]
        err = [abs(r["pred_pct"] - r["google_pct"]) for r in rows if r["pred_pct"] is not None]
        metrics = {"n": len(err), "MAE": round(sum(err) / len(err), 2) if err else None,
                   "within10": round(sum(e <= 10 for e in err) / len(err), 3) if err else None}
        cal = {k: calib.get(k) for k in ("version", "threshold", "weights", "n", "metrics")}
        cal["isotonic"] = bool(calib.get("isotonic"))
        return {"rows": rows[:limit], "metrics": metrics, "min_fit_rows": re_.MIN_FIT_ROWS, "calibration": cal}

    def calibrate(self) -> dict:
        """Học lại hiệu chỉnh từ toàn bộ số Google đã nhập, lưu JSON và dùng ngay cho lượt dự báo sau."""
        from aiot_ml import rain_ensemble as re_
        with session_scope() as s:
            rows = [{"features": o.features, "google_pct": o.google_pct, "issued_at": o.entered_at.isoformat()}
                    for o in s.scalars(select(GoogleRainObs).order_by(GoogleRainObs.entered_at, GoogleRainObs.id))]
        calib = re_.fit_calibration(rows)
        re_.save_calibration(calib, self.s.rain_calib_path)
        self._calib = calib
        log.info("Hiệu chỉnh mưa mới %s: %s", calib["version"], calib["metrics"])
        return calib

    def run_once(self, device_id: str | None = None) -> dict:
        device_id = device_id or self.s.default_device_id
        with self.lock:
            t0 = time.perf_counter()
            om = self.build_input()
            items, t_local = [], None
            if om is not None:
                t_local, items = self.forecaster().predict(om, source="open-meteo")
            if t_local is None:
                t_local = pd.Timestamp.now(tz=self.s.station_tz).tz_localize(None).floor("h")
            rain = self.ensemble_rain(device_id, pd.Timestamp(t_local))
            if rain:
                # LightGBM mưa vẫn chạy nhưng chỉ lưu để so sánh (rain_ml); số hiển thị là ensemble + trạm
                ml = [type(i)("rain_ml", i.horizon, i.value, None, None, i.model_ver, i.model_name, i.extra)
                      for i in items if i.target == "rain_prob"]
                items = [i for i in items if i.target != "rain_prob"] + rain + ml
            if not items:
                log.warning("Bỏ qua lượt dự báo %s: không có dữ liệu Open-Meteo lẫn ensemble", device_id)
                self.last_run = {"device_id": device_id, "source": "unavailable", "items": [],
                                 "elapsed_ms": (time.perf_counter() - t0) * 1000}
                return self.last_run
            source = "+".join(x for x, ok in (("open-meteo", om is not None), ("ensemble", bool(rain))) if ok)
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
                "rain_source": "ensemble" if any(i.target == "rain_ens" for i in items) else "lightgbm",
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
            lines.append("Chưa có dự báo: không lấy được dữ liệu Open-Meteo lẫn ensemble.")
        lines.append(f"Nguồn dữ liệu: {p['source']}" + (" (xác suất mưa: ensemble hiệu chỉnh theo Google + trạm)"
                                                         if p.get("rain_source") == "ensemble" else ""))
        if self.notifier:
            self.notifier.telegram("\n".join(lines))
        return "\n".join(lines)
