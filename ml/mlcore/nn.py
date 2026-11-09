"""Mạng nơ-ron viết tay bằng NumPy (phần nâng cao): MLP và GRU với lan truyền ngược thủ công.

Dense: a = x·W + b ;  ∂L/∂W = xᵀ·δ,  ∂L/∂b = Σδ,  ∂L/∂x = δ·Wᵀ

GRU (Cho et al. 2014), với σ = sigmoid, ⊙ = nhân từng phần tử:
    z_t = σ(x_t W_z + h_{t−1} U_z + b_z)                 (cổng cập nhật)
    r_t = σ(x_t W_r + h_{t−1} U_r + b_r)                 (cổng reset)
    ĥ_t = tanh(x_t W_h + (r_t ⊙ h_{t−1}) U_h + b_h)      (trạng thái ứng viên)
    h_t = (1 − z_t) ⊙ h_{t−1} + z_t ⊙ ĥ_t
    ŷ   = h_T W_y + b_y
BPTT (đi ngược t = T..1), với δh là ∂L/∂h_t:
    δĥ = δh ⊙ z ;  δz = δh ⊙ (ĥ − h_{t−1}) ;  δh_{t−1} = δh ⊙ (1 − z)
    δa_h = δĥ ⊙ (1 − ĥ²) ;  δ(r⊙h) = δa_h U_hᵀ ;  δr = δ(r⊙h) ⊙ h_{t−1} ;  δh_{t−1} += δ(r⊙h) ⊙ r
    δa_z = δz ⊙ z(1 − z) ;  δa_r = δr ⊙ r(1 − r)
    δh_{t−1} += δa_z U_zᵀ + δa_r U_rᵀ
    ∂W_* += x_tᵀ δa_* ;  ∂U_z += h_{t−1}ᵀ δa_z ; ∂U_r += h_{t−1}ᵀ δa_r ; ∂U_h += (r ⊙ h_{t−1})ᵀ δa_h
Gradient clipping theo chuẩn L2 toàn cục để tránh bùng nổ gradient.
"""
from __future__ import annotations

import numpy as np

from .linear import sigmoid, softmax
from .optim import clip_grad_norm, make_optimizer


def _act(name, z):
    if name == "relu":
        return np.maximum(z, 0.0)
    if name == "tanh":
        return np.tanh(z)
    if name == "sigmoid":
        return sigmoid(z)
    if name == "linear":
        return z
    raise ValueError(name)


def _act_grad(name, z, a):
    if name == "relu":
        return (z > 0).astype(float)
    if name == "tanh":
        return 1.0 - a * a
    if name == "sigmoid":
        return a * (1.0 - a)
    return np.ones_like(z)


class MLP:
    """Perceptron nhiều lớp. task='regression' (MSE) | 'binary' (sigmoid + log-loss) | 'multiclass' (softmax)."""

    def __init__(self, hidden=(32, 16), activation="relu", task="regression", lr=1e-3, epochs=200,
                 batch_size=128, l2=1e-5, optimizer="adam", clip=5.0, patience=20, seed=42, verbose=0):
        self.hidden, self.activation, self.task = tuple(hidden), activation, task
        self.lr, self.epochs, self.batch_size, self.l2 = lr, epochs, batch_size, l2
        self.optimizer, self.clip, self.patience, self.seed, self.verbose = optimizer, clip, patience, seed, verbose
        self.params = None
        self.classes_ = None
        self.history_ = {"train": [], "val": []}

    def init_params(self, d_in, d_out):
        rng = np.random.default_rng(self.seed)
        sizes = [d_in, *self.hidden, d_out]
        p = {}
        for i in range(len(sizes) - 1):
            scale = np.sqrt(2.0 / sizes[i]) if self.activation == "relu" else np.sqrt(1.0 / sizes[i])
            p[f"W{i}"] = rng.normal(0, scale, (sizes[i], sizes[i + 1]))
            p[f"b{i}"] = np.zeros(sizes[i + 1])
        self.params = p
        return p

    @property
    def n_layers(self):
        return len(self.hidden) + 1

    def _forward(self, p, X):
        cache = [(None, X)]
        a = X
        L = self.n_layers
        for i in range(L):
            z = a @ p[f"W{i}"] + p[f"b{i}"]
            if i < L - 1:
                a = _act(self.activation, z)
            else:
                a = z if self.task == "regression" else (sigmoid(z) if self.task == "binary" else softmax(z))
            cache.append((z, a))
        return a, cache

    def loss_and_grad(self, p, X, Y):
        n = X.shape[0]
        out, cache = self._forward(p, X)
        if self.task == "regression":
            loss = 0.5 * np.mean(np.sum((out - Y) ** 2, axis=1))
        elif self.task == "binary":
            o = np.clip(out, 1e-15, 1 - 1e-15)
            loss = -np.mean(Y * np.log(o) + (1 - Y) * np.log(1 - o))
        else:
            loss = -np.mean(np.sum(Y * np.log(np.clip(out, 1e-15, 1)), axis=1))
        loss += 0.5 * self.l2 * sum(np.sum(p[f"W{i}"] ** 2) for i in range(self.n_layers))
        # với cả 3 trường hợp, ∂L/∂z_cuối = (out − Y)/n (sigmoid+BCE, softmax+CE, linear+MSE)
        delta = (out - Y) / n
        grads = {}
        for i in reversed(range(self.n_layers)):
            a_prev = cache[i][1]
            grads[f"W{i}"] = a_prev.T @ delta + self.l2 * p[f"W{i}"]
            grads[f"b{i}"] = delta.sum(axis=0)
            if i > 0:
                z_prev, a_p = cache[i]
                delta = (delta @ p[f"W{i}"].T) * _act_grad(self.activation, z_prev, a_p)
        return float(loss), grads

    def _prep_y(self, y):
        y = np.asarray(y)
        if self.task == "regression":
            return y.reshape(len(y), -1).astype(float)
        if self.task == "binary":
            return y.reshape(-1, 1).astype(float)
        self.classes_ = np.unique(y) if self.classes_ is None else self.classes_
        Y = np.zeros((len(y), len(self.classes_)))
        Y[np.arange(len(y)), np.searchsorted(self.classes_, y)] = 1.0
        return Y

    def fit(self, X, y, eval_set=None):
        X = np.asarray(X, dtype=float)
        if self.task == "multiclass":
            self.classes_ = np.unique(y)
        Y = self._prep_y(y)
        p = self.init_params(X.shape[1], Y.shape[1])
        opt = make_optimizer(self.optimizer, lr=self.lr)
        rng = np.random.default_rng(self.seed)
        if eval_set is not None:
            Xv, Yv = np.asarray(eval_set[0], dtype=float), self._prep_y(eval_set[1])
        best, best_p, wait = np.inf, None, 0
        n = len(X)
        for ep in range(self.epochs):
            order = rng.permutation(n)
            for s in range(0, n, self.batch_size):
                idx = order[s:s + self.batch_size]
                _, g = self.loss_and_grad(p, X[idx], Y[idx])
                clip_grad_norm(g, self.clip)
                opt.step(p, g)
            tl, _ = self.loss_and_grad(p, X, Y)
            self.history_["train"].append(tl)
            if eval_set is not None:
                vl, _ = self.loss_and_grad(p, Xv, Yv)
                self.history_["val"].append(vl)
                if vl < best - 1e-9:
                    best, best_p, wait = vl, {k: v.copy() for k, v in p.items()}, 0
                else:
                    wait += 1
                    if wait >= self.patience:
                        break
            if self.verbose and ep % self.verbose == 0:
                print(f"  epoch {ep} train={tl:.5f}" + (f" val={vl:.5f}" if eval_set is not None else ""))
        self.params = best_p if best_p is not None else p
        return self

    def predict_raw(self, X):
        return self._forward(self.params, np.asarray(X, dtype=float))[0]

    def predict(self, X):
        out = self.predict_raw(X)
        if self.task == "regression":
            return out.ravel() if out.shape[1] == 1 else out
        if self.task == "binary":
            return (out.ravel() >= 0.5).astype(int)
        return self.classes_[np.argmax(out, axis=1)]

    def predict_proba(self, X):
        out = self.predict_raw(X)
        if self.task == "binary":
            return np.column_stack([1 - out.ravel(), out.ravel()])
        return out

    def to_npz_dict(self):
        return {k: v for k, v in self.params.items()}

    def to_dict(self):
        return {"type": "MLP", "hidden": list(self.hidden), "activation": self.activation, "task": self.task,
                "classes": None if self.classes_ is None else np.asarray(self.classes_).tolist(),
                "params": {k: v.tolist() for k, v in self.params.items()}}

    @classmethod
    def from_dict(cls, d):
        m = cls(hidden=d["hidden"], activation=d["activation"], task=d["task"])
        m.classes_ = None if d["classes"] is None else np.asarray(d["classes"])
        m.params = {k: np.asarray(v, dtype=float) for k, v in d["params"].items()}
        return m


class GRURegressor:
    """GRU một tầng + Dense đầu ra, cho dự báo chuỗi: X (n, T, d) -> ŷ (n, d_out). Loss MSE."""

    def __init__(self, hidden=32, lr=3e-3, epochs=50, batch_size=128, clip=1.0, l2=0.0, patience=8,
                 seed=42, verbose=0):
        self.H, self.lr, self.epochs, self.batch_size = hidden, lr, epochs, batch_size
        self.clip, self.l2, self.patience, self.seed, self.verbose = clip, l2, patience, seed, verbose
        self.params = None
        self.history_ = {"train": [], "val": []}

    def init_params(self, d, d_out):
        rng = np.random.default_rng(self.seed)
        H = self.H
        p = {}
        for g in ("z", "r", "h"):
            p[f"W{g}"] = rng.normal(0, np.sqrt(1.0 / d), (d, H))
            # ma trận hồi quy khởi tạo trực giao giúp gradient ổn định qua nhiều bước
            q, _ = np.linalg.qr(rng.normal(size=(H, H)))
            p[f"U{g}"] = q
            p[f"b{g}"] = np.zeros(H)
        p["Wy"] = rng.normal(0, np.sqrt(1.0 / H), (H, d_out))
        p["by"] = np.zeros(d_out)
        self.params = p
        return p

    def _forward(self, p, X):
        n, T, _ = X.shape
        h = np.zeros((n, self.H))
        cache = []
        for t in range(T):
            x = X[:, t, :]
            z = sigmoid(x @ p["Wz"] + h @ p["Uz"] + p["bz"])
            r = sigmoid(x @ p["Wr"] + h @ p["Ur"] + p["br"])
            hh = np.tanh(x @ p["Wh"] + (r * h) @ p["Uh"] + p["bh"])
            h_new = (1 - z) * h + z * hh
            cache.append((x, h, z, r, hh))
            h = h_new
        return h @ p["Wy"] + p["by"], h, cache

    def loss_and_grad(self, p, X, Y):
        n = X.shape[0]
        out, hT, cache = self._forward(p, X)
        loss = 0.5 * np.mean(np.sum((out - Y) ** 2, axis=1)) + 0.5 * self.l2 * (
            np.sum(p["Wy"] ** 2) + sum(np.sum(p[f"W{g}"] ** 2) for g in "zrh"))
        dy = (out - Y) / n
        g = {k: np.zeros_like(v) for k, v in p.items()}
        g["Wy"] = hT.T @ dy + self.l2 * p["Wy"]
        g["by"] = dy.sum(axis=0)
        dh = dy @ p["Wy"].T
        for x, h_prev, z, r, hh in reversed(cache):
            dhh = dh * z
            dz = dh * (hh - h_prev)
            dh_prev = dh * (1 - z)
            dah = dhh * (1 - hh * hh)
            g["Wh"] += x.T @ dah
            g["Uh"] += (r * h_prev).T @ dah
            g["bh"] += dah.sum(axis=0)
            drh = dah @ p["Uh"].T
            dr = drh * h_prev
            dh_prev += drh * r
            daz = dz * z * (1 - z)
            dar = dr * r * (1 - r)
            g["Wz"] += x.T @ daz
            g["Uz"] += h_prev.T @ daz
            g["bz"] += daz.sum(axis=0)
            g["Wr"] += x.T @ dar
            g["Ur"] += h_prev.T @ dar
            g["br"] += dar.sum(axis=0)
            dh_prev += daz @ p["Uz"].T + dar @ p["Ur"].T
            dh = dh_prev
        for k in "zrh":
            g[f"W{k}"] += self.l2 * p[f"W{k}"]
        return float(loss), g

    def fit(self, X, y, eval_set=None):
        X = np.asarray(X, dtype=float)
        Y = np.asarray(y, dtype=float).reshape(len(X), -1)
        p = self.init_params(X.shape[2], Y.shape[1])
        opt = make_optimizer("adam", lr=self.lr)
        rng = np.random.default_rng(self.seed)
        if eval_set is not None:
            Xv = np.asarray(eval_set[0], dtype=float)
            Yv = np.asarray(eval_set[1], dtype=float).reshape(len(Xv), -1)
        best, best_p, wait = np.inf, None, 0
        n = len(X)
        for ep in range(self.epochs):
            order = rng.permutation(n)
            for s in range(0, n, self.batch_size):
                idx = order[s:s + self.batch_size]
                _, g = self.loss_and_grad(p, X[idx], Y[idx])
                clip_grad_norm(g, self.clip)
                opt.step(p, g)
            tl = self.loss_and_grad(p, X[:4096], Y[:4096])[0]
            self.history_["train"].append(tl)
            if eval_set is not None:
                vl = self.loss_and_grad(p, Xv, Yv)[0]
                self.history_["val"].append(vl)
                if vl < best - 1e-9:
                    best, best_p, wait = vl, {k: v.copy() for k, v in p.items()}, 0
                else:
                    wait += 1
                    if wait >= self.patience:
                        break
            if self.verbose:
                print(f"  epoch {ep} train={tl:.5f}" + (f" val={vl:.5f}" if eval_set is not None else ""))
        self.params = best_p if best_p is not None else p
        return self

    def predict(self, X):
        out = self._forward(self.params, np.asarray(X, dtype=float))[0]
        return out.ravel() if out.shape[1] == 1 else out

    def to_dict(self):
        return {"type": "GRURegressor", "hidden": self.H, "params": {k: v.tolist() for k, v in self.params.items()}}

    @classmethod
    def from_dict(cls, d):
        m = cls(hidden=d["hidden"])
        m.params = {k: np.asarray(v, dtype=float) for k, v in d["params"].items()}
        return m


def gradient_check(loss_and_grad, params, *args, eps=1e-6, n_checks=20, seed=0):
    """So sánh gradient giải tích với sai phân hữu hạn trung tâm:
        ∂L/∂θ ≈ (L(θ + ε) − L(θ − ε)) / 2ε
    Trả về sai số tương đối lớn nhất  |g_a − g_n| / max(|g_a| + |g_n|, 1e-12)."""
    rng = np.random.default_rng(seed)
    _, grads = loss_and_grad(params, *args)
    worst = 0.0
    for k, P in params.items():
        flat = P.reshape(-1)
        gflat = grads[k].reshape(-1)
        for i in rng.choice(flat.size, size=min(n_checks, flat.size), replace=False):
            old = flat[i]
            flat[i] = old + eps
            lp, _ = loss_and_grad(params, *args)
            flat[i] = old - eps
            lm, _ = loss_and_grad(params, *args)
            flat[i] = old
            num = (lp - lm) / (2 * eps)
            rel = abs(num - gflat[i]) / max(abs(num) + abs(gflat[i]), 1e-12)
            if abs(num) < 1e-10 and abs(gflat[i]) < 1e-10:
                rel = 0.0
            worst = max(worst, rel)
    return worst
