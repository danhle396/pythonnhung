from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from sklearn import metrics as skm
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import make_scorer
from sklearn.tree import DecisionTreeClassifier

from .config import EXPERIMENTS_DIR, FIRMWARE_SRC, FIRMWARE_TESTS, MODELS_DIR, REPO_DIR, SEED
from .gas_edge import EDGE_FEATURES, LEVEL_NAMES, RuleConfig, extract_features_stream, run_levels_vectorized
from .export_micropython import (export_forest_micropython, forest_to_arrays, load_module_from_source,
                                 predict_float32, to_float32_list)
from .mdtable import align_tables
from .serialize import dataset_hash, save_model
from .tracking import ModelRegistry, log_experiment

CLASS_WEIGHT = {0: 1.0, 1: 1.5, 2: 4.0, 3: 6.0}


REQUIRED_COLUMNS = ["t", "gas_ppm", "rs_r0", "temp", "hum", "lux", "label", "scenario", "event_id", "stream_seed"]


def build_dataset(args):
    path = Path(args.data)
    if not path.exists():
        raise SystemExit(f"Không tìm thấy {path}. Thu dữ liệu đo thật bằng tools/label_logger.py trước khi huấn luyện.")
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df]
    if missing:
        raise SystemExit(f"CSV thiếu cột {missing}")
    if df["stream_seed"].nunique() < 3:
        raise SystemExit("Cần ít nhất 3 buổi thí nghiệm (stream_seed khác nhau) để chia train/val/test theo buổi.")
    feats = []
    for seed, g in df.groupby("stream_seed", sort=True):
        F = extract_features_stream(g)
        feats.append(pd.DataFrame(F, columns=EDGE_FEATURES, index=g.index))
    F = pd.concat(feats).loc[df.index]
    return df, F


def event_metrics(df, pred):
    out = {"events_ge2": 0, "detected_ge2": 0, "latency_s": [], "nuisance_events": 0, "nuisance_alarm_l1": 0,
           "nuisance_alarm_l2": 0, "clean_events": 0, "clean_alarm_l1": 0}
    d = df.assign(pred=pred)
    for (_, _), g in d.groupby(["stream_seed", "event_id"], sort=False):
        lab = int(g["label"].max())
        sc = g["scenario"].iloc[0]
        if lab >= 2:
            out["events_ge2"] += 1
            act = g[g["label"] >= 2]
            win = g.loc[act.index.min():act.index.max() + 10]
            hit = win["pred"] >= 2
            if hit.any():
                out["detected_ge2"] += 1
                out["latency_s"].append(int(hit.to_numpy().argmax()))
        if sc in ("steam", "alcohol", "perfume"):
            out["nuisance_events"] += 1
            out["nuisance_alarm_l1"] += int((g["pred"] >= 1).any())
            out["nuisance_alarm_l2"] += int((g["pred"] >= 2).any())
        if sc == "clean":
            out["clean_events"] += 1
            out["clean_alarm_l1"] += int((g["pred"] >= 1).any())
    lat = out.pop("latency_s")
    out["event_recall_ge2"] = out["detected_ge2"] / max(out["events_ge2"], 1)
    out["latency_median_s"] = float(np.median(lat)) if lat else None
    out["latency_p95_s"] = float(np.percentile(lat, 95)) if lat else None
    out["nuisance_fp_rate_l1"] = out["nuisance_alarm_l1"] / max(out["nuisance_events"], 1)
    out["nuisance_fp_rate_l2"] = out["nuisance_alarm_l2"] / max(out["nuisance_events"], 1)
    out["clean_fp_rate"] = out["clean_alarm_l1"] / max(out["clean_events"], 1)
    return out


def recall_ge2(y, pred):
    return float(skm.recall_score(np.asarray(y) >= 2, np.asarray(pred) >= 2, zero_division=0))


def sample_metrics(y, pred):
    labels = [0, 1, 2, 3]
    p, r, f, _ = skm.precision_recall_fscore_support(y, pred, labels=labels, zero_division=0)
    return {"macro_f1": float(f.mean()), "recall_ge2": recall_ge2(y, pred),
            "precision_ge2": float(skm.precision_score(y >= 2, pred >= 2, zero_division=0)),
            "per_class": [{"precision": float(p[k]), "recall": float(r[k]), "f1": float(f[k])} for k in labels],
            "confusion_matrix": skm.confusion_matrix(y, pred, labels=labels).tolist()}


def python_parity(src, X, cls_idx, proba):
    mod = load_module_from_source(src)
    bad, md = 0, 0.0
    xs = [to_float32_list(x) for x in X]
    t0 = time.perf_counter()
    for i, x in enumerate(xs):
        k, p = mod.predict_proba(x)
        bad += int(k != cls_idx[i])
        md = max(md, max(abs(a - b) for a, b in zip(p, proba[i])))
    us = (time.perf_counter() - t0) / max(1, len(xs)) * 1e6
    return {"checked": len(xs), "mismatches": bad, "max_proba_diff": md, "pc_us_per_inference": us}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="CSV đo thật có gán nhãn (tools/label_logger.py)")
    ap.add_argument("--model-ver", default="gas-v1")
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    df, F = build_dataset(a)
    seeds = sorted(df["stream_seed"].unique())
    n = len(seeds)
    s_tr, s_va, s_te = seeds[:int(n * 0.6)], seeds[int(n * 0.6):int(n * 0.8)], seeds[int(n * 0.8):]
    m_tr, m_va, m_te = (df["stream_seed"].isin(s).to_numpy() for s in (s_tr, s_va, s_te))
    X, y = F.to_numpy(), df["label"].to_numpy().astype(int)
    print(f"Dữ liệu đo thật {a.data}: {len(df)} mẫu 1 Hz, {df.groupby(['stream_seed', 'event_id']).ngroups} "
          f"sự kiện | phân bố nhãn {np.bincount(y, minlength=4).tolist()} | train/val/test streams {len(s_tr)}/{len(s_va)}/{len(s_te)}")

    cands = []
    for depth in (4, 5, 6):
        cands.append(("DecisionTree", {"max_depth": depth},
                      lambda d=depth: DecisionTreeClassifier(max_depth=d, min_samples_leaf=20,
                                                             class_weight=CLASS_WEIGHT, random_state=SEED)))
    for nt, depth in ((5, 5), (10, 5), (10, 6)):
        cands.append(("RandomForest", {"n_estimators": nt, "max_depth": depth},
                      lambda nt=nt, d=depth: RandomForestClassifier(
                          n_estimators=nt, max_depth=d, min_samples_leaf=20, max_features=0.6,
                          class_weight=CLASS_WEIGHT, random_state=SEED, n_jobs=-1)))
    best = None
    sel_log = []
    for name, params, make in cands:
        ts = time.perf_counter()
        m = make().fit(X[m_tr], y[m_tr])
        fit_s = time.perf_counter() - ts
        pv = m.predict(X[m_va])
        lv, _ = run_levels_vectorized(X[m_va], pv, "hybrid")
        sm = sample_metrics(y[m_va], lv)
        ev = event_metrics(df[m_va], lv)
        n_nodes = len(forest_to_arrays(m)["feature"])
        score = (ev["event_recall_ge2"] * 2 + sm["recall_ge2"] - 1.5 * ev["nuisance_fp_rate_l2"]
                 + sm["macro_f1"] - n_nodes / 20000)
        sel_log.append({"model": name, **params, "val_score": score, "val_event_recall_ge2": ev["event_recall_ge2"],
                        "val_recall_ge2": sm["recall_ge2"], "val_macro_f1": sm["macro_f1"],
                        "val_nuisance_fp_l2": ev["nuisance_fp_rate_l2"], "nodes": n_nodes, "fit_s": fit_s})
        print(f"  {name:12s} {params} score={score:.3f} evRec≥2={ev['event_recall_ge2']:.3f} "
              f"rec≥2={sm['recall_ge2']:.3f} F1={sm['macro_f1']:.3f} FP2={ev['nuisance_fp_rate_l2']:.2f} nodes={n_nodes}")
        if best is None or score > best[0]:
            best = (score, name, params, m)
    _, best_name, best_params, model = best
    print(f"-> chọn {best_name} {best_params}")

    Xte, yte, dte = X[m_te], y[m_te], df[m_te]
    pte = model.predict(Xte)
    comp = {}
    for mode in ("rule", "model", "hybrid"):
        lv, _ = run_levels_vectorized(Xte, pte, mode)
        comp[mode] = {**sample_metrics(yte, lv), **event_metrics(dte, lv)}
        c = comp[mode]
        print(f"  {mode:7s} macroF1={c['macro_f1']:.3f} recall≥2={c['recall_ge2']:.3f} evRecall≥2={c['event_recall_ge2']:.3f} "
              f"FP(nhiễu,≥1)={c['nuisance_fp_rate_l1']:.2f} FP(nhiễu,≥2)={c['nuisance_fp_rate_l2']:.2f} "
              f"latency={c['latency_median_s']}s")
    raw_model = sample_metrics(yte, pte)

    src = export_forest_micropython(model, EDGE_FEATURES, model_ver=a.model_ver, class_names=LEVEL_NAMES)
    rng = np.random.default_rng(SEED)
    pick = np.sort(np.r_[rng.choice(np.flatnonzero(yte == 0), min(250, int((yte == 0).sum())), replace=False),
                         *[np.flatnonzero(yte == k)[:: max(1, (yte == k).sum() // 80)][:80] for k in (1, 2, 3)]])
    cls_idx, proba = predict_float32(model, Xte[pick])
    python_match = float((model.classes_[cls_idx] == model.predict(Xte[pick])).mean())
    (FIRMWARE_SRC / "gas_model.py").write_text(src, encoding="utf-8")
    (FIRMWARE_TESTS / "gas_model_testvec.json").write_text(json.dumps(
        {"x": [to_float32_list(x) for x in Xte[pick]], "class_idx": cls_idx.tolist()}), encoding="utf-8")
    parity = python_parity(src, Xte[pick], cls_idx, proba)
    parity["float32_vs_float64_match"] = python_match
    A = forest_to_arrays(model)
    n_nodes, n_leaves = len(A["feature"]), int((A["feature"] < 0).sum())
    flash = n_nodes * (10 if n_nodes < 32767 else 16) + n_leaves * 4 * 4 + len(A["roots"]) * 2
    print(f"  MicroPython parity: {parity} | ~{flash / 1024:.1f} kB dữ liệu model, {n_nodes} nút")

    dh = dataset_hash(X[m_tr], y[m_tr])
    path = save_model({"model": model, "features": EDGE_FEATURES, "class_weight": CLASS_WEIGHT,
                       "rule_config": RuleConfig().__dict__}, MODELS_DIR / "gas_edge", model_ver=a.model_ver,
                      data_hash=dh, meta={"data": str(a.data)})
    order = np.argsort(-model.feature_importances_)
    imp = [(EDGE_FEATURES[i], float(model.feature_importances_[i])) for i in order]
    pi = permutation_importance(model, Xte[:20000], yte[:20000], scoring=make_scorer(recall_ge2), n_repeats=3,
                                random_state=SEED)
    perm = [(EDGE_FEATURES[i], float(pi.importances_mean[i])) for i in np.argsort(-pi.importances_mean)]
    res = {"data": str(a.data), "n_samples": int(len(df)),
           "label_counts": np.bincount(y, minlength=4).tolist(), "selection": sel_log,
           "chosen": {"model": best_name, **best_params}, "test_raw_model": raw_model, "test_comparison": comp,
           "edge_resources": {"nodes": n_nodes, "leaves": n_leaves, "trees": len(A["roots"]),
                              "flash_bytes_est": flash, "ram_bytes_runtime": 4 * (10 + 4) + 4 * (30 + 60 + 60)},
           "micropython_parity": parity, "importance_split_gain": imp, "importance_permutation_recall_ge2": perm,
           "model_path": str(path)}
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    (EXPERIMENTS_DIR / "gas_edge_results.json").write_text(json.dumps(res, indent=2, ensure_ascii=False, default=float),
                                                           encoding="utf-8")
    ModelRegistry().propose("gas_edge", {"model_ver": a.model_ver, "path": str(path.name), "model": best_name,
                                         "metric_name": "event_recall_ge2_hybrid",
                                         "metric_value": comp["hybrid"]["event_recall_ge2"],
                                         "greater_is_better": True, "data_hash": dh}, force=True)
    log_experiment("gas_edge", {"model": best_name, **best_params, "class_weight": CLASS_WEIGHT},
                   {m: {"recall_ge2": comp[m]["recall_ge2"], "event_recall_ge2": comp[m]["event_recall_ge2"],
                        "macro_f1": comp[m]["macro_f1"]} for m in comp}, SEED, time.perf_counter() - t0)
    write_report(res)
    print(f"Xong ({time.perf_counter() - t0:.0f}s). firmware/src/gas_model.py đã cập nhật — nạp lại bằng firmware/deploy.py.")


def write_report(res):
    c = res["test_comparison"]
    L = ["# Kết quả cảnh báo khí/khói tại edge", "",
         f"> Dữ liệu đo thật: `{res['data']}`, {res['n_samples']} mẫu 1 Hz.", "",
         f"Model chọn: **{res['chosen']}**", "",
         "## Rule / Model / Hybrid (tập test)", "",
         "| Chỉ số | Rule | Model | Hybrid |", "|---|---|---|---|"]
    rows = [("Macro-F1 (theo mẫu)", "macro_f1", "{:.3f}"), ("Recall cấp ≥2 (theo mẫu)", "recall_ge2", "{:.3f}"),
            ("Precision cấp ≥2 (theo mẫu)", "precision_ge2", "{:.3f}"),
            ("Recall cấp ≥2 (theo sự kiện)", "event_recall_ge2", "{:.3f}"),
            ("Báo động giả ≥1 trên sự kiện nhiễu", "nuisance_fp_rate_l1", "{:.2f}"),
            ("Báo động giả ≥2 trên sự kiện nhiễu", "nuisance_fp_rate_l2", "{:.2f}"),
            ("Độ trễ phát hiện cấp ≥2, trung vị (s)", "latency_median_s", "{}"),
            ("Độ trễ phát hiện cấp ≥2, P95 (s)", "latency_p95_s", "{}")]
    for label, k, fmt in rows:
        L.append(f"| {label} | " + " | ".join(fmt.format(c[m][k]) for m in ("rule", "model", "hybrid")) + " |")
    L += ["", "## Recall theo từng cấp (theo mẫu)", "", "| Cấp | Rule | Model | Hybrid |", "|---|---|---|---|"]
    for k in range(4):
        L.append(f"| {k} {LEVEL_NAMES[k]} | " + " | ".join(f"{c[m]['per_class'][k]['recall']:.3f}" for m in ("rule", "model", "hybrid")) + " |")
    L += ["", "## Ma trận nhầm lẫn — Hybrid (hàng: thật, cột: dự đoán)", "", "| | 0 | 1 | 2 | 3 |", "|---|---|---|---|---|"]
    for i, row in enumerate(c["hybrid"]["confusion_matrix"]):
        L.append(f"| {i} | " + " | ".join(map(str, row)) + " |")
    r = res["edge_resources"]
    p = res["micropython_parity"]
    L += ["", "## Tài nguyên edge & kiểm tra khớp MicroPython/scikit-learn", "",
          f"- {r['trees']} cây, {r['nodes']} nút, {r['leaves']} lá, ước tính **{r['flash_bytes_est'] / 1024:.1f} kB dữ liệu model** "
          f"(bytes trong gas_model.py)",
          f"- gas_model.py (float32) vs scikit-learn trên {p.get('checked')} vector: lệch lớp **{p.get('mismatches')}**, "
          f"lệch xác suất tối đa {p.get('max_proba_diff'):.2e}, {p.get('pc_us_per_inference', 0):.1f} µs/lần trên PC "
          f"(đo trên ESP32: `python -m mpremote run firmware/bench_device.py`)",
          "", "## Feature quan trọng (impurity, scikit-learn)", ""]
    L += [f"- {n}: {v:.3f}" for n, v in res["importance_split_gain"]]
    out = REPO_DIR / "docs" / "report" / "results_gas_edge.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(align_tables("\n".join(L) + "\n"), encoding="utf-8")


if __name__ == "__main__":
    main()
