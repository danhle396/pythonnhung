"""Huấn luyện mô hình cảnh báo khí/khói cho ESP32, so sánh Rule / Model / Hybrid, xuất sang C.

    python -m aiot_ml.train_gas_edge --data data/raw/gas_labeled.csv

Chỉ huấn luyện trên dữ liệu ĐO THẬT từ MQ-2, thu bằng tools/label_logger.py trong các buổi thí nghiệm có gán nhãn.
Chưa có dữ liệu -> không có model, firmware chạy rule (firmware/include/gas_model.h với GAS_MODEL_AVAILABLE = 0).
CSV cần các cột: t (giây), gas_ppm, rs_r0, temp, hum, lux, label (0..3), event_id, scenario, stream_seed.
Chia theo chuỗi (stream) để tập test là các buổi thí nghiệm khác hẳn tập train.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

from mlcore import ensemble, explain, metrics, tree
from mlcore.export_c import export_forest_c, export_test_vectors_c, forest_to_arrays, predict_c_like
from mlcore.serialize import dataset_hash, save_model

from .config import EXPERIMENTS_DIR, FIRMWARE_INCLUDE, MODELS_DIR, REPO_DIR, SEED
from .gas_edge import EDGE_FEATURES, LEVEL_NAMES, RuleConfig, extract_features_stream, run_levels_vectorized
from .tracking import ModelRegistry, log_experiment

CLASS_WEIGHT = {0: 1.0, 1: 1.5, 2: 4.0, 3: 6.0}  # phạt nặng khi bỏ sót cấp 2, 3 (ưu tiên Recall)


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
    """Đánh giá theo sự kiện: phát hiện (cấp dự đoán ≥ nhãn sự kiện ≥ 2), báo động giả, độ trễ."""
    out = {"events_ge2": 0, "detected_ge2": 0, "latency_s": [], "nuisance_events": 0, "nuisance_alarm_l1": 0,
           "nuisance_alarm_l2": 0, "clean_events": 0, "clean_alarm_l1": 0}
    d = df.assign(pred=pred)
    for (_, _), g in d.groupby(["stream_seed", "event_id"], sort=False):
        lab = int(g["label"].max())
        sc = g["scenario"].iloc[0]
        if lab >= 2:
            out["events_ge2"] += 1
            act = g[g["label"] >= 2]
            win = g.loc[act.index.min():act.index.max() + 10]  # cho phép trễ 10 s sau khi hết nhãn
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


def sample_metrics(y, pred):
    r = metrics.precision_recall_f1(y, pred, labels=[0, 1, 2, 3])
    ge2 = metrics.recall_binary((y >= 2).astype(int), (pred >= 2).astype(int))
    prec_ge2 = metrics.precision_binary((y >= 2).astype(int), (pred >= 2).astype(int))
    return {"macro_f1": r["macro"]["f1"], "recall_ge2": ge2, "precision_ge2": prec_ge2,
            "per_class": r["per_class"], "confusion_matrix": r["confusion_matrix"]}


def compile_parity(header_txt, tv_txt, prefix):
    """Biên dịch test harness bằng g++ trên PC, chạy và so khớp với Python."""
    cxx = shutil.which("g++") or shutil.which("gcc")
    if cxx is None:
        return {"compiled": False}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "gas_model.h").write_text(header_txt, encoding="utf-8")
        (td / "gas_model_testvec.h").write_text(tv_txt, encoding="utf-8")
        P = prefix.upper()
        (td / "main.cpp").write_text(f"""#include <cstdio>
#include <cmath>
#include <chrono>
#include "gas_model.h"
#include "gas_model_testvec.h"
int main() {{
  int bad = 0; float md = 0;
  auto t0 = std::chrono::high_resolution_clock::now();
  for (int r = 0; r < 20; ++r)
  for (int i = 0; i < {P}_N_TEST; ++i) {{
    float p[{P}_N_CLASSES]; int c = {prefix}_predict_proba({prefix}_test_x[i], p);
    if (r == 0) {{ if (c != {prefix}_test_class_idx[i]) ++bad;
      for (int k = 0; k < {P}_N_CLASSES; ++k) md = fmaxf(md, fabsf(p[k] - {prefix}_test_proba[i][k])); }}
  }}
  double us = std::chrono::duration<double, std::micro>(std::chrono::high_resolution_clock::now() - t0).count() / (20.0 * {P}_N_TEST);
  std::printf("%d %g %g\\n", bad, md, us);
}}""", encoding="utf-8")
        exe = td / "parity.exe"
        subprocess.run([cxx, "-O2", "-std=c++17", str(td / "main.cpp"), "-o", str(exe)], check=True, cwd=td)
        bad, md, us = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout.split()
    return {"compiled": True, "mismatches": int(bad), "max_proba_diff": float(md), "pc_us_per_inference": float(us)}


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

    # ------------------------------------------------ chọn model trên tập val
    cands = []
    for depth in (4, 5, 6):
        cands.append(("DecisionTree", {"max_depth": depth},
                      lambda d=depth: tree.DecisionTreeClassifier(max_depth=d, min_samples_leaf=20,
                                                                  class_weight=CLASS_WEIGHT, seed=SEED)))
    for nt, depth in ((5, 5), (10, 5), (10, 6)):
        cands.append(("RandomForest", {"n_estimators": nt, "max_depth": depth},
                      lambda nt=nt, d=depth: ensemble.RandomForestClassifier(
                          n_estimators=nt, max_depth=d, min_samples_leaf=20, max_features=0.6,
                          class_weight=CLASS_WEIGHT, seed=SEED)))
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
        # mục tiêu: ưu tiên recall ≥2 theo sự kiện, rồi giảm báo động giả, rồi macro-F1, phạt kích thước
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

    # ------------------------------------------------ so sánh Rule / Model / Hybrid trên test
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

    # ------------------------------------------------ xuất C + kiểm tra khớp
    P = "gas_model"
    header = export_forest_c(model, EDGE_FEATURES, prefix=P, model_ver=a.model_ver,
                             class_names=LEVEL_NAMES)
    rng = np.random.default_rng(SEED)
    pick = np.sort(np.r_[rng.choice(np.flatnonzero(yte == 0), min(250, int((yte == 0).sum())), replace=False),
                         *[np.flatnonzero(yte == k)[:: max(1, (yte == k).sum() // 80)][:80] for k in (1, 2, 3)]])
    cls_idx, proba = predict_c_like(model, Xte[pick])
    python_match = float((model.classes_[cls_idx] == model.predict(Xte[pick])).mean())
    tv = export_test_vectors_c(Xte[pick], cls_idx, proba, prefix=P, n_max=len(pick))
    FIRMWARE_INCLUDE.mkdir(parents=True, exist_ok=True)
    (FIRMWARE_INCLUDE / "gas_model.h").write_text(header, encoding="utf-8")
    tv_dir = REPO_DIR / "firmware" / "test" / "test_gas_model"
    tv_dir.mkdir(parents=True, exist_ok=True)
    (tv_dir / "gas_model_testvec.h").write_text(tv, encoding="utf-8")
    parity = compile_parity(header, tv, P)
    parity["python_float32_vs_float64_match"] = python_match
    A = forest_to_arrays(model)
    n_nodes, n_leaves = len(A["feature"]), int((A["feature"] < 0).sum())
    idx_bytes = 2 if n_nodes < 32767 else 4
    flash = n_nodes * (1 + 4 + 2 * idx_bytes) + n_leaves * 4 * 4 + len(A["roots"]) * 2
    print(f"  C parity: {parity} | ~{flash / 1024:.1f} kB flash, {n_nodes} nút")

    # ------------------------------------------------ lưu
    dh = dataset_hash(X[m_tr], y[m_tr])
    path = save_model({"model": model, "features": EDGE_FEATURES, "class_weight": CLASS_WEIGHT,
                       "rule_config": RuleConfig().__dict__}, MODELS_DIR / "gas_edge", model_ver=a.model_ver,
                      data_hash=dh, meta={"data": str(a.data)})
    imp = explain.split_gain_importance(model, EDGE_FEATURES)
    perm = explain.permutation_importance(lambda Z: model.predict(Z), Xte[:20000], yte[:20000],
                                          lambda yy, pp: metrics.recall_binary(yy >= 2, pp >= 2), n_repeats=3,
                                          greater_is_better=True, feature_names=EDGE_FEATURES)
    res = {"data": str(a.data), "n_samples": int(len(df)),
           "label_counts": np.bincount(y, minlength=4).tolist(), "selection": sel_log,
           "chosen": {"model": best_name, **best_params}, "test_raw_model": raw_model, "test_comparison": comp,
           "edge_resources": {"nodes": n_nodes, "leaves": n_leaves, "trees": len(A["roots"]),
                              "flash_bytes_est": flash, "ram_bytes_runtime": 4 * (10 + 4) + 4 * (30 + 60 + 60)},
           "c_parity": parity, "importance_split_gain": imp, "importance_permutation_recall_ge2": perm,
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
    print(f"Xong ({time.perf_counter() - t0:.0f}s). firmware/include/gas_model.h đã cập nhật.")


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
    p = res["c_parity"]
    L += ["", "## Tài nguyên edge & kiểm tra khớp C/Python", "",
          f"- {r['trees']} cây, {r['nodes']} nút, {r['leaves']} lá, ước tính **{r['flash_bytes_est'] / 1024:.1f} kB flash**, "
          f"RAM lúc chạy ≈ {r['ram_bytes_runtime']} B (bộ đệm cửa sổ + feature)",
          f"- C (g++) vs Python: lệch lớp **{p.get('mismatches')}**, lệch xác suất tối đa {p.get('max_proba_diff')}, "
          f"{p.get('pc_us_per_inference', 0):.3f} µs/lần trên PC (đo lại trên ESP32 bằng test_gas_model)",
          "", "## Feature quan trọng (split gain)", ""]
    L += [f"- {n}: {v:.3f}" for n, v in res["importance_split_gain"]]
    out = REPO_DIR / "docs" / "report" / "results_gas_edge.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
