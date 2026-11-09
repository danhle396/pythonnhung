"""Huấn luyện & so sánh các mô hình dự báo thời tiết 1h/3h/6h — toàn bộ bằng mlcore tự viết.

    python -m aiot_ml.train_forecast --config configs/forecast.json [--no-gru] [--quick]

Mô hình hồi quy (T/H/P, dự báo thay đổi Δ = x(t+h) − x(t), cộng lại x(t) khi đánh giá):
    Persistence, Seasonal naive (cùng giờ hôm trước), Holt-Winters, Ridge, GBDT (MSE), GRU (NumPy)
Mô hình mưa (có mưa trong h giờ tới):
    Persistence (đang mưa ⇒ sẽ mưa), Logistic Regression, GBDT (log-loss)
Chia tập theo thời gian: train 2021–2023, val 2024, test 2025 (bao trọn mùa mưa tháng 9–12).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from mlcore import ensemble, explain, linear, metrics, nn, preprocessing, smoothing
from mlcore.serialize import dataset_hash, save_model

from . import features as fe
from .config import EXPERIMENTS_DIR, ML_DIR, MODELS_DIR, REPO_DIR
from .tracking import ModelRegistry, log_experiment

FIG_DIR = REPO_DIR / "docs" / "report" / "figures"


def load_dataset(cfg):
    raw = pd.read_csv(ML_DIR / cfg["data_csv"], parse_dates=["time"], index_col="time")
    can = fe.clean(fe.open_meteo_to_canonical(raw))
    F = fe.build_features(can)
    Y = fe.build_targets(can, cfg["horizons"])
    ok = F.notna().all(axis=1) & Y.notna().all(axis=1)
    idx = F.index[ok]
    t_end = pd.Timestamp(cfg["split"]["train_end"])
    v_end = pd.Timestamp(cfg["split"]["val_end"])
    gap = pd.Timedelta(hours=max(cfg["horizons"]))  # bỏ biên để target của tập trước không chạm tập sau
    tr = idx[idx <= t_end - gap]
    va = idx[(idx > t_end) & (idx <= v_end - gap)]
    te = idx[idx > v_end]
    return can, F, Y, tr, va, te


def gru_sequences(can, F, idx, window, cols, scaler):
    """Chuỗi đầu vào W giờ gần nhất cho GRU: X[i] = feature chuẩn hoá tại t−W+1..t."""
    base = scaler.transform(F[cols].to_numpy())
    pos = F.index.get_indexer(idx)
    mask = pos >= window - 1
    pos = pos[mask]
    win = np.stack([base[p - window + 1:p + 1] for p in pos])
    return np.nan_to_num(win), mask


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ML_DIR / "configs" / "forecast.json"))
    ap.add_argument("--no-gru", action="store_true")
    ap.add_argument("--quick", action="store_true", help="ít cây hơn để chạy thử nhanh")
    a = ap.parse_args(argv)
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    seed = cfg["seed"]
    if a.quick:
        cfg["gbdt_reg"]["n_estimators"] = cfg["gbdt_clf"]["n_estimators"] = 60
        cfg["gru"]["epochs"] = 3
    if a.no_gru:
        cfg["gru"]["enabled"] = False

    t_all = time.perf_counter()
    can, F, Y, tr, va, te = load_dataset(cfg)
    cols = list(F.columns)
    print(f"Dữ liệu: {len(F)} giờ, {len(cols)} feature | train {len(tr)} ({tr.min():%Y-%m} → {tr.max():%Y-%m}), "
          f"val {len(va)}, test {len(te)} ({te.min():%Y-%m} → {te.max():%Y-%m})")
    Xtr, Xva, Xte = (F.loc[i, cols].to_numpy() for i in (tr, va, te))
    dhash = dataset_hash(Xtr)
    scaler = preprocessing.StandardScaler().fit(Xtr)
    Ztr, Zva, Zte = scaler.transform(Xtr), scaler.transform(Xva), scaler.transform(Xte)
    reg = ModelRegistry()
    results = {"regression": {}, "rain": {}, "timing": {}, "importance": {}, "meta": {
        "n_features": len(cols), "features": cols, "train": [str(tr.min()), str(tr.max()), len(tr)],
        "val": [str(va.min()), str(va.max()), len(va)], "test": [str(te.min()), str(te.max()), len(te)],
        "data_hash": dhash, "seed": seed}}
    test_preds = {}
    model_dir = MODELS_DIR / "forecast"

    # ------------------------------------------------------------ GRU (một mạng dự báo đồng thời 9 đầu ra)
    gru_pred = {}
    if cfg["gru"]["enabled"]:
        g = cfg["gru"]
        seq_cols = ["temp", "hum", "pres", "dew", "dpd", "sky", "is_rain", "hour_sin", "hour_cos",
                    "doy_sin", "doy_cos", "pres_d3"]
        s_seq = preprocessing.StandardScaler().fit(F.loc[tr, seq_cols].to_numpy())
        out_cols = [f"{t}_{h}h" for t in cfg["targets"] for h in cfg["horizons"]]
        y_sc = preprocessing.StandardScaler().fit(Y.loc[tr, out_cols].to_numpy())
        Xs_tr, m_tr = gru_sequences(can, F, tr, g["window"], seq_cols, s_seq)
        Xs_va, m_va = gru_sequences(can, F, va, g["window"], seq_cols, s_seq)
        Xs_te, m_te = gru_sequences(can, F, te, g["window"], seq_cols, s_seq)
        Ys_tr = y_sc.transform(Y.loc[tr[m_tr], out_cols].to_numpy())
        Ys_va = y_sc.transform(Y.loc[va[m_va], out_cols].to_numpy())
        t0 = time.perf_counter()
        gru = nn.GRURegressor(hidden=g["hidden"], lr=g["lr"], epochs=g["epochs"], batch_size=g["batch_size"],
                              clip=1.0, patience=5, seed=seed, verbose=1)
        print(f"GRU: {Xs_tr.shape} …")
        gru.fit(Xs_tr, Ys_tr, eval_set=(Xs_va, Ys_va))
        results["timing"]["gru_train_s"] = time.perf_counter() - t0
        P = y_sc.inverse_transform(gru.predict(Xs_te))
        full = np.full((len(te), len(out_cols)), np.nan)
        full[m_te] = P
        for j, c in enumerate(out_cols):
            gru_pred[c] = full[:, j]
        save_model(gru, model_dir / "gru_all",
                   model_ver="gru-v1", data_hash=dhash,
                   meta={"seq_cols": seq_cols, "out_cols": out_cols, "window": g["window"],
                         "x_scaler": s_seq.to_dict(), "y_scaler": y_sc.to_dict()})

    # ------------------------------------------------------------ hồi quy T/H/P
    for target in cfg["targets"]:
        x_abs = can[target]
        # Holt-Winters: fit 1 lần trên chuỗi tuyệt đối (2 năm cuối của train) cho mỗi horizon
        hw_series = x_abs.loc[:tr.max()].iloc[-cfg["holt_winters"]["fit_last_hours"]:].to_numpy()
        for h in cfg["horizons"]:
            key = f"{target}_{h}h"
            print(f"\n=== {key} ===")
            ytr, yva, yte = (Y.loc[i, key].to_numpy() for i in (tr, va, te))
            base_te = x_abs.loc[te].to_numpy()
            true_te = base_te + yte
            preds, timing = {}, {}
            preds["Persistence"] = np.zeros(len(te))
            sn = fe.seasonal_naive(can, target, h)
            preds["Seasonal naive"] = pd.Series(sn, index=can.index).loc[te].to_numpy()
            t0 = time.perf_counter()
            hw = smoothing.HoltWinters(cfg["holt_winters"]["season_length"]).fit(hw_series, horizon=h)
            hw_all = pd.Series(hw.rolling_forecast(x_abs.to_numpy(), h), index=can.index)
            preds["Holt-Winters"] = hw_all.loc[te].to_numpy() - base_te
            timing["Holt-Winters"] = time.perf_counter() - t0
            # Ridge: chọn alpha trên val
            t0 = time.perf_counter()
            best = None
            for al in cfg["ridge_alphas"]:
                r = linear.Ridge(alpha=al).fit(Ztr, ytr)
                e = metrics.mae(yva, r.predict(Zva))
                if best is None or e < best[0]:
                    best = (e, al, r)
            ridge = best[2]
            preds["Ridge"] = ridge.predict(Zte)
            timing["Ridge"] = time.perf_counter() - t0
            # GBDT
            gb = ensemble.GradientBoostingRegressor(seed=seed, **cfg["gbdt_reg"])
            gb.fit(Xtr, ytr, eval_set=(Xva, yva))
            t0 = time.perf_counter()
            preds["GBDT"] = gb.predict(Xte)
            infer = (time.perf_counter() - t0) / len(te)
            timing["GBDT"] = gb.fit_time_s_
            print(f"  GBDT: {len(gb.trees_)} cây (best_iter {gb.best_iteration_}), {gb.fit_time_s_:.1f}s, "
                  f"suy luận {infer * 1e6:.1f} µs/mẫu")
            if key in gru_pred:
                preds["GRU (NumPy)"] = gru_pred[key]
            res = {}
            for name, p in preds.items():
                m = np.isfinite(p)
                res[name] = metrics.regression_report(true_te[m], base_te[m] + p[m])
                res[name]["n"] = int(m.sum())
            res["_val_MAE"] = {"Ridge": best[0], "GBDT": metrics.mae(yva, gb.predict(Xva)), "ridge_alpha": best[1]}
            res["_timing_s"] = {**timing, "GBDT_infer_us_per_sample": infer * 1e6, "GBDT_trees": len(gb.trees_)}
            for name in preds:
                print(f"  {name:15s} MAE={res[name]['MAE']:.3f} RMSE={res[name]['RMSE']:.3f}")
            results["regression"][key] = res
            test_preds[key] = {k: base_te + v for k, v in preds.items()} | {"true": true_te}
            # chọn model triển khai theo MAE val (chỉ mô hình dạng bảng — backend dùng được trực tiếp)
            use_gbdt = res["_val_MAE"]["GBDT"] <= res["_val_MAE"]["Ridge"]
            bundle = {"features": cols, "target": target, "horizon": h, "kind": "delta",
                      "model": gb if use_gbdt else ridge, "scaler": None if use_gbdt else scaler,
                      "model_name": "GBDT" if use_gbdt else "Ridge"}
            mver = f"fc-{key}-{time.strftime('%Y%m%d%H%M')}"
            path = save_model(bundle, model_dir / key, model_ver=mver, data_hash=dhash,
                              meta={"test": res[bundle["model_name"]]})
            promoted = reg.propose(f"forecast_{key}", {
                "model_ver": mver, "path": str(path.relative_to(ML_DIR)), "model": bundle["model_name"],
                "metric_name": "MAE_test", "metric_value": res[bundle["model_name"]]["MAE"],
                "greater_is_better": False, "data_hash": dhash,
                "baseline_persistence_MAE": res["Persistence"]["MAE"]})
            print(f"  -> lưu {path.name}, model={bundle['model_name']}, promoted={promoted}")
            log_experiment(f"forecast_{key}", {**cfg["gbdt_reg"], "ridge_alpha": best[1]},
                           {k: v["MAE"] for k, v in res.items() if not k.startswith("_")}, seed,
                           gb.fit_time_s_)
            if key == "temp_1h":
                results["importance"]["temp_1h_split_gain"] = explain.split_gain_importance(gb, cols)[:15]
                sub = slice(0, 4000)
                results["importance"]["temp_1h_permutation"] = explain.permutation_importance(
                    gb.predict, Xte[sub], yte[sub], metrics.mae, n_repeats=3, seed=seed, feature_names=cols)[:15]

    # ------------------------------------------------------------ mưa
    for h in cfg["horizons"]:
        key = f"rain_{h}h"
        print(f"\n=== {key} ===")
        ytr, yva, yte = (Y.loc[i, key].to_numpy().astype(int) for i in (tr, va, te))
        probs_va, probs_te = {}, {}
        now_va = F.loc[va, "is_rain"].to_numpy()
        now_te = F.loc[te, "is_rain"].to_numpy()
        probs_va["Persistence"], probs_te["Persistence"] = now_va, now_te
        t0 = time.perf_counter()
        lr = linear.LogisticRegression(seed=seed, **cfg["logistic"]).fit(Ztr, ytr)
        lr_time = time.perf_counter() - t0
        probs_va["Logistic"], probs_te["Logistic"] = lr.predict_proba(Zva)[:, 1], lr.predict_proba(Zte)[:, 1]
        gc = ensemble.GradientBoostingClassifier(seed=seed, **cfg["gbdt_clf"]).fit(Xtr, ytr, eval_set=(Xva, yva))
        probs_va["GBDT"], probs_te["GBDT"] = gc.predict_proba(Xva)[:, 1], gc.predict_proba(Xte)[:, 1]
        res = {}
        for name in probs_te:
            thr = 0.5 if name == "Persistence" else metrics.best_f1_threshold(yva, probs_va[name])[0]
            res[name] = metrics.binary_report(yte, probs_te[name], threshold=thr)
            res[name]["val_F1"] = metrics.f1_binary(yva, (probs_va[name] >= thr).astype(int))
            print(f"  {name:12s} F1={res[name]['F1']:.3f} AUC={res[name]['ROC_AUC']:.3f} "
                  f"Brier={res[name]['Brier']:.3f} thr={thr:.2f}")
        res["_timing_s"] = {"Logistic": lr_time, "GBDT": gc.fit_time_s_, "GBDT_trees": len(gc.trees_)}
        res["_positive_rate_test"] = float(yte.mean())
        results["rain"][key] = res
        use_gbdt = res["GBDT"]["val_F1"] >= res["Logistic"]["val_F1"]
        name = "GBDT" if use_gbdt else "Logistic"
        bundle = {"features": cols, "target": "rain", "horizon": h, "kind": "prob",
                  "model": gc if use_gbdt else lr, "scaler": None if use_gbdt else scaler,
                  "threshold": res[name]["threshold"], "model_name": name}
        mver = f"fc-{key}-{time.strftime('%Y%m%d%H%M')}"
        path = save_model(bundle, model_dir / key, model_ver=mver, data_hash=dhash, meta={"test": res[name]})
        reg.propose(f"forecast_{key}", {"model_ver": mver, "path": str(path.relative_to(ML_DIR)), "model": name,
                                        "metric_name": "F1_test", "metric_value": res[name]["F1"],
                                        "greater_is_better": True, "data_hash": dhash})
        log_experiment(f"forecast_{key}", cfg["gbdt_clf"], {k: v["F1"] for k, v in res.items() if not k.startswith("_")},
                       seed, gc.fit_time_s_)
        test_preds[key] = {"true": yte, **probs_te}
        if key == "rain_3h":
            results["importance"]["rain_3h_split_gain"] = explain.split_gain_importance(gc, cols)[:15]

    results["timing"]["total_s"] = time.perf_counter() - t_all
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    (EXPERIMENTS_DIR / "forecast_results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False,
                                                                      default=float), encoding="utf-8")
    write_report(results, test_preds, te)
    print(f"\nXong trong {results['timing']['total_s']:.0f}s. Kết quả: {EXPERIMENTS_DIR / 'forecast_results.json'}")


def write_report(results, test_preds, te_idx):
    """Bảng markdown cho báo cáo + hình vẽ."""
    lines = ["# Kết quả dự báo thời tiết (tập test 2025)", "",
             f"Dữ liệu: Open-Meteo theo giờ tại VKU. Train {results['meta']['train'][0][:10]} → "
             f"{results['meta']['train'][1][:10]}, val 2024, test {results['meta']['test'][0][:10]} → "
             f"{results['meta']['test'][1][:10]}. {results['meta']['n_features']} feature.", "",
             "## Hồi quy — MAE (RMSE)", ""]
    keys = list(results["regression"])
    models = [m for m in results["regression"][keys[0]] if not m.startswith("_")]
    lines.append("| Mô hình | " + " | ".join(keys) + " |")
    lines.append("|---|" + "---|" * len(keys))
    for m in models:
        cells = []
        for k in keys:
            r = results["regression"][k].get(m)
            if r is None:
                cells.append("—")
                continue
            best = min(results["regression"][k][x]["MAE"] for x in models if x in results["regression"][k])
            s = f"{r['MAE']:.3f} ({r['RMSE']:.3f})"
            cells.append(f"**{s}**" if np.isclose(r["MAE"], best) else s)
        lines.append(f"| {m} | " + " | ".join(cells) + " |")
    lines += ["", "## Dự báo mưa — F1 / ROC-AUC / Brier (ngưỡng chọn trên val)", "",
              "| Mô hình | " + " | ".join(results["rain"]) + " |", "|---|" + "---|" * len(results["rain"])]
    for m in ["Persistence", "Logistic", "GBDT"]:
        cells = [f"{results['rain'][k][m]['F1']:.3f} / {results['rain'][k][m]['ROC_AUC']:.3f} / "
                 f"{results['rain'][k][m]['Brier']:.3f}" for k in results["rain"]]
        lines.append(f"| {m} | " + " | ".join(cells) + " |")
    lines += ["", "## Thời gian huấn luyện GBDT (giây) / số cây", ""]
    for k in keys:
        t = results["regression"][k]["_timing_s"]
        lines.append(f"- {k}: {t['GBDT']:.1f}s, {t['GBDT_trees']} cây, suy luận {t['GBDT_infer_us_per_sample']:.1f} µs/mẫu")
    for k in results["rain"]:
        t = results["rain"][k]["_timing_s"]
        lines.append(f"- {k}: GBDT {t['GBDT']:.1f}s ({t['GBDT_trees']} cây), Logistic {t['Logistic']:.1f}s")
    if results["importance"]:
        lines += ["", "## Mức quan trọng feature (temp_1h, GBDT)", "", "| Feature | Split gain | | Feature | Permutation ΔMAE |",
                  "|---|---|---|---|---|"]
        sg = results["importance"]["temp_1h_split_gain"]
        pi = results["importance"]["temp_1h_permutation"]
        for i in range(min(10, len(sg), len(pi))):
            lines.append(f"| {sg[i][0]} | {sg[i][1]:.3f} | | {pi[i][0]} | {pi[i][1]:.4f} |")
    out = REPO_DIR / "docs" / "report" / "results_forecast.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        FIG_DIR.mkdir(parents=True, exist_ok=True)
        idx = pd.DatetimeIndex(te_idx)
        win = (idx >= "2025-11-01") & (idx < "2025-11-15")
        fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
        for ax, key, unit in zip(axes, ["temp_3h", "hum_3h", "pres_3h"], ["°C", "%", "hPa"]):
            tp = test_preds[key]
            ax.plot(idx[win], tp["true"][win], "k-", lw=1.4, label="Thực tế")
            for name, style in [("Persistence", ":"), ("Ridge", "--"), ("GBDT", "-")]:
                ax.plot(idx[win], tp[name][win], style, lw=1, label=name)
            ax.set_ylabel(f"{key} ({unit})")
            ax.grid(alpha=0.3)
        axes[0].legend(ncol=4, fontsize=8)
        axes[0].set_title("Dự báo 3h — 1–14/11/2025 (tập test, mùa mưa)")
        fig.tight_layout()
        fig.savefig(FIG_DIR / "forecast_3h_nov2025.png", dpi=120)
        plt.close(fig)
        sg = results["importance"].get("temp_1h_split_gain")
        if sg:
            fig, ax = plt.subplots(figsize=(7, 5))
            ax.barh([s[0] for s in sg[:12]][::-1], [s[1] for s in sg[:12]][::-1])
            ax.set_title("Split-gain importance — GBDT temp_1h")
            fig.tight_layout()
            fig.savefig(FIG_DIR / "importance_temp_1h.png", dpi=120)
            plt.close(fig)
    except Exception as e:  # không có matplotlib vẫn chạy được
        print("Bỏ qua vẽ hình:", e)


if __name__ == "__main__":
    main()
