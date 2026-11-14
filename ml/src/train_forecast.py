"""Huấn luyện & so sánh mô hình dự báo thời tiết 1/3/6 giờ trên dữ liệu Open-Meteo tại VKU.

Mô hình lấy từ thư viện chuẩn:
  - Persistence, Seasonal naive: baseline (không học)
  - Holt-Winters: statsmodels ExponentialSmoothing (cộng tính, trend tắt dần, mùa 24 h)
  - Ridge, Logistic: scikit-learn
  - GBDT: LightGBM (LGBMRegressor / LGBMClassifier) — mô hình được triển khai
  - GRU: PyTorch (chỉ để so sánh; bỏ qua nếu chưa cài torch)
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn import metrics as skm
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler

from . import features as fe
from .config import EXPERIMENTS_DIR, ML_DIR, MODELS_DIR, REPO_DIR
from .mdtable import align_tables
from .serialize import dataset_hash, save_model
from .tracking import ModelRegistry, log_experiment

FIG_DIR = REPO_DIR / "docs" / "report" / "figures"
GRU_NAME = "GRU (PyTorch)"


def load_dataset(cfg):
    raw = pd.read_csv(ML_DIR / cfg["data_csv"], parse_dates=["time"], index_col="time")
    can = fe.clean(fe.open_meteo_to_canonical(raw))
    F = fe.build_features(can)
    Y = fe.build_targets(can, cfg["horizons"])
    ok = F.notna().all(axis=1) & Y.notna().all(axis=1)
    idx = F.index[ok]
    t_end = pd.Timestamp(cfg["split"]["train_end"])
    v_end = pd.Timestamp(cfg["split"]["val_end"])
    gap = pd.Timedelta(hours=max(cfg["horizons"]))
    tr = idx[idx <= t_end - gap]
    va = idx[(idx > t_end) & (idx <= v_end - gap)]
    te = idx[idx > v_end]
    return can, F, Y, tr, va, te


# ------------------------------------------------------------------ độ đo (scikit-learn)
def regression_report(y, yhat):
    return {"MAE": float(skm.mean_absolute_error(y, yhat)), "RMSE": float(skm.root_mean_squared_error(y, yhat)),
            "R2": float(skm.r2_score(y, yhat))}


def binary_report(y, p, threshold=0.5):
    yhat = (np.asarray(p) >= threshold).astype(int)
    return {"Accuracy": float(skm.accuracy_score(y, yhat)),
            "Precision": float(skm.precision_score(y, yhat, zero_division=0)),
            "Recall": float(skm.recall_score(y, yhat, zero_division=0)),
            "F1": float(skm.f1_score(y, yhat, zero_division=0)),
            "ROC_AUC": float(skm.roc_auc_score(y, p)), "Brier": float(skm.brier_score_loss(y, p)),
            "LogLoss": float(skm.log_loss(y, np.clip(p, 1e-6, 1 - 1e-6))), "threshold": float(threshold)}


def best_f1_threshold(y, p, grid=np.linspace(0.05, 0.95, 91)):
    scores = [skm.f1_score(y, (np.asarray(p) >= t).astype(int), zero_division=0) for t in grid]
    i = int(np.argmax(scores))
    return float(grid[i]), float(scores[i])


# ------------------------------------------------------------------ Holt-Winters (statsmodels)
def holt_winters_rolling(series: pd.Series, fit_end, fit_hours, m, h):
    """Ước lượng tham số trên `fit_hours` giờ cuối của train, rồi chạy bộ lọc với tham số cố định qua toàn chuỗi
    và lấy dự báo h bước tại mỗi thời điểm t: ℓ_t + (φ+…+φ^h)·b_t + s_{t+h−m}."""
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    y = series.interpolate(limit_direction="both")
    start = y.loc[:fit_end].index[-fit_hours]
    y = y.loc[start:]
    fit_y = y.loc[:fit_end].to_numpy()
    spec = dict(trend="add", damped_trend=True, seasonal="add", seasonal_periods=m)
    fit = ExponentialSmoothing(fit_y, initialization_method="estimated", **spec).fit(optimized=True)
    p = fit.params
    full = ExponentialSmoothing(y.to_numpy(), initialization_method="known", initial_level=p["initial_level"],
                                initial_trend=p["initial_trend"], initial_seasonal=p["initial_seasons"],
                                **spec).fit(smoothing_level=p["smoothing_level"], smoothing_trend=p["smoothing_trend"],
                                            smoothing_seasonal=p["smoothing_seasonal"],
                                            damping_trend=p["damping_trend"], optimized=False)
    lvl, tr_, sea = np.asarray(full.level), np.asarray(full.trend), np.asarray(full.season)
    phi = p["damping_trend"]
    damp = sum(phi ** i for i in range(1, h + 1))
    n = len(y)
    out = np.full(n, np.nan)
    t = np.arange(m, n)
    out[t] = lvl[t] + damp * tr_[t] + sea[t + h - m]
    # tự kiểm tra: công thức trùng với forecast() của statsmodels tại cuối đoạn ước lượng
    k = len(fit_y) - 1
    ref = fit.forecast(h)[-1]
    mine = np.asarray(fit.level)[k] + damp * np.asarray(fit.trend)[k] + np.asarray(fit.season)[k + h - m]
    assert np.isclose(ref, mine, atol=1e-6), (ref, mine)
    return pd.Series(out, index=y.index), {k: float(np.asarray(v).ravel()[0]) if np.ndim(v) else float(v)
                                           for k, v in p.items() if k.startswith(("smoothing", "damping"))}


# ------------------------------------------------------------------ GRU (PyTorch)
def gru_sequences(F, idx, window, cols, scaler):
    base = scaler.transform(F[cols].to_numpy())
    pos = F.index.get_indexer(idx)
    mask = pos >= window - 1
    pos = pos[mask]
    win = np.stack([base[p - window + 1:p + 1] for p in pos])
    return np.nan_to_num(win).astype(np.float32), mask


def train_gru(Xtr, Ytr, Xva, Yva, g, seed):
    import torch
    from torch import nn

    torch.manual_seed(seed)

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.gru = nn.GRU(Xtr.shape[2], g["hidden"], batch_first=True)
            self.head = nn.Linear(g["hidden"], Ytr.shape[1])

        def forward(self, x):
            out, _ = self.gru(x)
            return self.head(out[:, -1])

    net = Net()
    opt = torch.optim.Adam(net.parameters(), lr=g["lr"])
    loss_fn = nn.MSELoss()
    xt, yt = torch.from_numpy(Xtr), torch.from_numpy(Ytr.astype(np.float32))
    xv, yv = torch.from_numpy(Xva), torch.from_numpy(Yva.astype(np.float32))
    gen = torch.Generator().manual_seed(seed)
    best, best_state, bad = np.inf, None, 0
    for ep in range(g["epochs"]):
        net.train()
        perm = torch.randperm(len(xt), generator=gen)
        for i in range(0, len(xt), g["batch_size"]):
            b = perm[i:i + g["batch_size"]]
            opt.zero_grad()
            loss = loss_fn(net(xt[b]), yt[b])
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
        net.eval()
        with torch.no_grad():
            v = float(loss_fn(net(xv), yv))
        print(f"  GRU epoch {ep + 1:2d}: val MSE {v:.4f}")
        if v < best - 1e-5:
            best, best_state, bad = v, {k: t.clone() for k, t in net.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= 5:
                break
    net.load_state_dict(best_state)
    net.eval()
    return net


def gru_predict(net, X):
    import torch
    with torch.no_grad():
        return net(torch.from_numpy(X)).numpy()


# ------------------------------------------------------------------ LightGBM
def lgb_params(c, seed):
    return dict(n_estimators=c["n_estimators"], learning_rate=c["learning_rate"], max_depth=c["max_depth"],
                num_leaves=c["num_leaves"], min_child_samples=c["min_child_samples"], reg_lambda=c["reg_lambda"],
                subsample=c["subsample"], subsample_freq=1, colsample_bytree=c["colsample_bytree"],
                max_bin=c["max_bin"], random_state=seed, n_jobs=-1, verbose=-1)


def fit_lgb(model, Xtr, ytr, Xva, yva, rounds):
    t0 = time.perf_counter()
    model.fit(Xtr, ytr, eval_set=[(Xva, yva)],
              callbacks=[lgb.early_stopping(rounds, verbose=False), lgb.log_evaluation(0)])
    return time.perf_counter() - t0


def gain_importance(model, cols, top=15):
    g = model.booster_.feature_importance(importance_type="gain").astype(float)
    g = g / g.sum() if g.sum() > 0 else g
    order = np.argsort(-g)[:top]
    return [(cols[i], float(g[i])) for i in order]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ML_DIR / "configs" / "forecast.json"))
    ap.add_argument("--no-gru", action="store_true")
    ap.add_argument("--quick", action="store_true", help="ít cây hơn để chạy thử nhanh")
    ap.add_argument("--force-promote", action="store_true",
                    help="thăng cấp model mới kể cả khi không tốt hơn (dùng khi đổi định dạng model)")
    a = ap.parse_args(argv)
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    seed = cfg["seed"]
    if a.quick:
        cfg["gbdt_reg"]["n_estimators"] = cfg["gbdt_clf"]["n_estimators"] = 60
        cfg["gru"]["epochs"] = 2
    if a.no_gru:
        cfg["gru"]["enabled"] = False
    if cfg["gru"]["enabled"]:
        try:
            import torch  # noqa: F401
        except ImportError:
            print("Chưa cài PyTorch — bỏ qua GRU (pip install torch).")
            cfg["gru"]["enabled"] = False

    t_all = time.perf_counter()
    can, F, Y, tr, va, te = load_dataset(cfg)
    cols = list(F.columns)
    print(f"Dữ liệu: {len(F)} giờ, {len(cols)} feature | train {len(tr)} ({tr.min():%Y-%m} → {tr.max():%Y-%m}), "
          f"val {len(va)}, test {len(te)} ({te.min():%Y-%m} → {te.max():%Y-%m})")
    Xtr, Xva, Xte = (F.loc[i, cols].to_numpy() for i in (tr, va, te))
    dhash = dataset_hash(Xtr)
    scaler = StandardScaler().fit(Xtr)
    Ztr, Zva, Zte = scaler.transform(Xtr), scaler.transform(Xva), scaler.transform(Xte)
    reg = ModelRegistry()
    results = {"regression": {}, "rain": {}, "timing": {}, "importance": {}, "holt_winters": {}, "meta": {
        "n_features": len(cols), "features": cols, "train": [str(tr.min()), str(tr.max()), len(tr)],
        "val": [str(va.min()), str(va.max()), len(va)], "test": [str(te.min()), str(te.max()), len(te)],
        "data_hash": dhash, "seed": seed}}
    test_preds = {}
    model_dir = MODELS_DIR / "forecast"

    gru_pred = {}
    if cfg["gru"]["enabled"]:
        g = cfg["gru"]
        seq_cols = ["temp", "hum", "pres", "dew", "dpd", "sky", "is_rain", "hour_sin", "hour_cos",
                    "doy_sin", "doy_cos", "pres_d3"]
        s_seq = StandardScaler().fit(F.loc[tr, seq_cols].to_numpy())
        out_cols = [f"{t}_{h}h" for t in cfg["targets"] for h in cfg["horizons"]]
        y_sc = StandardScaler().fit(Y.loc[tr, out_cols].to_numpy())
        Xs_tr, m_tr = gru_sequences(F, tr, g["window"], seq_cols, s_seq)
        Xs_va, m_va = gru_sequences(F, va, g["window"], seq_cols, s_seq)
        Xs_te, m_te = gru_sequences(F, te, g["window"], seq_cols, s_seq)
        Ys_tr = y_sc.transform(Y.loc[tr[m_tr], out_cols].to_numpy())
        Ys_va = y_sc.transform(Y.loc[va[m_va], out_cols].to_numpy())
        t0 = time.perf_counter()
        print(f"GRU (PyTorch): {Xs_tr.shape} …")
        net = train_gru(Xs_tr, Ys_tr, Xs_va, Ys_va, g, seed)
        results["timing"]["gru_train_s"] = time.perf_counter() - t0
        P = y_sc.inverse_transform(gru_predict(net, Xs_te))
        full = np.full((len(te), len(out_cols)), np.nan)
        full[m_te] = P
        for j, c in enumerate(out_cols):
            gru_pred[c] = full[:, j]

    for target in cfg["targets"]:
        x_abs = can[target]
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
            hw_all, hw_par = holt_winters_rolling(x_abs, tr.max(), cfg["holt_winters"]["fit_last_hours"],
                                                  cfg["holt_winters"]["season_length"], h)
            preds["Holt-Winters"] = hw_all.reindex(te).to_numpy() - base_te
            timing["Holt-Winters"] = time.perf_counter() - t0
            results["holt_winters"][key] = hw_par
            t0 = time.perf_counter()
            best = None
            for al in cfg["ridge_alphas"]:
                r = Ridge(alpha=al).fit(Ztr, ytr)
                e = skm.mean_absolute_error(yva, r.predict(Zva))
                if best is None or e < best[0]:
                    best = (e, al, r)
            ridge = best[2]
            preds["Ridge"] = ridge.predict(Zte)
            timing["Ridge"] = time.perf_counter() - t0
            gb = lgb.LGBMRegressor(objective="regression", **lgb_params(cfg["gbdt_reg"], seed))
            fit_s = fit_lgb(gb, Xtr, ytr, Xva, yva, cfg["gbdt_reg"]["early_stopping_rounds"])
            t0 = time.perf_counter()
            preds["GBDT"] = gb.predict(Xte)
            infer = (time.perf_counter() - t0) / len(te)
            n_trees = gb.booster_.num_trees()
            timing["GBDT"] = fit_s
            print(f"  GBDT (LightGBM): {n_trees} cây (best_iter {gb.best_iteration_}), {fit_s:.1f}s, "
                  f"suy luận {infer * 1e6:.1f} µs/mẫu")
            if key in gru_pred:
                preds[GRU_NAME] = gru_pred[key]
            res = {}
            for name, p in preds.items():
                m = np.isfinite(p)
                res[name] = regression_report(true_te[m], base_te[m] + p[m])
                res[name]["n"] = int(m.sum())
            res["_val_MAE"] = {"Ridge": best[0], "GBDT": float(skm.mean_absolute_error(yva, gb.predict(Xva))),
                               "ridge_alpha": best[1]}
            res["_timing_s"] = {**timing, "GBDT_infer_us_per_sample": infer * 1e6, "GBDT_trees": n_trees}
            for name in preds:
                print(f"  {name:15s} MAE={res[name]['MAE']:.3f} RMSE={res[name]['RMSE']:.3f}")
            results["regression"][key] = res
            test_preds[key] = {k: base_te + v for k, v in preds.items()} | {"true": true_te}
            use_gbdt = res["_val_MAE"]["GBDT"] <= res["_val_MAE"]["Ridge"]
            bundle = {"features": cols, "target": target, "horizon": h, "kind": "delta",
                      "model": gb if use_gbdt else ridge, "scaler": None if use_gbdt else scaler,
                      "model_name": "GBDT" if use_gbdt else "Ridge"}
            mver = f"fc-{key}-{time.strftime('%Y%m%d%H%M')}"
            path = save_model(bundle, model_dir / key, model_ver=mver, data_hash=dhash,
                              meta={"test": res[bundle["model_name"]]})
            promoted = reg.propose(f"forecast_{key}", {
                "model_ver": mver, "path": path.relative_to(ML_DIR).as_posix(), "model": bundle["model_name"],
                "metric_name": "MAE_test", "metric_value": res[bundle["model_name"]]["MAE"],
                "greater_is_better": False, "data_hash": dhash,
                "baseline_persistence_MAE": res["Persistence"]["MAE"]}, force=a.force_promote)
            print(f"  -> lưu {path.name}, model={bundle['model_name']}, promoted={promoted}")
            log_experiment(f"forecast_{key}", {**cfg["gbdt_reg"], "ridge_alpha": best[1]},
                           {k: v["MAE"] for k, v in res.items() if not k.startswith("_")}, seed, fit_s)
            if key == "temp_1h":
                results["importance"]["temp_1h_split_gain"] = gain_importance(gb, cols)
                sub = slice(0, 4000)
                pi = permutation_importance(gb, Xte[sub], yte[sub], scoring="neg_mean_absolute_error",
                                            n_repeats=3, random_state=seed)
                order = np.argsort(-pi.importances_mean)[:15]
                results["importance"]["temp_1h_permutation"] = [(cols[i], float(pi.importances_mean[i]))
                                                                for i in order]

    for h in cfg["horizons"]:
        key = f"rain_{h}h"
        print(f"\n=== {key} ===")
        ytr, yva, yte = (Y.loc[i, key].to_numpy().astype(int) for i in (tr, va, te))
        probs_va, probs_te = {}, {}
        probs_va["Persistence"] = F.loc[va, "is_rain"].to_numpy()
        probs_te["Persistence"] = F.loc[te, "is_rain"].to_numpy()
        t0 = time.perf_counter()
        best = None
        for C in cfg["logistic_C"]:
            m = LogisticRegression(C=C, max_iter=2000).fit(Ztr, ytr)
            ll = skm.log_loss(yva, m.predict_proba(Zva)[:, 1])
            if best is None or ll < best[0]:
                best = (ll, C, m)
        lr = best[2]
        lr_time = time.perf_counter() - t0
        probs_va["Logistic"], probs_te["Logistic"] = lr.predict_proba(Zva)[:, 1], lr.predict_proba(Zte)[:, 1]
        gc = lgb.LGBMClassifier(objective="binary", **lgb_params(cfg["gbdt_clf"], seed))
        gc_s = fit_lgb(gc, Xtr, ytr, Xva, yva, cfg["gbdt_clf"]["early_stopping_rounds"])
        probs_va["GBDT"], probs_te["GBDT"] = gc.predict_proba(Xva)[:, 1], gc.predict_proba(Xte)[:, 1]
        res = {}
        for name in probs_te:
            thr = 0.5 if name == "Persistence" else best_f1_threshold(yva, probs_va[name])[0]
            res[name] = binary_report(yte, probs_te[name], threshold=thr)
            res[name]["val_F1"] = float(skm.f1_score(yva, (probs_va[name] >= thr).astype(int)))
            print(f"  {name:12s} F1={res[name]['F1']:.3f} AUC={res[name]['ROC_AUC']:.3f} "
                  f"Brier={res[name]['Brier']:.3f} thr={thr:.2f}")
        res["_timing_s"] = {"Logistic": lr_time, "Logistic_C": best[1], "GBDT": gc_s,
                            "GBDT_trees": gc.booster_.num_trees()}
        res["_positive_rate_test"] = float(yte.mean())
        results["rain"][key] = res
        use_gbdt = res["GBDT"]["val_F1"] >= res["Logistic"]["val_F1"]
        name = "GBDT" if use_gbdt else "Logistic"
        bundle = {"features": cols, "target": "rain", "horizon": h, "kind": "prob",
                  "model": gc if use_gbdt else lr, "scaler": None if use_gbdt else scaler,
                  "threshold": res[name]["threshold"], "model_name": name}
        mver = f"fc-{key}-{time.strftime('%Y%m%d%H%M')}"
        path = save_model(bundle, model_dir / key, model_ver=mver, data_hash=dhash, meta={"test": res[name]})
        reg.propose(f"forecast_{key}", {"model_ver": mver, "path": path.relative_to(ML_DIR).as_posix(), "model": name,
                                        "metric_name": "F1_test", "metric_value": res[name]["F1"],
                                        "greater_is_better": True, "data_hash": dhash}, force=a.force_promote)
        log_experiment(f"forecast_{key}", cfg["gbdt_clf"], {k: v["F1"] for k, v in res.items() if not k.startswith("_")},
                       seed, gc_s)
        test_preds[key] = {"true": yte, **probs_te}
        if key == "rain_3h":
            results["importance"]["rain_3h_split_gain"] = gain_importance(gc, cols)

    results["timing"]["total_s"] = time.perf_counter() - t_all
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    (EXPERIMENTS_DIR / "forecast_results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False,
                                                                      default=float), encoding="utf-8")
    write_report(results, test_preds, te)
    print(f"\nXong trong {results['timing']['total_s']:.0f}s. Kết quả: {EXPERIMENTS_DIR / 'forecast_results.json'}")


def write_report(results, test_preds, te_idx):
    lines = ["# Kết quả dự báo thời tiết (tập test 2025)", "",
             f"Dữ liệu: Open-Meteo theo giờ tại VKU. Train {results['meta']['train'][0][:10]} → "
             f"{results['meta']['train'][1][:10]}, val 2024, test {results['meta']['test'][0][:10]} → "
             f"{results['meta']['test'][1][:10]}. {results['meta']['n_features']} feature.", "",
             "Thư viện: Holt-Winters — statsmodels; Ridge, Logistic — scikit-learn; GBDT — LightGBM; "
             "GRU — PyTorch. Độ đo — scikit-learn.", "",
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
    if "gru_train_s" in results["timing"]:
        lines.append(f"- GRU (PyTorch, 6 đầu ra chung): {results['timing']['gru_train_s']:.0f}s")
    if results["importance"]:
        lines += ["", "## Mức quan trọng feature (temp_1h, GBDT)", "",
                  "| Feature | Gain (chuẩn hoá) | | Feature | Permutation ΔMAE |", "|---|---|---|---|---|"]
        sg = results["importance"]["temp_1h_split_gain"]
        pi = results["importance"]["temp_1h_permutation"]
        for i in range(min(10, len(sg), len(pi))):
            lines.append(f"| {sg[i][0]} | {sg[i][1]:.3f} | | {pi[i][0]} | {pi[i][1]:.4f} |")
    out = REPO_DIR / "docs" / "report" / "results_forecast.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(align_tables("\n".join(lines) + "\n"), encoding="utf-8")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        FIG_DIR.mkdir(parents=True, exist_ok=True)
        idx = pd.DatetimeIndex(te_idx)
        win = (idx >= "2025-11-01") & (idx < "2025-11-15")
        fig, axes = plt.subplots(2, 1, figsize=(12, 6.5), sharex=True)
        for ax, key, unit in zip(axes, ["temp_3h", "hum_3h"], ["°C", "%"]):
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
            ax.set_title("Gain importance — LightGBM temp_1h")
            fig.tight_layout()
            fig.savefig(FIG_DIR / "importance_temp_1h.png", dpi=120)
            plt.close(fig)
    except Exception as e:
        print("Bỏ qua vẽ hình:", e)


if __name__ == "__main__":
    main()
