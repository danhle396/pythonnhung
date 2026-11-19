"""Xác suất mưa theo giờ từ Open-Meteo Ensemble (miễn phí, không cần key) + hiệu chỉnh học bắt chước Google.

Nguồn: https://ensemble-api.open-meteo.com/v1/ensemble — mỗi mô hình chạy nhiều phương án (thành viên) hơi khác nhau:
ECMWF IFS 0,25° (51), NCEP GEFS 0,25° (31), DWD ICON EPS (40). Xác suất mưa của một mô hình ở ngưỡng θ mm
= tỉ lệ thành viên có lượng mưa giờ đó ≥ θ.

Google không cung cấp dữ liệu miễn phí, nên hệ thống học cách bắt chước số Google mà người dùng tra trên Google Search
và nhập tay ở dashboard. Mỗi lần nhập, backend chụp lại đặc trưng ensemble của đúng các giờ đó (cùng thời điểm phát
hành), rồi `fit_calibration`:
  1. tìm kiếm lưới: ngưỡng θ và trọng số từng mô hình → p = Σ wₘ·frac(m, θ) / Σ wₘ, chọn cấu hình có MAE nhỏ nhất
     so với Google sau khi khớp tuyến tính a·p + b (đo mức "đi cùng" Google);
  2. hồi quy đẳng biến (IsotonicRegression của scikit-learn) ánh xạ p → số Google, chỉ giữ nếu giảm MAE trên phần
     dữ liệu mới nhất (chia theo thời gian).
Chưa đủ dữ liệu → cấu hình mặc định (gộp 3 mô hình, θ = 1 mm), chọn từ lần đo đầu tiên (lệch TB 12 điểm, 5 giờ).
"""
from __future__ import annotations

import datetime as dt
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .config import MODELS_DIR, STATION

URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
API_MODELS = {"ecmwf": "ecmwf_ifs025", "gfs": "gfs025", "icon": "icon_seamless"}
MODELS = tuple(API_MODELS)
THRESHOLDS = (0.1, 0.25, 0.5, 1.0, 2.0, 3.0)
WEIGHT_GRID = (0.0, 0.5, 1.0)
CALIB_PATH = MODELS_DIR / "rain_calib.json"
MIN_FIT_ROWS = 40
MAX_STATION_DEV = 10.0
# YL-83 của trạm đang báo mưa (rain_level ≥ 1): trạm thấy mưa thật tại VKU → cộng điểm, giảm dần theo tầm dự báo
STATION_WET_BOOST = {1: 10.0, 3: 5.0, 6: 0.0}
DEFAULT_CALIB = {"version": "ens-default", "threshold": 1.0, "weights": {"ecmwf": 1.0, "gfs": 1.0, "icon": 1.0},
                 "isotonic": None, "n": 0, "metrics": None}


def feature_name(model: str, thr: float) -> str:
    return f"{model}_ge{thr:g}"


def _model_of(column: str) -> str | None:
    c = column.lower()
    if "ecmwf" in c:
        return "ecmwf"
    if "gfs" in c or "gefs" in c:
        return "gfs"
    if "icon" in c:
        return "icon"
    return None


def parse_members(js: dict) -> dict[str, pd.DataFrame]:
    """JSON ensemble → {mô hình: bảng lượng mưa (giờ địa phương × thành viên)}."""
    h = js.get("hourly") or {}
    idx = pd.to_datetime(pd.Series(h.get("time", [])))
    out = {}
    for m in MODELS:
        cols = [c for c in h if c.startswith("precipitation") and _model_of(c) == m]
        if cols:
            out[m] = pd.DataFrame({c: h[c] for c in cols}, index=pd.DatetimeIndex(idx)).astype(float)
    return out


def fetch_members(lat=STATION["lat"], lon=STATION["lon"], tz=STATION["tz"], forecast_days=2, timeout=60):
    js = requests.get(URL, params={"latitude": lat, "longitude": lon, "hourly": "precipitation",
                                   "models": ",".join(API_MODELS.values()), "forecast_days": forecast_days,
                                   "timezone": tz}, timeout=timeout,
                      headers={"User-Agent": "vku-aiot-station/1.0"}).json()
    if "hourly" not in js:
        raise RuntimeError(f"Open-Meteo Ensemble lỗi: {js.get('reason', js)}")
    return parse_members(js)


def features_at(members: dict[str, pd.DataFrame], t: pd.Timestamp) -> dict | None:
    """Tỉ lệ thành viên có mưa ≥ θ ở giờ t, cho từng mô hình × ngưỡng (None nếu không có giờ đó)."""
    f = {}
    for m, df in members.items():
        if t not in df.index:
            continue
        row = df.loc[t].dropna().to_numpy()
        if not len(row):
            continue
        for thr in THRESHOLDS:
            f[feature_name(m, thr)] = float((row >= thr).mean())
    return f or None


def raw_prob(f: dict, threshold: float, weights: dict) -> float | None:
    """p (0–1) = trung bình có trọng số của tỉ lệ thành viên có mưa ≥ threshold (bỏ mô hình thiếu dữ liệu)."""
    num = den = 0.0
    for m, w in weights.items():
        v = f.get(feature_name(m, threshold))
        if v is None or w <= 0:
            continue
        num += w * v
        den += w
    return num / den if den > 0 else None


def predict_pct(f: dict, calib: dict) -> float | None:
    p = raw_prob(f, calib["threshold"], calib["weights"])
    if p is None:
        return None
    iso = calib.get("isotonic")
    pct = float(np.interp(p, iso["x"], iso["y"])) if iso else p * 100
    return min(100.0, max(0.0, pct))


def station_adjustment(horizon: int, station_rain_level: int | None) -> tuple[float, str]:
    if station_rain_level is not None and station_rain_level >= 1:
        return STATION_WET_BOOST.get(horizon, 0.0), "trạm đang báo mưa"
    return 0.0, ""


def blend(base_pct: float, adj_pct: float, max_dev: float = MAX_STATION_DEV) -> float:
    """Kết quả cuối (0–100): base + hiệu chỉnh trạm, phần hiệu chỉnh không quá max_dev điểm."""
    v = base_pct + max(-max_dev, min(max_dev, adj_pct))
    return min(100.0, max(0.0, v))


def _metrics(pred: np.ndarray, target: np.ndarray) -> dict:
    e = np.abs(pred - target)
    return {"n": int(len(e)), "MAE": round(float(e.mean()), 2), "within10": round(float((e <= 10).mean()), 3),
            "max": round(float(e.max()), 1)}


def fit_calibration(rows: list[dict], valid_frac: float = 0.3) -> dict:
    """rows: [{"features": {...}, "google_pct": 0–100, "issued_at": thời điểm nhập}] → cấu hình hiệu chỉnh mới.

    Chọn cấu hình trên phần cũ (train), báo cáo trên phần mới nhất (valid); cấu hình cuối fit lại trên toàn bộ.
    """
    rows = sorted((r for r in rows if r.get("features")), key=lambda r: str(r.get("issued_at", "")))
    if len(rows) < MIN_FIT_ROWS:
        raise ValueError(f"Cần ít nhất {MIN_FIT_ROWS} giờ có số Google (hiện có {len(rows)})")
    F = [r["features"] for r in rows]
    y = np.array([float(r["google_pct"]) for r in rows])
    n_tr = max(1, int(round(len(rows) * (1 - valid_frac))))

    def search(ix):
        best = None
        for thr in THRESHOLDS:
            for ws in itertools.product(WEIGHT_GRID, repeat=len(MODELS)):
                if sum(ws) == 0:
                    continue
                w = dict(zip(MODELS, ws))
                p = np.array([raw_prob(F[i], thr, w) for i in ix], dtype=float)
                ok = ~np.isnan(p)
                if ok.mean() < 0.9:
                    continue
                # chấm theo sai số sau khi khớp tuyến tính a·p + b: chọn nguồn/ngưỡng "đi cùng" Google nhất,
                # kể cả khi Google nén hay dãn thang xác suất (bước sau mới quyết định có ánh xạ hay không)
                A = np.column_stack([p[ok], np.ones(ok.sum())])
                coef, *_ = np.linalg.lstsq(A, y[ix][ok], rcond=None)
                mae = float(np.abs(A @ coef - y[ix][ok]).mean())
                if best is None or mae < best[0]:
                    best = (mae, thr, w)
        return best

    def with_iso(ix, thr, w):
        from sklearn.isotonic import IsotonicRegression
        p = np.array([raw_prob(F[i], thr, w) for i in ix], dtype=float)
        ok = ~np.isnan(p)
        iso = IsotonicRegression(y_min=0, y_max=100, out_of_bounds="clip").fit(p[ok], y[ix][ok])
        return {"x": [float(v) for v in iso.X_thresholds_], "y": [float(v) for v in iso.y_thresholds_]}

    def evaluate(calib, ix):
        p = np.array([predict_pct(F[i], calib) for i in ix], dtype=float)
        ok = ~np.isnan(p)
        return _metrics(p[ok], y[ix][ok])

    tr, va = list(range(n_tr)), list(range(n_tr, len(rows)))
    _, thr, w = search(tr)
    plain = {"threshold": thr, "weights": w, "isotonic": None}
    iso_cal = {**plain, "isotonic": with_iso(tr, thr, w)}
    use_iso = bool(va) and evaluate(iso_cal, va)["MAE"] < evaluate(plain, va)["MAE"]
    valid = {"plain": evaluate(plain, va) if va else None, "isotonic": evaluate(iso_cal, va) if va else None}
    default_valid = evaluate(DEFAULT_CALIB, va) if va else None

    every = list(range(len(rows)))
    _, thr, w = search(every)
    final = {"threshold": thr, "weights": w, "isotonic": with_iso(every, thr, w) if use_iso else None}
    return {"version": f"ens-{dt.datetime.now():%Y%m%d%H%M}", **final, "n": len(rows),
            "metrics": {"train_all": evaluate(final, every), "valid_recent": valid["isotonic" if use_iso else "plain"],
                        "valid_default": default_valid, "valid_rows": len(va), "use_isotonic": use_iso}}


def load_calibration(path: Path = CALIB_PATH) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULT_CALIB)


def save_calibration(calib: dict, path: Path = CALIB_PATH) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(calib, indent=1, ensure_ascii=False), encoding="utf-8")
