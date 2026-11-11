"""Xuất model cây/rừng/logistic sang header C cho ESP32 — tự viết, thay cho emlearn/micromlgen.

Định dạng: mọi cây được nối vào chung các mảng `const` (nằm trong flash, không tốn RAM):
    feature[i]   : chỉ số feature (−1 nếu là lá)
    threshold[i] : ngưỡng float (đi trái nếu x[feature] <= threshold)
    left[i], right[i] : chỉ số nút con (toàn cục)
    leaf_value[i][K]  : phân phối lớp tại lá
    roots[t]     : nút gốc của cây t
Suy luận chỉ là vòng lặp duyệt mảng, không cần thư viện, không cấp phát động.
Tuỳ chọn lượng tử hoá: ngưỡng và xác suất lưu dạng số nguyên (int32 / uint16) để giảm flash.
"""
from __future__ import annotations

import datetime as _dt

import numpy as np

from .linear import LogisticRegression
from .tree import DecisionTreeClassifier


def _trees_of(model):
    if isinstance(model, DecisionTreeClassifier):
        return [model.tree_]
    if hasattr(model, "trees_"):
        return list(model.trees_)
    raise TypeError("Chỉ hỗ trợ DecisionTreeClassifier / RandomForestClassifier")


def _fmt_float(v):
    v = float(np.float32(v))
    if np.isinf(v):
        return "3.4e38f" if v > 0 else "-3.4e38f"
    s = repr(v)
    if "e" not in s and "." not in s:
        s += ".0"
    return s + "f"


def _rows(vals, per_line=12, fmt=str, indent="    "):
    vals = list(vals)
    lines = [indent + ", ".join(fmt(v) for v in vals[i:i + per_line]) for i in range(0, len(vals), per_line)]
    return ",\n".join(lines)


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


def predict_c_like(model, X):
    """Mô phỏng chính xác phép tính của code C (float32, cộng dồn theo thứ tự cây) để so khớp 100%."""
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


def export_forest_c(model, feature_names, prefix="gas_model", model_ver="v1", class_labels=None,
                    class_names=None, guard=None):
    """Sinh nội dung header C cho DecisionTreeClassifier / RandomForestClassifier."""
    A = forest_to_arrays(model)
    n_nodes = len(A["feature"])
    K = A["value"].shape[1]
    F = len(feature_names)
    labels = class_labels if class_labels is not None else np.asarray(model.classes_).tolist()
    names = class_names or [str(c) for c in labels]
    idx_t = "int16_t" if n_nodes < 32767 else "int32_t"
    P = prefix.upper()
    guard = guard or f"{P}_H"
    is_leaf = A["feature"] < 0
    # chỉ lưu giá trị cho lá: ánh xạ nút -> chỉ số lá để tiết kiệm flash
    leaf_index = np.full(n_nodes, -1)
    leaf_index[is_leaf] = np.arange(is_leaf.sum())
    # nút lá: left = chỉ số lá (dùng lại mảng left, vì lá không có con)
    left = np.where(is_leaf, leaf_index, A["left"])
    leaf_vals = A["value"][is_leaf]
    out = []
    out.append(f"// Tự động sinh bởi ml/mlcore/export_c.py — KHÔNG sửa tay.")
    out.append(f"// Thời điểm: {_dt.datetime.now().isoformat(timespec='seconds')}")
    out.append(f"// Model: {type(model).__name__}, {len(A['roots'])} cây, {n_nodes} nút, {len(leaf_vals)} lá")
    out.append(f"#ifndef {guard}\n#define {guard}\n\n#include <stdint.h>\n")
    out.append(f"#define {P}_AVAILABLE 1")
    out.append(f'#define {P}_VERSION "{model_ver}"')
    out.append(f"#define {P}_N_FEATURES {F}")
    out.append(f"#define {P}_N_CLASSES {K}")
    out.append(f"#define {P}_N_TREES {len(A['roots'])}")
    out.append(f"#define {P}_N_NODES {n_nodes}\n")
    out.append("// Thứ tự feature (phải khớp với edge_ai.cpp):")
    for i, nme in enumerate(feature_names):
        out.append(f"//   x[{i}] = {nme}")
    out.append("")
    out.append(f"static const int8_t {prefix}_class_label[{K}] = {{{', '.join(str(int(c)) for c in labels)}}};")
    out.append(f"static const char* const {prefix}_class_name[{K}] = {{{', '.join(chr(34) + n + chr(34) for n in names)}}};")
    out.append(f"static const uint16_t {prefix}_roots[{len(A['roots'])}] = {{{', '.join(map(str, A['roots']))}}};")
    out.append(f"static const int8_t {prefix}_feature[{n_nodes}] = {{\n{_rows(A['feature'].tolist(), 24)}\n}};")
    out.append(f"static const float {prefix}_threshold[{n_nodes}] = {{\n{_rows(A['threshold'], 6, _fmt_float)}\n}};")
    out.append(f"// với nút lá: left = chỉ số dòng trong {prefix}_leaf")
    out.append(f"static const {idx_t} {prefix}_left[{n_nodes}] = {{\n{_rows(left.tolist(), 16)}\n}};")
    out.append(f"static const {idx_t} {prefix}_right[{n_nodes}] = {{\n{_rows(A['right'].tolist(), 16)}\n}};")
    leaf_lines = ",\n".join("    {" + ", ".join(_fmt_float(v) for v in row) + "}" for row in leaf_vals)
    out.append(f"static const float {prefix}_leaf[{len(leaf_vals)}][{K}] = {{\n{leaf_lines}\n}};\n")
    out.append(f"""/* Suy luận: trả về chỉ số lớp (0..K-1), ghi xác suất vào proba[K]. */
static inline int {prefix}_predict_proba(const float* x, float* proba) {{
    for (int k = 0; k < {P}_N_CLASSES; ++k) proba[k] = 0.0f;
    for (int t = 0; t < {P}_N_TREES; ++t) {{
        int n = {prefix}_roots[t];
        while ({prefix}_feature[n] >= 0) {{
            n = (x[{prefix}_feature[n]] <= {prefix}_threshold[n]) ? {prefix}_left[n] : {prefix}_right[n];
        }}
        const float* v = {prefix}_leaf[{prefix}_left[n]];
        for (int k = 0; k < {P}_N_CLASSES; ++k) proba[k] += v[k];
    }}
    int best = 0;
    for (int k = 0; k < {P}_N_CLASSES; ++k) {{
        proba[k] = proba[k] / (float){P}_N_TREES;
        if (proba[k] > proba[best]) best = k;
    }}
    return best;
}}

/* Trả về nhãn lớp gốc (ví dụ cấp cảnh báo 0..3). */
static inline int {prefix}_predict(const float* x) {{
    float p[{P}_N_CLASSES];
    return {prefix}_class_label[{prefix}_predict_proba(x, p)];
}}
""")
    out.append(f"#endif  // {guard}\n")
    return "\n".join(out)


def export_logistic_c(model: LogisticRegression, feature_names, prefix="lr_model", scaler=None):
    """Header C cho logistic nhị phân/đa lớp, gộp sẵn StandardScaler nếu có."""
    W = np.asarray(model.W, dtype=float)
    b = np.asarray(model.b, dtype=float)
    if scaler is not None:  # z = ((x − μ)/σ)·W + b = x·(W/σ) + (b − (μ/σ)·W)
        W2 = W / scaler.scale_[:, None]
        b = b - (scaler.mean_ / scaler.scale_) @ W
        W = W2
    F, K = W.shape
    P = prefix.upper()
    w_lines = ",\n".join("    {" + ", ".join(_fmt_float(v) for v in row) + "}" for row in W)
    return f"""// Tự động sinh bởi ml/mlcore/export_c.py
#ifndef {P}_H
#define {P}_H
#include <math.h>
#define {P}_N_FEATURES {F}
#define {P}_N_OUT {K}
// feature: {', '.join(feature_names)}
static const float {prefix}_W[{F}][{K}] = {{
{w_lines}
}};
static const float {prefix}_b[{K}] = {{{', '.join(_fmt_float(v) for v in b)}}};
static inline void {prefix}_logits(const float* x, float* z) {{
    for (int k = 0; k < {K}; ++k) {{
        z[k] = {prefix}_b[k];
        for (int j = 0; j < {F}; ++j) z[k] += x[j] * {prefix}_W[j][k];
    }}
}}
static inline float {prefix}_predict_binary(const float* x) {{
    float z[{K}];
    {prefix}_logits(x, z);
    return 1.0f / (1.0f + expf(-z[0]));
}}
#endif
"""


def export_test_vectors_c(X, expected_class, expected_proba, prefix="gas_model", n_max=500):
    """Header chứa vector kiểm thử dùng chung cho test trên PC (g++) và trên ESP32."""
    X = np.asarray(X, dtype=np.float32)[:n_max]
    yc = np.asarray(expected_class)[:n_max]
    pr = np.asarray(expected_proba, dtype=np.float32)[:n_max]
    n, F = X.shape
    K = pr.shape[1]
    xs = ",\n".join("    {" + ", ".join(_fmt_float(v) for v in row) + "}" for row in X)
    ps = ",\n".join("    {" + ", ".join(_fmt_float(v) for v in row) + "}" for row in pr)
    return f"""// Vector kiểm thử sinh tự động — so khớp predict() C với Python
#ifndef {prefix.upper()}_TESTVEC_H
#define {prefix.upper()}_TESTVEC_H
#define {prefix.upper()}_N_TEST {n}
static const float {prefix}_test_x[{n}][{F}] = {{
{xs}
}};
static const int {prefix}_test_class_idx[{n}] = {{{', '.join(str(int(v)) for v in yc)}}};
static const float {prefix}_test_proba[{n}][{K}] = {{
{ps}
}};
#endif
"""
