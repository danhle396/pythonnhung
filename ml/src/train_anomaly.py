"""Phát hiện bất thường ở cloud (task.md 8.7):
  1. Isolation Forest trên đặc trưng cửa sổ 10 phút của gas ppm (+ T/H, giờ) để bắt rò rỉ chậm.
  2. So sánh với z-score theo giờ trong ngày.
  3. CUSUM trên baseline R0 hằng ngày để phát hiện trôi (lão hoá) MQ-2 -> đề xuất hiệu chuẩn lại.

    python -m aiot_ml.train_anomaly [--data telemetry.csv]
Không có --data: dùng chuỗi dài hạn mô phỏng (gas_sim.generate_long_term) — cần thay bằng dữ liệu trạm thật.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from mlcore import anomaly, metrics, preprocessing as pp
from mlcore.serialize import save_model

from .config import EXPERIMENTS_DIR, MODELS_DIR, REPO_DIR, SEED
from .gas_sim import generate_long_term

WINDOW_FEATURES = ["ppm_mean", "ppm_std", "ppm_slope", "ppm_d60", "temp", "hum", "hour_sin", "hour_cos"]


def window_features(df: pd.DataFrame, freq="10min") -> pd.DataFrame:
    """df: index thời gian, cột gas_ppm, temp, hum. Trả về feature theo cửa sổ 10 phút."""
    g = df["gas_ppm"].resample(freq)
    out = pd.DataFrame({"ppm_mean": g.mean(), "ppm_std": g.std(),
                        "ppm_slope": g.apply(lambda s: pp.linear_slope(s.to_numpy()) * len(s) if len(s) > 1 else 0.0),
                        "temp": df["temp"].resample(freq).mean(), "hum": df["hum"].resample(freq).mean()})
    out["ppm_d60"] = out["ppm_mean"] - out["ppm_mean"].shift(6)
    out["hour_sin"], out["hour_cos"] = pp.cyclic_encode(out.index.hour + out.index.minute / 60.0, 24)
    if "leak" in df:
        out["leak"] = df["leak"].resample(freq).max()
    return out.dropna()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=None)
    a = ap.parse_args(argv)
    leak_days = [22, 24, 26, 28]
    if a.data:
        raw = pd.read_csv(a.data, parse_dates=["ts"]).set_index("ts")
    else:
        raw = generate_long_term(days=30, seed=SEED, leak_days=leak_days, drift_start_day=18).set_index("ts")
    W = window_features(raw)
    split = W.index[0] + pd.Timedelta(days=20)
    tr, te = W[W.index < split], W[W.index >= split]
    Xtr, Xte = tr[WINDOW_FEATURES].to_numpy(), te[WINDOW_FEATURES].to_numpy()
    scaler = pp.StandardScaler().fit(Xtr)
    iso = anomaly.IsolationForest(n_estimators=200, max_samples=256, contamination=0.01, seed=SEED)
    iso.fit(scaler.transform(Xtr))
    s_te = iso.score_samples(scaler.transform(Xte))
    hz = anomaly.HourlyZScore(z_thr=3.0).fit(tr["ppm_mean"].to_numpy(), tr.index.hour)
    z_te = np.abs(hz.score(te["ppm_mean"].to_numpy(), te.index.hour))
    res = {"data": "real" if a.data else "simulated", "train_windows": len(tr), "test_windows": len(te)}
    if "leak" in te:
        y = te["leak"].to_numpy().astype(int)
        pred_if = (s_te > iso.threshold_).astype(int)
        pred_z = (z_te > 3.0).astype(int)
        days = (te.index[-1] - te.index[0]).total_seconds() / 86400
        for name, score, pred in [("IsolationForest", s_te, pred_if), ("HourlyZScore", z_te, pred_z)]:
            # phát hiện theo sự kiện rò rỉ (các đoạn leak liên tiếp)
            seg = np.flatnonzero(np.diff(np.r_[0, y, 0]) != 0).reshape(-1, 2)
            det, lat = 0, []
            for s, e in seg:
                hit = pred[s:e]
                if hit.any():
                    det += 1
                    lat.append(int(hit.argmax()) * 10)
            fp_windows = int(((pred == 1) & (y == 0)).sum())
            res[name] = {"ROC_AUC": metrics.roc_auc(y, score), "precision": metrics.precision_binary(y, pred),
                         "recall": metrics.recall_binary(y, pred), "events": int(len(seg)), "events_detected": det,
                         "median_latency_min": float(np.median(lat)) if lat else None,
                         "false_alarm_windows_per_day": fp_windows / days}
            print(f"  {name:16s} AUC={res[name]['ROC_AUC']:.3f} P={res[name]['precision']:.2f} R={res[name]['recall']:.2f} "
                  f"events {det}/{len(seg)} latency={res[name]['median_latency_min']} phút FP/ngày={fp_windows / days:.2f}")
    # CUSUM trôi R0: ước lượng R0 mỗi ngày từ giờ "sạch" nhất (2h–4h sáng, không nấu ăn)
    clean = raw[(raw.index.hour >= 2) & (raw.index.hour < 4)]
    daily_ratio = clean["rs_r0"].resample("1D").median().dropna()
    cus = anomaly.CUSUM(k=0.5, h=4.0).fit(daily_ratio.iloc[:10].to_numpy())
    det = cus.detect(daily_ratio.to_numpy())
    first = next((i for i, d in det["alarms"]), None)
    res["CUSUM_R0"] = {"days": len(daily_ratio), "drift_start_day": None if a.data else 18,
                       "first_alarm_day": first, "alarms": det["alarms"],
                       "suggest_recalibration": first is not None}
    print(f"  CUSUM R0: trôi bắt đầu ngày 18 (mô phỏng), báo động đầu tiên ngày {first}")
    save_model({"scaler": scaler, "iforest": iso, "hourly_z": hz, "features": WINDOW_FEATURES, "window": "10min",
                "cusum": cus}, MODELS_DIR / "gas_anomaly", model_ver="anom-v1", meta={"synthetic": a.data is None})
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    (EXPERIMENTS_DIR / "anomaly_results.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
    L = ["# Phát hiện bất thường ở cloud", "", f"Dữ liệu: **{res['data']}** — 20 ngày train (bình thường), 10 ngày test "
         f"có {len(leak_days)} sự cố rò rỉ chậm cài vào.", "",
         "| Phương pháp | ROC-AUC | Precision | Recall | Sự cố phát hiện | Trễ trung vị (phút) | Cửa sổ báo nhầm/ngày |",
         "|---|---|---|---|---|---|---|"]
    for n in ("IsolationForest", "HourlyZScore"):
        if n in res:
            r = res[n]
            L.append(f"| {n} | {r['ROC_AUC']:.3f} | {r['precision']:.2f} | {r['recall']:.2f} | {r['events_detected']}/{r['events']} "
                     f"| {r['median_latency_min']} | {r['false_alarm_windows_per_day']:.2f} |")
    L += ["", f"CUSUM trên R0 hằng ngày: trôi bắt đầu ngày {res['CUSUM_R0']['drift_start_day']}, "
              f"báo động đầu tiên ngày {res['CUSUM_R0']['first_alarm_day']} ⇒ đề xuất hiệu chuẩn lại MQ-2."]
    (REPO_DIR / "docs" / "report" / "results_anomaly.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
