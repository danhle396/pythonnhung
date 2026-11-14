"""Xuất DecisionTreeClassifier / RandomForestClassifier của scikit-learn thành module MicroPython (gas_model.py).

Cây được đóng gói thành bytes (struct) để tiết kiệm RAM trên ESP32: mỗi nút (feature, trái, phải, ngưỡng float32),
mỗi lá là vector xác suất lớp. Suy luận giống predict_proba của scikit-learn: trung bình xác suất lá qua các cây.
"""
from __future__ import annotations

import datetime as _dt
import struct
import types

import numpy as np


def _trees_of(model):
    if hasattr(model, "estimators_"):
        return [e.tree_ for e in model.estimators_]
    if hasattr(model, "tree_"):
        return [model.tree_]
    raise TypeError("Chỉ hỗ trợ DecisionTreeClassifier / RandomForestClassifier của scikit-learn")


def forest_to_arrays(model):
    feat, thr, left, right, val, roots = [], [], [], [], [], []
    off = 0
    for t in _trees_of(model):
        roots.append(off)
        leaf = t.children_left < 0
        feat.extend(np.where(leaf, -1, t.feature).tolist())
        thr.extend(t.threshold.tolist())
        left.extend([(x + off) if x >= 0 else -1 for x in t.children_left.tolist()])
        right.extend([(x + off) if x >= 0 else -1 for x in t.children_right.tolist()])
        v = t.value[:, 0, :].astype(float)
        v = v / np.maximum(v.sum(axis=1, keepdims=True), 1e-12)
        val.extend(v.tolist())
        off += t.node_count
    return {"feature": np.array(feat), "threshold": np.array(thr), "left": np.array(left),
            "right": np.array(right), "value": np.array(val), "roots": np.array(roots)}


def predict_float32(model, X):
    """Suy luận giống hệt module MicroPython (float32) — dùng để kiểm tra khớp với scikit-learn."""
    A = forest_to_arrays(model)
    X = np.asarray(X, dtype=np.float32)
    thr = A["threshold"].astype(np.float32)
    val = A["value"].astype(np.float32)
    n = len(X)
    proba = np.zeros((n, val.shape[1]), dtype=np.float32)
    for r in A["roots"]:
        node = np.full(n, r, dtype=np.int64)
        while True:
            f = A["feature"][node]
            act = np.flatnonzero(f >= 0)
            if act.size == 0:
                break
            na = node[act]
            go = X[act, f[act]] <= thr[na]
            node[act] = np.where(go, A["left"][na], A["right"][na])
        proba += val[node]
    proba = proba / np.float32(len(A["roots"]))
    return np.argmax(proba, axis=1), proba


def _f32(v):
    v = float(np.float32(v))
    return 3.4e38 if v == np.inf else (-3.4e38 if v == -np.inf else v)


def export_forest_micropython(model, feature_names, model_ver="v1", class_names=None):
    A = forest_to_arrays(model)
    n_nodes = len(A["feature"])
    K = A["value"].shape[1]
    labels = np.asarray(model.classes_).tolist()
    names = class_names or [str(c) for c in labels]
    is_leaf = A["feature"] < 0
    leaf_index = np.full(n_nodes, -1)
    leaf_index[is_leaf] = np.arange(is_leaf.sum())
    left = np.where(is_leaf, leaf_index, A["left"])
    idx_fmt = "h" if n_nodes < 32767 else "i"
    node_fmt = "<" + idx_fmt * 3 + "f"
    nodes = b"".join(struct.pack(node_fmt, int(f), int(l), int(r), _f32(t))
                     for f, l, r, t in zip(A["feature"], left, A["right"], A["threshold"]))
    leaves = b"".join(struct.pack("<" + "f" * K, *[_f32(v) for v in row]) for row in A["value"][is_leaf])
    lines = [
        "# Tự động sinh bởi ml/src/export_micropython.py (từ scikit-learn) — KHÔNG sửa tay.",
        f"# Thời điểm: {_dt.datetime.now().isoformat(timespec='seconds')}",
        f"# Model: {type(model).__name__}, {len(A['roots'])} cây, {n_nodes} nút, {int(is_leaf.sum())} lá, "
        f"{len(nodes) + len(leaves)} byte dữ liệu",
        "# Thứ tự feature (phải khớp với firmware/src/edge_ai.py):",
        *[f"#   x[{i}] = {n}" for i, n in enumerate(feature_names)],
        "import struct",
        "",
        "AVAILABLE = True",
        f"VERSION = {model_ver!r}",
        f"N_FEATURES = {len(feature_names)}",
        f"N_CLASSES = {K}",
        f"CLASS_LABEL = {tuple(int(c) for c in labels)!r}",
        f"CLASS_NAME = {tuple(names)!r}",
        f"ROOTS = {tuple(int(r) for r in A['roots'])!r}",
        f"_FMT = {node_fmt!r}",
        f"_NODE = {struct.calcsize(node_fmt)}",
        f"_NODES = {nodes!r}",
        f"_LEAF = {leaves!r}",
        "",
        "",
        "def predict_proba(x):",
        "    acc = [0.0] * N_CLASSES",
        "    unpack = struct.unpack_from",
        "    for i in ROOTS:",
        "        while True:",
        "            f, l, r, t = unpack(_FMT, _NODES, i * _NODE)",
        "            if f < 0:",
        "                break",
        "            i = l if x[f] <= t else r",
        "        v = unpack('<' + 'f' * N_CLASSES, _LEAF, l * 4 * N_CLASSES)",
        "        for k in range(N_CLASSES):",
        "            acc[k] += v[k]",
        "    n = len(ROOTS)",
        "    best = 0",
        "    for k in range(N_CLASSES):",
        "        acc[k] /= n",
        "        if acc[k] > acc[best]:",
        "            best = k",
        "    return best, acc",
        "",
    ]
    return "\n".join(lines)


def load_module_from_source(src: str, name="gas_model"):
    mod = types.ModuleType(name)
    exec(compile(src, f"<{name}>", "exec"), mod.__dict__)
    return mod


def to_float32_list(x):
    return [float(v) for v in np.asarray(x, dtype=np.float32)]
