"""Phát hiện bất thường tự cài đặt: Isolation Forest, CUSUM, z-score theo giờ trong ngày.

Isolation Forest (Liu, Ting, Zhou 2008)
    Mỗi iTree dựng trên ψ mẫu con: chọn ngẫu nhiên một feature q và ngưỡng p ~ U(min_q, max_q),
    chia tiếp cho tới khi nút còn 1 mẫu hoặc đạt độ cao giới hạn ⌈log₂ ψ⌉.
    Điểm bất thường dễ bị "cô lập" ⇒ đường đi ngắn.
        h(x) = độ sâu lá + c(|lá|)
        c(n) = 2·H(n−1) − 2(n−1)/n,  H(i) ≈ ln(i) + 0.5772156649  (c(2) = 1, c(1) = 0)
        s(x, ψ) = 2^{ −E[h(x)] / c(ψ) }   ∈ (0, 1];  s → 1: bất thường,  s ≲ 0.5: bình thường.

CUSUM hai phía (Page 1954) trên giá trị chuẩn hoá z_t = (x_t − μ₀)/σ₀:
    S⁺_t = max(0, S⁺_{t−1} + z_t − k),   S⁻_t = max(0, S⁻_{t−1} − z_t − k)
    Báo động khi S⁺_t > h hoặc S⁻_t > h  (k ≈ 0.5: phát hiện dịch chuyển ~1σ, h ≈ 4–5).
"""
from __future__ import annotations

import math

import numpy as np

EULER = 0.5772156649015329


def c_factor(n):
    """Độ dài đường đi trung bình của tìm kiếm thất bại trong BST n nút."""
    n = np.asarray(n, dtype=float)
    out = np.zeros_like(n)
    out = np.where(n == 2, 1.0, out)
    m = n > 2
    out = np.where(m, 2.0 * (np.log(np.where(m, n - 1, 1)) + EULER) - 2.0 * (n - 1) / np.where(m, n, 1), out)
    return out


class IsolationForest:
    def __init__(self, n_estimators=100, max_samples=256, contamination=0.01, seed=42):
        self.n_estimators, self.max_samples, self.contamination, self.seed = n_estimators, max_samples, contamination, seed
        self.trees_ = []
        self.psi_ = None
        self.threshold_ = None

    def _build(self, X, rng, limit):
        feat, thr, left, right, size, depth = [], [], [], [], [], []

        def node(idx, d):
            nid = len(feat)
            feat.append(-1); thr.append(0.0); left.append(-1); right.append(-1)
            size.append(len(idx)); depth.append(d)
            if d >= limit or len(idx) <= 1:
                return nid
            sub = X[idx]
            lo, hi = sub.min(axis=0), sub.max(axis=0)
            cand = np.flatnonzero(hi > lo)
            if cand.size == 0:
                return nid
            q = int(rng.choice(cand))
            p = float(rng.uniform(lo[q], hi[q]))
            m = sub[:, q] < p
            feat[nid], thr[nid] = q, p
            left[nid] = node(idx[m], d + 1)
            right[nid] = node(idx[~m], d + 1)
            return nid

        node(np.arange(len(X)), 0)
        feat = np.array(feat); size = np.array(size); depth = np.array(depth, dtype=float)
        path = depth + np.where(feat < 0, c_factor(size), 0.0)  # chỉ dùng ở lá
        return {"feature": feat, "threshold": np.array(thr), "left": np.array(left),
                "right": np.array(right), "path": path}

    def fit(self, X):
        X = np.asarray(X, dtype=float)
        rng = np.random.default_rng(self.seed)
        n = len(X)
        self.psi_ = min(self.max_samples, n)
        limit = int(math.ceil(math.log2(max(self.psi_, 2))))
        self.trees_ = [self._build(X[rng.choice(n, self.psi_, replace=False)], rng, limit)
                       for _ in range(self.n_estimators)]
        s = self.score_samples(X)
        self.threshold_ = float(np.quantile(s, 1.0 - self.contamination))
        return self

    def _path_length(self, t, X):
        node = np.zeros(len(X), dtype=int)
        while True:
            f = t["feature"][node]
            act = np.flatnonzero(f >= 0)
            if act.size == 0:
                return t["path"][node]
            na = node[act]
            go = X[act, f[act]] < t["threshold"][na]
            node[act] = np.where(go, t["left"][na], t["right"][na])

    def score_samples(self, X):
        """Điểm bất thường s(x) ∈ (0, 1]; càng cao càng bất thường."""
        X = np.asarray(X, dtype=float)
        Eh = np.mean([self._path_length(t, X) for t in self.trees_], axis=0)
        return 2.0 ** (-Eh / float(c_factor(self.psi_)))

    def predict(self, X):
        """1 = bất thường, 0 = bình thường (theo ngưỡng contamination trên tập fit)."""
        return (self.score_samples(X) > self.threshold_).astype(int)

    def to_dict(self):
        return {"type": "IsolationForest", "psi": self.psi_, "threshold": self.threshold_,
                "contamination": self.contamination,
                "trees": [{k: v.tolist() for k, v in t.items()} for t in self.trees_]}

    @classmethod
    def from_dict(cls, d):
        m = cls(n_estimators=len(d["trees"]), contamination=d["contamination"])
        m.psi_, m.threshold_ = d["psi"], d["threshold"]
        m.trees_ = [{k: np.asarray(v) for k, v in t.items()} for t in d["trees"]]
        return m


class CUSUM:
    """CUSUM hai phía. fit() trên đoạn tham chiếu (ví dụ R0 khi mới hiệu chuẩn)."""

    def __init__(self, k=0.5, h=5.0, reset_on_alarm=True):
        self.k, self.h, self.reset_on_alarm = k, h, reset_on_alarm
        self.mu_, self.sigma_ = None, None
        self.s_pos, self.s_neg = 0.0, 0.0

    def fit(self, ref):
        ref = np.asarray(ref, dtype=float)
        self.mu_ = float(np.nanmean(ref))
        self.sigma_ = float(max(np.nanstd(ref), 1e-9))
        self.s_pos = self.s_neg = 0.0
        return self

    def update(self, x):
        """Cập nhật 1 mẫu. Trả về +1 (trôi lên), −1 (trôi xuống) hoặc 0."""
        z = (x - self.mu_) / self.sigma_
        self.s_pos = max(0.0, self.s_pos + z - self.k)
        self.s_neg = max(0.0, self.s_neg - z - self.k)
        alarm = 1 if self.s_pos > self.h else (-1 if self.s_neg > self.h else 0)
        if alarm and self.reset_on_alarm:
            self.s_pos = self.s_neg = 0.0
        return alarm

    def detect(self, x):
        """Chạy trên cả chuỗi. Trả về dict gồm S⁺, S⁻ và danh sách (chỉ số, hướng) báo động."""
        x = np.asarray(x, dtype=float)
        sp, sn, alarms = np.zeros(len(x)), np.zeros(len(x)), []
        for i, v in enumerate(x):
            if np.isnan(v):
                sp[i], sn[i] = self.s_pos, self.s_neg
                continue
            a = self.update(v)
            sp[i], sn[i] = self.s_pos, self.s_neg
            if a:
                alarms.append((i, a))
        return {"s_pos": sp, "s_neg": sn, "alarms": alarms}

    def to_dict(self):
        return {"type": "CUSUM", "k": self.k, "h": self.h, "mu": self.mu_, "sigma": self.sigma_}

    @classmethod
    def from_dict(cls, d):
        m = cls(d["k"], d["h"])
        m.mu_, m.sigma_ = d["mu"], d["sigma"]
        return m


class HourlyZScore:
    """Baseline đơn giản: z = (x − μ_giờ) / σ_giờ, với μ/σ ước lượng riêng cho từng giờ trong ngày."""

    def __init__(self, z_thr=3.0):
        self.z_thr = z_thr
        self.mu_ = None
        self.sd_ = None

    def fit(self, x, hours):
        x = np.asarray(x, dtype=float)
        hours = np.asarray(hours, dtype=int)
        self.mu_ = np.array([np.nanmean(x[hours == hh]) if np.any(hours == hh) else np.nanmean(x) for hh in range(24)])
        self.sd_ = np.array([np.nanstd(x[hours == hh]) if np.sum(hours == hh) > 1 else np.nanstd(x) for hh in range(24)])
        self.sd_ = np.maximum(self.sd_, 1e-9)
        return self

    def score(self, x, hours):
        hours = np.asarray(hours, dtype=int)
        return (np.asarray(x, dtype=float) - self.mu_[hours]) / self.sd_[hours]

    def predict(self, x, hours):
        return (np.abs(self.score(x, hours)) > self.z_thr).astype(int)

    def to_dict(self):
        return {"type": "HourlyZScore", "z_thr": self.z_thr, "mu": self.mu_.tolist(), "sd": self.sd_.tolist()}

    @classmethod
    def from_dict(cls, d):
        m = cls(d["z_thr"])
        m.mu_, m.sd_ = np.asarray(d["mu"]), np.asarray(d["sd"])
        return m
