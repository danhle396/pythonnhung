from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .serialize import load_model

from . import features as fe
from .config import ML_DIR, MODELS_DIR


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

    def __init__(self, registry_path: Path = MODELS_DIR / "registry.json"):
        reg = json.loads(Path(registry_path).read_text(encoding="utf-8"))
        self.bundles = {}
        for name, slot in reg.items():
            if not name.startswith("forecast_") or not slot.get("active"):
                continue
            entry = slot["active"]
            obj, head = load_model(ML_DIR / entry["path"].replace("\\", "/"))
            obj["_ver"] = head["model_ver"]
            obj["_rmse"] = head.get("meta", {}).get("test", {}).get("RMSE")
            self.bundles[name.removeprefix("forecast_")] = obj
        if not self.bundles:
            raise RuntimeError("Registry không có model forecast active — chạy train_forecast trước")
        self.features = next(iter(self.bundles.values()))["features"]

    @staticmethod
    def min_hours():
        return 30

    def predict(self, can: pd.DataFrame, source="open-meteo"):
        x_in = fe.clean(can.copy())
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
                if b["target"] == "hum":
                    v, lo, hi = (min(100.0, max(0.0, z)) if z is not None else None for z in (v, lo, hi))
                out.append(ForecastItem(b["target"], b["horizon"], v, lo, hi, b["_ver"], b["model_name"],
                                        {"source": source}))
            else:
                p = float(model.predict_proba(Xs)[0, 1])
                out.append(ForecastItem("rain_prob", b["horizon"], p, None, None, b["_ver"], b["model_name"],
                                        {"threshold": b.get("threshold", 0.5), "will_rain": p >= b.get("threshold", 0.5),
                                         "source": source}))
        return t0, sorted(out, key=lambda i: (i.target, i.horizon))
