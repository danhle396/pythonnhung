from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from sklearn import metrics as skm
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from . import prep as pp
from .mdtable import align_tables
from .serialize import save_model

from .config import EXPERIMENTS_DIR, MODELS_DIR, REPO_DIR, SEED

WINDOW_FEATURES = ["ppm_mean", "ppm_std", "ppm_slope", "ppm_d60", "temp", "hum", "hour_sin", "hour_cos"]


def window_features(df: pd.DataFrame, freq="10min") -> pd.DataFrame:
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
    ap.add_argument("--data", required=True, help="CSV telemetry đo thật của trạm")
    ap.add_argument("--train-days", type=float, default=20, help="số ngày đầu dùng để học trạng thái bình thường")
    a = ap.parse_args(argv)
    raw = pd.read_csv(a.data, parse_dates=["ts"]).set_index("ts").sort_index()
    W = window_features(raw)
    split = W.index[0] + pd.Timedelta(days=a.train_days)
    tr, te = W[W.index < split], W[W.index >= split]
    Xtr, Xte = tr[WINDOW_FEATURES].to_numpy(), te[WINDOW_FEATURES].to_numpy()
    scaler = StandardScaler().fit(Xtr)
    iso = IsolationForest(n_estimators=200, max_samples=256, contamination=0.01, random_state=SEED)
    iso.fit(scaler.transform(Xtr))
    s_te = -iso.score_samples(scaler.transform(Xte))  # càng lớn càng bất thường
    hz = pp.HourlyZScore(z_thr=3.0).fit(tr["ppm_mean"].to_numpy(), tr.index.hour)
    z_te = np.abs(hz.score(te["ppm_mean"].to_numpy(), te.index.hour))
    res = {"data": str(a.data), "train_windows": len(tr), "test_windows": len(te)}
    if "leak" in te:
        y = te["leak"].to_numpy().astype(int)
        pred_if = (iso.predict(scaler.transform(Xte)) == -1).astype(int)
        pred_z = (z_te > 3.0).astype(int)
        days = (te.index[-1] - te.index[0]).total_seconds() / 86400
        for name, score, pred in [("IsolationForest", s_te, pred_if), ("HourlyZScore", z_te, pred_z)]:
            seg = np.flatnonzero(np.diff(np.r_[0, y, 0]) != 0).reshape(-1, 2)
            det, lat = 0, []
            for s, e in seg:
                hit = pred[s:e]
                if hit.any():
                    det += 1
                    lat.append(int(hit.argmax()) * 10)
            fp_windows = int(((pred == 1) & (y == 0)).sum())
            res[name] = {"ROC_AUC": float(skm.roc_auc_score(y, score)),
                         "precision": float(skm.precision_score(y, pred, zero_division=0)),
                         "recall": float(skm.recall_score(y, pred, zero_division=0)), "events": int(len(seg)), "events_detected": det,
                         "median_latency_min": float(np.median(lat)) if lat else None,
                         "false_alarm_windows_per_day": fp_windows / days}
            print(f"  {name:16s} AUC={res[name]['ROC_AUC']:.3f} P={res[name]['precision']:.2f} R={res[name]['recall']:.2f} "
                  f"events {det}/{len(seg)} latency={res[name]['median_latency_min']} phút FP/ngày={fp_windows / days:.2f}")
    clean = raw[(raw.index.hour >= 2) & (raw.index.hour < 4)]
    daily_ratio = clean["rs_r0"].resample("1D").median().dropna()
    cus = pp.CUSUM(k=0.5, h=4.0).fit(daily_ratio.iloc[:10].to_numpy())
    det = cus.detect(daily_ratio.to_numpy())
    first = next((i for i, d in det["alarms"]), None)
    res["CUSUM_R0"] = {"days": len(daily_ratio), "first_alarm_day": first, "alarms": det["alarms"],
                       "suggest_recalibration": first is not None}
    print(f"  CUSUM R0: {len(daily_ratio)} ngày, báo động đầu tiên ngày {first}")
    save_model({"scaler": scaler, "iforest": iso, "hourly_z": hz, "features": WINDOW_FEATURES, "window": "10min",
                "cusum": cus}, MODELS_DIR / "gas_anomaly", model_ver="anom-v1", meta={"data": str(a.data)})
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    (EXPERIMENTS_DIR / "anomaly_results.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
    L = ["# Phát hiện bất thường ở cloud", "", f"Dữ liệu đo thật: `{res['data']}` — {res['train_windows']} cửa sổ 10 phút "
         f"train, {res['test_windows']} cửa sổ test.", "",
         "| Phương pháp | ROC-AUC | Precision | Recall | Sự cố phát hiện | Trễ trung vị (phút) | Cửa sổ báo nhầm/ngày |",
         "|---|---|---|---|---|---|---|"]
    for n in ("IsolationForest", "HourlyZScore"):
        if n in res:
            r = res[n]
            L.append(f"| {n} | {r['ROC_AUC']:.3f} | {r['precision']:.2f} | {r['recall']:.2f} | {r['events_detected']}/{r['events']} "
                     f"| {r['median_latency_min']} | {r['false_alarm_windows_per_day']:.2f} |")
    L += ["", f"CUSUM trên R0 hằng ngày ({res['CUSUM_R0']['days']} ngày): báo động đầu tiên ngày "
              f"{res['CUSUM_R0']['first_alarm_day']}" + (" ⇒ đề xuất hiệu chuẩn lại MQ-2." if first is not None else ".")]
    (REPO_DIR / "docs" / "report" / "results_anomaly.md").write_text(align_tables("\n".join(L) + "\n"), encoding="utf-8")


if __name__ == "__main__":
    main()
