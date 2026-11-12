"""Xuất model cây/rừng sang module MicroPython cho ESP32 — tự viết, thay cho emlearn/micromlgen.

Mọi cây được nối vào chung một mảng nút, đóng gói nhị phân (`bytes`) để tiết kiệm RAM trên ESP32:
    mỗi nút = struct "<hhhf" (int16 feature, int16 left, int16 right, float32 threshold) — 10 byte;
    feature = −1 nếu là lá, khi đó `left` là chỉ số dòng trong bảng xác suất lá;
    bảng lá = float32 × N_CLASSES mỗi lá; ROOTS = nút gốc của từng cây.
Suy luận chỉ là vòng lặp duyệt mảng bằng struct.unpack_from, không cần thư viện, không cấp phát lớn.
Ngưỡng lưu float32 vì MicroPython trên ESP32 dùng số thực 32 bit; `predict_float32` mô phỏng đúng phép tính đó
để kiểm tra khớp 100 % trên PC.
"""
from __future__ import annotations

import datetime as _dt
import struct

import numpy as np

from .tree import DecisionTreeClassifier


def _trees_of(model):
    if isinstance(model, DecisionTreeClassifier):
        return [model.tree_]
    if hasattr(model, "trees_"):
        return list(model.trees_)
    raise TypeError("Chỉ hỗ trợ DecisionTreeClassifier / RandomForestClassifier")


def forest_to_arrays(model):
    trees = _trees_of(model)
    feat, thr, left, right, val, roots = [], [], [], [], [], []
    off = 0
    for t in trees:
        roots.append(off)
        feat.extend(t.feature.tolist())
        thr.extend(t.threshold.tolist())
        left.extend([(x + off) if x >= 0 else -1 for x in t.left.tolist()])
        right.extend([(x + off) if x >= 0 else -1 for x in t.right.tolist()])
        val.extend(np.atleast_2d(t.value).tolist())
        off += t.n_nodes
    return {"feature": np.array(feat), "threshold": np.array(thr), "left": np.array(left),
            "right": np.array(right), "value": np.array(val), "roots": np.array(roots)}


def predict_float32(model, X):
    """Mô phỏng phép tính số thực 32 bit trên ESP32 (cộng dồn theo thứ tự cây) để so khớp."""
    A = forest_to_arrays(model)
    X = np.asarray(X, dtype=np.float32)
    thr = A["threshold"].astype(np.float32)
    val = A["value"].astype(np.float32)
    n, K = len(X), val.shape[1]
    proba = np.zeros((n, K), dtype=np.float32)
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


def export_forest_micropython(model, feature_names, model_ver="v1", class_labels=None, class_names=None):
    """Sinh mã nguồn module `gas_model.py` (cùng giao diện với bản giữ chỗ trong firmware/src/gas_model.py)."""
    A = forest_to_arrays(model)
    n_nodes = len(A["feature"])
    K = A["value"].shape[1]
    labels = class_labels if class_labels is not None else np.asarray(model.classes_).tolist()
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
    node_size = struct.calcsize(node_fmt)
    lines = [
        "# Tự động sinh bởi ml/mlcore/export_micropython.py — KHÔNG sửa tay.",
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
        f"_NODE = {node_size}",
        f"_NODES = {nodes!r}",
        f"_LEAF = {leaves!r}",
        "",
        "",
        "def predict_proba(x):",
        '    """x: 10 feature. Trả về (chỉ số lớp, danh sách xác suất trung bình các cây)."""',
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
    """Nạp mã nguồn module sinh ra vào CPython (dùng để kiểm tra khớp trên PC)."""
    import types
    mod = types.ModuleType(name)
    exec(compile(src, f"<{name}>", "exec"), mod.__dict__)
    return mod


def to_float32_list(x):
    """Làm tròn vector feature về float32 như trên ESP32."""
    return [float(v) for v in np.asarray(x, dtype=np.float32)]
