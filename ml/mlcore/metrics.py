"""Các độ đo đánh giá, tự cài đặt.

Hồi quy:
    MAE  = (1/n) Σ |y - ŷ|
    RMSE = sqrt((1/n) Σ (y - ŷ)^2)
    MAPE = (100/n) Σ |y - ŷ| / |y|            (bỏ qua y = 0)
    R²   = 1 - Σ (y - ŷ)^2 / Σ (y - ȳ)^2
Phân loại:
    Precision_k = TP_k / (TP_k + FP_k),  Recall_k = TP_k / (TP_k + FN_k)
    F1_k = 2·P·R / (P + R),  macro-F1 = trung bình F1_k
    ROC-AUC (Mann–Whitney): AUC = (Σ rank(dương) - n⁺(n⁺+1)/2) / (n⁺·n⁻)
    Brier = (1/n) Σ (p - y)^2,   LogLoss = -(1/n) Σ [y·ln p + (1-y)·ln(1-p)]
"""
from __future__ import annotations

import numpy as np


def _arr(a):
    return np.asarray(a, dtype=float).ravel()


# ----------------------------------------------------------------- hồi quy
def mae(y, yhat):
    y, yhat = _arr(y), _arr(yhat)
    return float(np.mean(np.abs(y - yhat)))


def rmse(y, yhat):
    y, yhat = _arr(y), _arr(yhat)
    return float(np.sqrt(np.mean((y - yhat) ** 2)))


def mse(y, yhat):
    y, yhat = _arr(y), _arr(yhat)
    return float(np.mean((y - yhat) ** 2))


def mape(y, yhat):
    y, yhat = _arr(y), _arr(yhat)
    m = np.abs(y) > 1e-12
    return float(100.0 * np.mean(np.abs(y[m] - yhat[m]) / np.abs(y[m])))


def r2(y, yhat):
    y, yhat = _arr(y), _arr(yhat)
    ss_res = np.sum((y - yhat) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    return float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0


# ------------------------------------------------------------- phân loại
def confusion_matrix(y, yhat, labels=None):
    """C[i, j] = số mẫu có nhãn thật labels[i] và dự đoán labels[j]."""
    y = np.asarray(y).ravel()
    yhat = np.asarray(yhat).ravel()
    if labels is None:
        labels = np.unique(np.concatenate([y, yhat]))
    labels = np.asarray(labels)
    k = len(labels)
    pos = {v: i for i, v in enumerate(labels.tolist())}
    yi = np.array([pos[v] for v in y.tolist()])
    pi = np.array([pos[v] for v in yhat.tolist()])
    cm = np.bincount(yi * k + pi, minlength=k * k).reshape(k, k)
    return cm


def accuracy(y, yhat):
    y, yhat = np.asarray(y).ravel(), np.asarray(yhat).ravel()
    return float(np.mean(y == yhat))


def precision_recall_f1(y, yhat, labels=None):
    """Trả về dict: per_class {label: {precision, recall, f1, support}} và macro."""
    y, yhat = np.asarray(y).ravel(), np.asarray(yhat).ravel()
    if labels is None:
        labels = np.unique(np.concatenate([y, yhat]))
    cm = confusion_matrix(y, yhat, labels)
    tp = np.diag(cm).astype(float)
    fp = cm.sum(axis=0) - tp
    fn = cm.sum(axis=1) - tp
    with np.errstate(divide="ignore", invalid="ignore"):
        prec = np.where(tp + fp > 0, tp / (tp + fp), 0.0)
        rec = np.where(tp + fn > 0, tp / (tp + fn), 0.0)
        f1 = np.where(prec + rec > 0, 2 * prec * rec / (prec + rec), 0.0)
    per = {}
    for i, lab in enumerate(np.asarray(labels).tolist()):
        per[lab] = {"precision": float(prec[i]), "recall": float(rec[i]), "f1": float(f1[i]),
                    "support": int(cm[i].sum())}
    return {"per_class": per,
            "macro": {"precision": float(prec.mean()), "recall": float(rec.mean()), "f1": float(f1.mean())},
            "confusion_matrix": cm.tolist(), "labels": np.asarray(labels).tolist()}


def f1_binary(y, yhat, pos_label=1):
    y, yhat = np.asarray(y).ravel(), np.asarray(yhat).ravel()
    tp = np.sum((y == pos_label) & (yhat == pos_label))
    fp = np.sum((y != pos_label) & (yhat == pos_label))
    fn = np.sum((y == pos_label) & (yhat != pos_label))
    if tp == 0:
        return 0.0
    p, r = tp / (tp + fp), tp / (tp + fn)
    return float(2 * p * r / (p + r))


def precision_binary(y, yhat, pos_label=1):
    y, yhat = np.asarray(y).ravel(), np.asarray(yhat).ravel()
    tp = np.sum((y == pos_label) & (yhat == pos_label))
    fp = np.sum((y != pos_label) & (yhat == pos_label))
    return float(tp / (tp + fp)) if tp + fp > 0 else 0.0


def recall_binary(y, yhat, pos_label=1):
    y, yhat = np.asarray(y).ravel(), np.asarray(yhat).ravel()
    tp = np.sum((y == pos_label) & (yhat == pos_label))
    fn = np.sum((y == pos_label) & (yhat != pos_label))
    return float(tp / (tp + fn)) if tp + fn > 0 else 0.0


def _rankdata(a):
    """Hạng trung bình (1-based), các giá trị bằng nhau nhận hạng trung bình."""
    a = np.asarray(a, dtype=float)
    order = np.argsort(a, kind="mergesort")
    sa = a[order]
    ranks = np.empty(len(a), dtype=float)
    # ranh giới các nhóm giá trị bằng nhau
    diff = np.concatenate([[True], sa[1:] != sa[:-1], [True]])
    starts = np.flatnonzero(diff)
    for s, e in zip(starts[:-1], starts[1:]):
        ranks[order[s:e]] = 0.5 * (s + 1 + e)  # trung bình của hạng s+1..e
    return ranks


def roc_auc(y, score):
    """ROC-AUC tính theo thống kê hạng Mann–Whitney (xử lý đúng giá trị trùng)."""
    y = np.asarray(y).ravel().astype(int)
    score = _arr(score)
    n_pos = int(y.sum())
    n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    r = _rankdata(score)
    return float((r[y == 1].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def roc_curve(y, score):
    """Trả về (fpr, tpr, thresholds) theo ngưỡng giảm dần."""
    y = np.asarray(y).ravel().astype(int)
    score = _arr(score)
    order = np.argsort(-score, kind="mergesort")
    s, yy = score[order], y[order]
    distinct = np.flatnonzero(np.diff(s)) if len(s) > 1 else np.array([], dtype=int)
    idx = np.concatenate([distinct, [len(s) - 1]])
    tps = np.cumsum(yy)[idx]
    fps = (idx + 1) - tps
    P, N = max(yy.sum(), 1), max(len(yy) - yy.sum(), 1)
    return (np.concatenate([[0.0], fps / N]), np.concatenate([[0.0], tps / P]),
            np.concatenate([[np.inf], s[idx]]))


def brier_score(y, p):
    y, p = _arr(y), _arr(p)
    return float(np.mean((p - y) ** 2))


def log_loss(y, p, eps=1e-15):
    y, p = _arr(y), np.clip(_arr(p), eps, 1 - eps)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def best_f1_threshold(y, p, grid=None):
    """Tìm ngưỡng xác suất cho F1 lớn nhất (chỉ dùng trên tập validation)."""
    if grid is None:
        grid = np.linspace(0.05, 0.95, 91)
    scores = [f1_binary(y, (np.asarray(p) >= t).astype(int)) for t in grid]
    i = int(np.argmax(scores))
    return float(grid[i]), float(scores[i])


def regression_report(y, yhat):
    return {"MAE": mae(y, yhat), "RMSE": rmse(y, yhat), "MAPE": mape(y, yhat), "R2": r2(y, yhat)}


def binary_report(y, p, threshold=0.5):
    yhat = (np.asarray(p) >= threshold).astype(int)
    return {"Accuracy": accuracy(y, yhat), "Precision": precision_binary(y, yhat),
            "Recall": recall_binary(y, yhat), "F1": f1_binary(y, yhat),
            "ROC_AUC": roc_auc(y, p), "Brier": brier_score(y, p), "LogLoss": log_loss(y, p),
            "threshold": float(threshold)}
