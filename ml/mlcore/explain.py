"""Giải thích mô hình (thay cho SHAP).

Split-gain importance: tổng mức giảm loss (gain) của mọi nút chia theo feature j, chuẩn hoá về tổng 1.
Permutation importance (Breiman 2001): xáo trộn cột j trên tập kiểm tra, đo mức tăng sai số
    PI_j = (1/R) Σ_r [ err(y, f(X^{(j,r)})) − err(y, f(X)) ]
Feature quan trọng ⇒ phá vỡ nó làm sai số tăng nhiều.
"""
from __future__ import annotations

import numpy as np


def split_gain_importance(model, feature_names=None):
    imp = np.asarray(model.feature_importances_)
    names = feature_names or [f"f{i}" for i in range(len(imp))]
    order = np.argsort(-imp)
    return [(names[i], float(imp[i])) for i in order]


def permutation_importance(predict_fn, X, y, metric, n_repeats=5, seed=42, greater_is_better=False,
                           feature_names=None):
    """predict_fn: X -> ŷ ; metric(y, ŷ) -> số. Trả về list (tên, mean, std) sắp giảm dần."""
    X = np.asarray(X, dtype=float)
    rng = np.random.default_rng(seed)
    base = metric(y, predict_fn(X))
    names = feature_names or [f"f{i}" for i in range(X.shape[1])]
    res = []
    for j in range(X.shape[1]):
        deltas = []
        saved = X[:, j].copy()
        for _ in range(n_repeats):
            X[:, j] = saved[rng.permutation(len(saved))]
            s = metric(y, predict_fn(X))
            deltas.append(base - s if greater_is_better else s - base)
        X[:, j] = saved
        res.append((names[j], float(np.mean(deltas)), float(np.std(deltas))))
    return sorted(res, key=lambda t: -t[1])
