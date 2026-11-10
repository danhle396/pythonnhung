"""Suy luận dự báo dùng chung cho backend (forecast_service) và CLI.

Chiến lược "pretrain trên Open-Meteo + hiệu chỉnh bias bằng dữ liệu trạm" (task.md 8.3):
  1. Model được huấn luyện trên lược đồ chuẩn của Open-Meteo.
  2. BiasCorrector học ánh xạ tuyến tính trạm → Open-Meteo cho từng biến (x_om ≈ a·x_st + b) trên
     các giờ trùng nhau (Ridge tự viết). Đầu vào trạm được đưa về "thang Open-Meteo" trước khi dự báo,
     kết quả được đổi ngược về thang trạm: x_st = (x_om − b)/a.
  3. Nếu trạm thiếu dữ liệu (< min_hours giờ hợp lệ) ⇒ dùng Open-Meteo vài ngày gần nhất làm đầu vào;
     nếu cả hai đều không có ⇒ fallback persistence.
Khoảng tin cậy 95% xấp xỉ: ŷ ± 1.96·RMSE_test (RMSE lưu trong header của model).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from mlcore.linear import Ridge
from mlcore.serialize import load_model

from . import features as fe
from .config import ML_DIR, MODELS_DIR

BIAS_VARS = ["temp", "hum", "pres", "dew"]


class BiasCorrector:
    def __init__(self, alpha=1.0, min_overlap=24):
        self.alpha, self.min_overlap = alpha, min_overlap
        self.coef = {}  # var -> (a, b)

    def fit(self, station: pd.DataFrame, om: pd.DataFrame):
        j = station[BIAS_VARS].join(om[BIAS_VARS].add_suffix("_om"), how="inner").rename(columns={v: f"{v}_st" for v in BIAS_VARS}).dropna()
        for v in BIAS_VARS:
            if len(j) < self.min_overlap:
                self.coef[v] = (1.0, float((j[f"{v}_om"] - j[f"{v}_st"]).mean()) if len(j) else 0.0)
                continue
            m = Ridge(alpha=self.alpha).fit(j[[f"{v}_st"]].to_numpy(), j[f"{v}_om"].to_numpy())
            a = float(m.coef_[0])
            if 0.5 <= a <= 1.5:
                self.coef[v] = (a, float(m.intercept_))
            else:
                # tương quan trạm–Open-Meteo kém (hệ số góc bất thường): chỉ hiệu chỉnh độ lệch, tránh khuếch đại
                # sai số khi đổi ngược (chia cho a nhỏ sẽ nới rộng khoảng tin cậy)
                self.coef[v] = (1.0, float((j[f"{v}_om"] - j[f"{v}_st"]).mean()))
        return self

    def to_om(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        for v, (a, b) in self.coef.items():
            if v in out:
                out[v] = a * out[v] + b
        return out

    def to_station(self, var, x):
        a, b = self.coef.get(var, (1.0, 0.0))
        return (np.asarray(x) - b) / a

    def to_dict(self):
        return {"coef": self.coef}

    @classmethod
    def from_dict(cls, d):
        m = cls()
        m.coef = {k: tuple(v) for k, v in d["coef"].items()}
        return m


@dataclass
class ForecastItem:
    target: str
    horizon: int
    value: float
    lower: float | None
    upper: float | None
    model_ver: str
    model_name: str
    extra: dict = field(default_factory=dict)


class Forecaster:
    """Nạp mọi model forecast đang active trong registry."""

    def __init__(self, registry_path: Path = MODELS_DIR / "registry.json"):
        reg = json.loads(Path(registry_path).read_text(encoding="utf-8"))
        self.bundles = {}
        for name, slot in reg.items():
            if not name.startswith("forecast_") or not slot.get("active"):
                continue
            entry = slot["active"]
            obj, head = load_model(ML_DIR / entry["path"].replace("\\", "/"))  # registry có thể sinh trên Windows
            obj["_ver"] = head["model_ver"]
            obj["_rmse"] = head.get("meta", {}).get("test", {}).get("RMSE")
            self.bundles[name.removeprefix("forecast_")] = obj
        if not self.bundles:
            raise RuntimeError("Registry không có model forecast active — chạy train_forecast trước")
        self.features = next(iter(self.bundles.values()))["features"]

    @staticmethod
    def min_hours():
        return 30  # 24h lag + rolling 24h + dự phòng

    def predict(self, can: pd.DataFrame, bias: BiasCorrector | None = None, source="station"):
        """can: lược đồ chuẩn theo giờ (đã có ít nhất ~30 giờ). Dự báo tại giờ cuối cùng."""
        can = fe.clean(can.copy())
        x_in = bias.to_om(can) if bias is not None else can
        F = fe.build_features(x_in)
        last = F.iloc[[-1]]
        if last.isna().any(axis=None):
            last = last.fillna(F.ffill().iloc[[-1]]).fillna(0.0)
        X = last[self.features].to_numpy()
        t0 = F.index[-1]
        out = []
        for key, b in self.bundles.items():
            model = b["model"]
            Xs = b["scaler"].transform(X) if b.get("scaler") is not None else X
            if b["kind"] == "delta":
                base = float(x_in[b["target"]].iloc[-1])
                v = base + float(model.predict(Xs)[0])
                r = b.get("_rmse")
                lo, hi = (v - 1.96 * r, v + 1.96 * r) if r else (None, None)
                if bias is not None:
                    v, lo, hi = (float(bias.to_station(b["target"], z)) if z is not None else None for z in (v, lo, hi))
                if b["target"] == "hum":  # độ ẩm tương đối nằm trong [0, 100]
                    v, lo, hi = (min(100.0, max(0.0, z)) if z is not None else None for z in (v, lo, hi))
                out.append(ForecastItem(b["target"], b["horizon"], v, lo, hi, b["_ver"], b["model_name"],
                                        {"source": source}))
            else:
                p = float(model.predict_proba(Xs)[0, 1])
                out.append(ForecastItem("rain_prob", b["horizon"], p, None, None, b["_ver"], b["model_name"],
                                        {"threshold": b.get("threshold", 0.5), "will_rain": p >= b.get("threshold", 0.5),
                                         "source": source}))
        return t0, sorted(out, key=lambda i: (i.target, i.horizon))


def persistence_fallback(last_values: dict, horizons=(1, 3, 6)):
    """Khi không có model/dữ liệu: dự báo = giá trị hiện tại."""
    items = []
    for tgt in ("temp", "hum", "pres"):
        if last_values.get(tgt) is not None:
            for h in horizons:
                items.append(ForecastItem(tgt, h, float(last_values[tgt]), None, None, "persistence", "Persistence",
                                          {"source": "fallback"}))
    return items
