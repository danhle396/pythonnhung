"""CART (Classification And Regression Trees) tự cài đặt, huấn luyện trên histogram.

Histogram binning
    Mỗi feature được rời rạc hoá thành ≤ B bin theo phân vị: bin(x) = min{b : x ≤ e_b}.
    Ngưỡng ứng viên chỉ là các mép bin e_b ⇒ thay vì sắp xếp n giá trị, mỗi nút chỉ cần một
    histogram O(n·F) (np.bincount) rồi quét O(F·B) để tìm điểm cắt tốt nhất.
    Mẹo trừ histogram: hist(con lớn) = hist(cha) − hist(con nhỏ) ⇒ chỉ tính hist cho con nhỏ hơn.

Cây hồi quy dựa trên gradient/hessian (dùng chung cho CART-MSE và Gradient Boosting)
    Với nút có G = Σ g_i, H = Σ h_i:
        Gain = G_L²/(H_L + λ) + G_R²/(H_R + λ) − G²/(H + λ)
        Giá trị lá (bước Newton) w* = −G / (H + λ)
    CART-MSE là trường hợp riêng g_i = −y_i, h_i = 1, λ = 0:
        Gain = S_L²/n_L + S_R²/n_R − S²/n  = mức giảm tổng bình phương sai số (SSE),
        w* = mean(y) trong lá.

Cây phân loại (Gini / Entropy, có trọng số lớp)
    W_k = tổng trọng số mẫu lớp k trong nút, W = Σ_k W_k, p_k = W_k / W
    Gini(t) = 1 − Σ_k p_k²,  Entropy(t) = −Σ_k p_k log₂ p_k
    Gain = W·I(t) − W_L·I(t_L) − W_R·I(t_R)
    Trọng số lớp lớn ⇒ bỏ sót lớp đó bị "phạt" nặng hơn ⇒ tăng Recall cho lớp đó.

Cây được lưu dưới dạng mảng node (feature, threshold, left, right, value) — chính là định dạng
xuất sang C cho ESP32 (xem export_c.py). Nút lá có feature = −1.
"""
from __future__ import annotations

import numpy as np


# ======================================================================= binning
class Binner:
    """Rời rạc hoá theo phân vị. Mép bin là trung điểm giữa hai giá trị dữ liệu liên tiếp,
    nhờ vậy ngưỡng không bao giờ trùng đúng một giá trị mẫu (an toàn khi ép kiểu float32 trên MCU)."""

    def __init__(self, max_bins=64):
        if not 2 <= max_bins <= 65535:
            raise ValueError("max_bins phải trong [2, 65535]")
        self.max_bins = max_bins
        self.edges_ = None

    def fit(self, X):
        X = np.asarray(X, dtype=float)
        self.edges_ = []
        for j in range(X.shape[1]):
            col = X[:, j]
            col = col[~np.isnan(col)]
            uniq = np.unique(col)
            if len(uniq) <= 1:
                edges = np.array([], dtype=float)
            elif len(uniq) <= self.max_bins:
                edges = (uniq[:-1] + uniq[1:]) / 2.0
            else:
                qs = np.quantile(col, np.linspace(0, 1, self.max_bins + 1)[1:-1])
                pos = np.unique(np.clip(np.searchsorted(uniq, qs, side="right") - 1, 0, len(uniq) - 2))
                edges = (uniq[pos] + uniq[pos + 1]) / 2.0
            self.edges_.append(edges)
        return self

    @property
    def n_bins_(self):
        return np.array([len(e) + 1 for e in self.edges_])

    def transform(self, X):
        X = np.asarray(X, dtype=float)
        dtype = np.uint8 if self.max_bins <= 256 else np.uint16
        out = np.empty(X.shape, dtype=dtype)
        for j, e in enumerate(self.edges_):
            out[:, j] = np.searchsorted(e, X[:, j], side="left")  # NaN -> bin cuối
        return out

    def fit_transform(self, X):
        return self.fit(X).transform(X)


# ======================================================================= cấu trúc cây
class Tree:
    """Cây dạng mảng. value: (n_nodes,) cho hồi quy hoặc (n_nodes, K) cho phân loại."""

    def __init__(self, feature, threshold, left, right, value, gain, n_samples):
        self.feature = np.asarray(feature, dtype=np.int32)
        self.threshold = np.asarray(threshold, dtype=float)
        self.left = np.asarray(left, dtype=np.int32)
        self.right = np.asarray(right, dtype=np.int32)
        self.value = np.asarray(value, dtype=float)
        self.gain = np.asarray(gain, dtype=float)
        self.n_samples = np.asarray(n_samples, dtype=np.int64)

    @property
    def n_nodes(self):
        return len(self.feature)

    @property
    def max_depth(self):
        depth = np.zeros(self.n_nodes, dtype=int)
        for i in range(self.n_nodes):  # nút con luôn có chỉ số lớn hơn nút cha
            if self.feature[i] >= 0:
                depth[self.left[i]] = depth[self.right[i]] = depth[i] + 1
        return int(depth.max())

    def apply(self, X, threshold_dtype=None):
        """Trả về chỉ số nút lá của từng mẫu (duyệt vector hoá theo từng tầng)."""
        X = np.asarray(X)
        thr = self.threshold if threshold_dtype is None else self.threshold.astype(threshold_dtype)
        node = np.zeros(X.shape[0], dtype=np.int32)
        while True:
            feat = self.feature[node]
            act = np.flatnonzero(feat >= 0)
            if act.size == 0:
                return node
            na = node[act]
            go_left = X[act, feat[act]] <= thr[na]
            node[act] = np.where(go_left, self.left[na], self.right[na])

    def predict_value(self, X, threshold_dtype=None):
        return self.value[self.apply(X, threshold_dtype)]

    def feature_gain(self, n_features):
        imp = np.zeros(n_features)
        m = self.feature >= 0
        np.add.at(imp, self.feature[m], self.gain[m])
        return imp

    def to_dict(self):
        return {"feature": self.feature.tolist(), "threshold": self.threshold.tolist(),
                "left": self.left.tolist(), "right": self.right.tolist(), "value": self.value.tolist(),
                "gain": self.gain.tolist(), "n_samples": self.n_samples.tolist()}

    @classmethod
    def from_dict(cls, d):
        return cls(d["feature"], d["threshold"], d["left"], d["right"], d["value"], d["gain"], d["n_samples"])


# ======================================================================= bộ dựng cây
def _feature_mask(rng, F, max_features):
    if max_features is None or max_features >= F:
        return None
    m = np.zeros(F, dtype=bool)
    m[rng.choice(F, size=max_features, replace=False)] = True
    return m


def _resolve_max_features(max_features, F):
    if max_features is None:
        return None
    if max_features == "sqrt":
        return max(1, int(np.sqrt(F)))
    if max_features == "log2":
        return max(1, int(np.log2(F)))
    if isinstance(max_features, float):
        return max(1, int(max_features * F))
    return int(max_features)


def build_gradient_tree(Xb, edges, g, h, rows=None, max_depth=6, min_samples_leaf=1,
                        min_child_weight=1e-3, reg_lambda=0.0, min_gain=1e-12, max_features=None,
                        rng=None):
    """Dựng cây hồi quy từ gradient g và hessian h (xem docstring module).

    Xb    : (n, F) chỉ số bin (từ Binner.transform)
    edges : list mép bin của từng feature
    rows  : chỉ số các hàng dùng để dựng cây (subsample / bootstrap). None = tất cả.
    """
    n, F = Xb.shape
    B = int(max(len(e) for e in edges)) + 1
    n_edges = np.array([len(e) for e in edges])
    bin_ok = np.arange(B - 1)[None, :] < n_edges[:, None]  # (F, B-1): b là mép thật
    offs = (np.arange(F) * B).astype(np.int64)
    rng = rng or np.random.default_rng(0)
    mf = _resolve_max_features(max_features, F)
    rows = np.arange(n) if rows is None else np.asarray(rows)
    g = np.asarray(g, dtype=float)
    h = np.asarray(h, dtype=float)

    def hist(idx):
        flat = (Xb[idx].astype(np.int64) + offs).ravel()
        G = np.bincount(flat, weights=np.repeat(g[idx], F), minlength=F * B).reshape(F, B)
        H = np.bincount(flat, weights=np.repeat(h[idx], F), minlength=F * B).reshape(F, B)
        C = np.bincount(flat, minlength=F * B).reshape(F, B).astype(float)
        return G, H, C

    feature, threshold, left, right, value, gains, nsamp = [], [], [], [], [], [], []

    def new_node(Gt, Ht, cnt):
        feature.append(-1); threshold.append(0.0); left.append(-1); right.append(-1)
        value.append(-Gt / (Ht + reg_lambda) if Ht + reg_lambda > 0 else 0.0)
        gains.append(0.0); nsamp.append(int(cnt))
        return len(feature) - 1

    root_hist = hist(rows)
    Gt, Ht = root_hist[0][0].sum(), root_hist[1][0].sum()
    root = new_node(Gt, Ht, len(rows))
    stack = [(root, rows, 0, root_hist)]
    while stack:
        nid, idx, depth, (G, H, C) = stack.pop()
        Gt, Ht, Ct = G[0].sum(), H[0].sum(), C[0].sum()
        if depth >= max_depth or Ct < 2 * min_samples_leaf:
            continue
        GL = np.cumsum(G, axis=1)[:, :-1]
        HL = np.cumsum(H, axis=1)[:, :-1]
        CL = np.cumsum(C, axis=1)[:, :-1]
        GR, HR, CR = Gt - GL, Ht - HL, Ct - CL
        valid = (bin_ok & (CL >= min_samples_leaf) & (CR >= min_samples_leaf)
                 & (HL >= min_child_weight) & (HR >= min_child_weight))
        fm = _feature_mask(rng, F, mf)
        if fm is not None:
            valid &= fm[:, None]
        if not valid.any():
            continue
        with np.errstate(divide="ignore", invalid="ignore"):
            gain = GL ** 2 / (HL + reg_lambda) + GR ** 2 / (HR + reg_lambda) - Gt ** 2 / (Ht + reg_lambda)
        gain = np.where(valid, gain, -np.inf)
        f, b = np.unravel_index(int(np.argmax(gain)), gain.shape)
        best = gain[f, b]
        if not np.isfinite(best) or best <= min_gain:
            continue
        go_left = Xb[idx, f] <= b
        il, ir = idx[go_left], idx[~go_left]
        # mẹo trừ histogram
        if len(il) <= len(ir):
            hl = hist(il)
            hr = (G - hl[0], H - hl[1], C - hl[2])
        else:
            hr = hist(ir)
            hl = (G - hr[0], H - hr[1], C - hr[2])
        feature[nid], threshold[nid], gains[nid] = int(f), float(edges[f][b]), float(best)
        lid = new_node(GL[f, b], HL[f, b], len(il))
        rid = new_node(GR[f, b], HR[f, b], len(ir))
        left[nid], right[nid] = lid, rid
        stack.append((rid, ir, depth + 1, hr))
        stack.append((lid, il, depth + 1, hl))
    return Tree(feature, threshold, left, right, value, gains, nsamp)


def build_class_tree(Xb, edges, y_idx, K, sample_weight=None, rows=None, max_depth=6,
                     min_samples_leaf=1, criterion="gini", min_gain=1e-12, max_features=None, rng=None):
    """Dựng cây phân loại. y_idx: nhãn đã mã hoá 0..K-1. value của lá = phân phối lớp (có trọng số)."""
    n, F = Xb.shape
    B = int(max(len(e) for e in edges)) + 1
    n_edges = np.array([len(e) for e in edges])
    bin_ok = np.arange(B - 1)[None, :] < n_edges[:, None]
    offs = (np.arange(F) * B).astype(np.int64)
    rng = rng or np.random.default_rng(0)
    mf = _resolve_max_features(max_features, F)
    rows = np.arange(n) if rows is None else np.asarray(rows)
    w = np.ones(n) if sample_weight is None else np.asarray(sample_weight, dtype=float)
    y_idx = np.asarray(y_idx, dtype=np.int64)

    def hist(idx):
        base = Xb[idx].astype(np.int64) + offs  # (m, F)
        flat = (base * K + y_idx[idx][:, None]).ravel()
        W = np.bincount(flat, weights=np.repeat(w[idx], F), minlength=F * B * K).reshape(F, B, K)
        C = np.bincount(base.ravel(), minlength=F * B).reshape(F, B).astype(float)
        return W, C

    def weighted_impurity(Wk):
        """Trả về W·I (tổng trọng số × độ vẩn đục) theo trục cuối."""
        Wsum = Wk.sum(axis=-1)
        with np.errstate(divide="ignore", invalid="ignore"):
            if criterion == "gini":
                out = Wsum - np.where(Wsum > 0, (Wk ** 2).sum(axis=-1) / Wsum, 0.0)
            else:  # entropy (log2)
                t = np.where(Wk > 0, Wk * np.log2(np.where(Wk > 0, Wk, 1.0)), 0.0).sum(axis=-1)
                out = np.where(Wsum > 0, Wsum * np.log2(np.where(Wsum > 0, Wsum, 1.0)) - t, 0.0)
        return out

    feature, threshold, left, right, value, gains, nsamp = [], [], [], [], [], [], []

    def new_node(Wk, cnt):
        tot = Wk.sum()
        feature.append(-1); threshold.append(0.0); left.append(-1); right.append(-1)
        value.append((Wk / tot) if tot > 0 else np.full(K, 1.0 / K))
        gains.append(0.0); nsamp.append(int(cnt))
        return len(feature) - 1

    root_hist = hist(rows)
    root = new_node(root_hist[0][0].sum(axis=0), len(rows))
    stack = [(root, rows, 0, root_hist)]
    while stack:
        nid, idx, depth, (W, C) = stack.pop()
        Wt = W[0].sum(axis=0)
        Ct = C[0].sum()
        if depth >= max_depth or Ct < 2 * min_samples_leaf or np.count_nonzero(Wt) <= 1:
            continue
        WL = np.cumsum(W, axis=1)[:, :-1, :]
        CL = np.cumsum(C, axis=1)[:, :-1]
        WR = Wt - WL
        CR = Ct - CL
        valid = bin_ok & (CL >= min_samples_leaf) & (CR >= min_samples_leaf)
        fm = _feature_mask(rng, F, mf)
        if fm is not None:
            valid &= fm[:, None]
        if not valid.any():
            continue
        gain = weighted_impurity(Wt) - weighted_impurity(WL) - weighted_impurity(WR)
        gain = np.where(valid, gain, -np.inf)
        f, b = np.unravel_index(int(np.argmax(gain)), gain.shape)
        best = gain[f, b]
        if not np.isfinite(best) or best <= min_gain:
            continue
        go_left = Xb[idx, f] <= b
        il, ir = idx[go_left], idx[~go_left]
        if len(il) <= len(ir):
            hl = hist(il)
            hr = (W - hl[0], C - hl[1])
        else:
            hr = hist(ir)
            hl = (W - hr[0], C - hr[1])
        feature[nid], threshold[nid], gains[nid] = int(f), float(edges[f][b]), float(best)
        lid = new_node(WL[f, b], len(il))
        rid = new_node(WR[f, b], len(ir))
        left[nid], right[nid] = lid, rid
        stack.append((rid, ir, depth + 1, hr))
        stack.append((lid, il, depth + 1, hl))
    return Tree(feature, threshold, left, right, value, gains, nsamp)


def class_weight_vector(y_idx, K, class_weight):
    """Trả về trọng số từng mẫu. class_weight: None | 'balanced' | {lớp_idx: w}."""
    if class_weight is None:
        return np.ones(len(y_idx))
    if class_weight == "balanced":
        cnt = np.bincount(y_idx, minlength=K).astype(float)
        cw = np.where(cnt > 0, len(y_idx) / (K * np.maximum(cnt, 1)), 0.0)
    else:
        cw = np.ones(K)
        for k, v in class_weight.items():
            cw[int(k)] = v
    return cw[y_idx]


# ======================================================================= estimator
class DecisionTreeRegressor:
    def __init__(self, max_depth=6, min_samples_leaf=5, max_bins=64, max_features=None, seed=42):
        self.max_depth, self.min_samples_leaf, self.max_bins = max_depth, min_samples_leaf, max_bins
        self.max_features, self.seed = max_features, seed
        self.tree_ = None
        self.n_features_ = None

    def fit(self, X, y, sample_weight=None, binner=None, Xb=None):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float).ravel()
        binner = binner or Binner(self.max_bins).fit(X)
        Xb = binner.transform(X) if Xb is None else Xb
        w = np.ones(len(y)) if sample_weight is None else np.asarray(sample_weight, dtype=float)
        rows = np.flatnonzero(w > 0)
        self.tree_ = build_gradient_tree(Xb, binner.edges_, -y * w, w, rows=rows, max_depth=self.max_depth,
                                         min_samples_leaf=self.min_samples_leaf, min_child_weight=0.0,
                                         reg_lambda=0.0, max_features=self.max_features,
                                         rng=np.random.default_rng(self.seed))
        self.n_features_ = X.shape[1]
        return self

    def predict(self, X):
        return self.tree_.predict_value(np.asarray(X, dtype=float))

    @property
    def feature_importances_(self):
        imp = self.tree_.feature_gain(self.n_features_)
        return imp / imp.sum() if imp.sum() > 0 else imp

    def to_dict(self):
        return {"type": "DecisionTreeRegressor", "max_depth": self.max_depth,
                "n_features": self.n_features_, "tree": self.tree_.to_dict()}

    @classmethod
    def from_dict(cls, d):
        m = cls(max_depth=d["max_depth"])
        m.tree_ = Tree.from_dict(d["tree"])
        m.n_features_ = d["n_features"]
        return m


class DecisionTreeClassifier:
    def __init__(self, max_depth=6, min_samples_leaf=1, criterion="gini", class_weight=None,
                 max_bins=64, max_features=None, seed=42):
        self.max_depth, self.min_samples_leaf, self.criterion = max_depth, min_samples_leaf, criterion
        self.class_weight, self.max_bins, self.max_features, self.seed = class_weight, max_bins, max_features, seed
        self.tree_ = None
        self.classes_ = None
        self.n_features_ = None

    def fit(self, X, y, sample_weight=None, binner=None, Xb=None):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y).ravel()
        self.classes_ = np.unique(y)
        K = len(self.classes_)
        y_idx = np.searchsorted(self.classes_, y)
        binner = binner or Binner(self.max_bins).fit(X)
        Xb = binner.transform(X) if Xb is None else Xb
        cw = self.class_weight
        if isinstance(cw, dict):  # khoá là nhãn gốc -> đổi sang chỉ số lớp
            cw = {int(np.searchsorted(self.classes_, k)): v for k, v in cw.items() if k in set(self.classes_.tolist())}
        w = class_weight_vector(y_idx, K, cw)
        if sample_weight is not None:
            w = w * np.asarray(sample_weight, dtype=float)
        rows = np.flatnonzero(w > 0)
        self.tree_ = build_class_tree(Xb, binner.edges_, y_idx, K, sample_weight=w, rows=rows,
                                      max_depth=self.max_depth, min_samples_leaf=self.min_samples_leaf,
                                      criterion=self.criterion, max_features=self.max_features,
                                      rng=np.random.default_rng(self.seed))
        self.n_features_ = X.shape[1]
        return self

    def predict_proba(self, X, threshold_dtype=None):
        return self.tree_.predict_value(np.asarray(X), threshold_dtype)

    def predict(self, X, threshold_dtype=None):
        return self.classes_[np.argmax(self.predict_proba(X, threshold_dtype), axis=1)]

    @property
    def feature_importances_(self):
        imp = self.tree_.feature_gain(self.n_features_)
        return imp / imp.sum() if imp.sum() > 0 else imp

    def to_dict(self):
        return {"type": "DecisionTreeClassifier", "max_depth": self.max_depth, "criterion": self.criterion,
                "classes": self.classes_.tolist(), "n_features": self.n_features_, "tree": self.tree_.to_dict()}

    @classmethod
    def from_dict(cls, d):
        m = cls(max_depth=d["max_depth"], criterion=d["criterion"])
        m.classes_ = np.asarray(d["classes"])
        m.n_features_ = d["n_features"]
        m.tree_ = Tree.from_dict(d["tree"])
        return m
