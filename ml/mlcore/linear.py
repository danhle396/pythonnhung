"""Mô hình tuyến tính tự cài đặt.

Linear / Ridge Regression
    min_w  (1/2n)·||Xw + b - y||² + (λ/2n)·||w||²
    Nghiệm đóng (sau khi trừ trung bình để không phạt hệ số chặn):
        w = (XcᵀXc + λI)⁻¹ Xcᵀ yc ,   b = ȳ - x̄ᵀw
    Bản gradient descent:
        ∇w = (1/n)·Xᵀ(Xw + b - y) + (λ/n)·w ,   ∇b = (1/n)·Σ (Xw + b - y)

Logistic Regression (nhị phân: sigmoid, đa lớp: softmax), mini-batch GD + L2
    p = σ(z) = 1 / (1 + e^{-z}),   z = Xw + b
    L = -(1/Σs) Σ s_i [y_i ln p_i + (1-y_i) ln(1-p_i)] + (λ/2)·||w||²
    ∇w = (1/Σs)·Xᵀ(s ⊙ (p - y)) + λ·w ,   ∇b = (1/Σs)·Σ s_i (p_i - y_i)
    (với softmax: thay y bằng one-hot, p bằng softmax(z); công thức gradient giữ nguyên dạng)
"""
from __future__ import annotations

import numpy as np

from .optim import make_optimizer


class LinearRegression:
    def __init__(self, alpha=0.0, fit_intercept=True, solver="closed", lr=0.01, epochs=1000,
                 batch_size=None, seed=42, tol=1e-9):
        self.alpha = alpha
        self.fit_intercept = fit_intercept
        self.solver = solver
        self.lr, self.epochs, self.batch_size, self.seed, self.tol = lr, epochs, batch_size, seed, tol
        self.coef_ = None
        self.intercept_ = 0.0
        self.loss_history_ = []

    def fit(self, X, y, sample_weight=None):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float).ravel()
        if self.solver == "closed":
            self._fit_closed(X, y, sample_weight)
        else:
            self._fit_gd(X, y)
        return self

    def _fit_closed(self, X, y, sw):
        n, d = X.shape
        w = np.ones(n) if sw is None else np.asarray(sw, dtype=float)
        if self.fit_intercept:
            xm = np.average(X, axis=0, weights=w)
            ym = np.average(y, weights=w)
        else:
            xm, ym = np.zeros(d), 0.0
        Xc, yc = X - xm, y - ym
        Xw = Xc * w[:, None]
        A = Xc.T @ Xw + self.alpha * np.eye(d)
        bvec = Xw.T @ yc
        try:
            self.coef_ = np.linalg.solve(A, bvec)
        except np.linalg.LinAlgError:  # ma trận suy biến -> giả nghịch đảo
            self.coef_ = np.linalg.pinv(A) @ bvec
        self.intercept_ = float(ym - xm @ self.coef_)

    def _fit_gd(self, X, y):
        n, d = X.shape
        rng = np.random.default_rng(self.seed)
        params = {"w": np.zeros(d), "b": np.zeros(1)}
        opt = make_optimizer("sgd", lr=self.lr) if self.solver == "gd" else make_optimizer("adam", lr=self.lr)
        bs = self.batch_size or n
        prev = np.inf
        for ep in range(self.epochs):
            order = rng.permutation(n) if bs < n else np.arange(n)
            for s in range(0, n, bs):
                idx = order[s:s + bs]
                loss, g = self.loss_and_grad(params, X[idx], y[idx])
                if not self.fit_intercept:
                    g["b"][:] = 0
                opt.step(params, g)
            loss, _ = self.loss_and_grad(params, X, y)
            self.loss_history_.append(loss)
            if abs(prev - loss) < self.tol:
                break
            prev = loss
        self.coef_ = params["w"]
        self.intercept_ = float(params["b"][0])

    def loss_and_grad(self, params, X, y):
        n = len(y)
        r = X @ params["w"] + params["b"][0] - y
        loss = 0.5 * np.mean(r ** 2) + 0.5 * self.alpha / n * np.sum(params["w"] ** 2)
        return loss, {"w": X.T @ r / n + self.alpha / n * params["w"], "b": np.array([r.mean()])}

    def predict(self, X):
        return np.asarray(X, dtype=float) @ self.coef_ + self.intercept_

    def to_dict(self):
        return {"type": "LinearRegression", "alpha": self.alpha, "fit_intercept": self.fit_intercept,
                "coef": self.coef_.tolist(), "intercept": self.intercept_}

    @classmethod
    def from_dict(cls, d):
        m = cls(alpha=d["alpha"], fit_intercept=d["fit_intercept"])
        m.coef_ = np.asarray(d["coef"], dtype=float)
        m.intercept_ = float(d["intercept"])
        return m


class Ridge(LinearRegression):
    def __init__(self, alpha=1.0, **kw):
        super().__init__(alpha=alpha, **kw)

    def to_dict(self):
        d = super().to_dict()
        d["type"] = "Ridge"
        return d


def sigmoid(z):
    # dạng ổn định số học, tránh tràn exp
    out = np.empty_like(z, dtype=float)
    pos = z >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    ez = np.exp(z[~pos])
    out[~pos] = ez / (1.0 + ez)
    return out


def softmax(Z):
    Z = Z - Z.max(axis=1, keepdims=True)
    E = np.exp(Z)
    return E / E.sum(axis=1, keepdims=True)


class LogisticRegression:
    """Hồi quy logistic nhị phân/đa lớp, mini-batch GD, phạt L2, có trọng số lớp."""

    def __init__(self, alpha=1e-4, lr=0.05, epochs=200, batch_size=256, optimizer="adam",
                 class_weight=None, seed=42, tol=1e-7, verbose=False):
        self.alpha, self.lr, self.epochs, self.batch_size = alpha, lr, epochs, batch_size
        self.optimizer, self.class_weight, self.seed, self.tol, self.verbose = optimizer, class_weight, seed, tol, verbose
        self.classes_ = None
        self.W = None
        self.b = None
        self.loss_history_ = []

    # ---- tiện ích
    def _encode(self, y):
        idx = np.searchsorted(self.classes_, y)
        K = len(self.classes_)
        if K == 2:
            return idx.astype(float).reshape(-1, 1)
        Y = np.zeros((len(y), K))
        Y[np.arange(len(y)), idx] = 1.0
        return Y

    def _sample_weight(self, y):
        if self.class_weight is None:
            return np.ones(len(y))
        if self.class_weight == "balanced":
            cls, cnt = np.unique(y, return_counts=True)
            cw = {c: len(y) / (len(cls) * k) for c, k in zip(cls, cnt)}
        else:
            cw = self.class_weight
        return np.array([cw.get(v, 1.0) for v in y.tolist()])

    def loss_and_grad(self, params, X, Y, sw=None):
        W, b = params["W"], params["b"]
        n = X.shape[0]
        sw = np.ones(n) if sw is None else sw
        S = sw.sum()
        Z = X @ W + b
        if W.shape[1] == 1:
            P = sigmoid(Z)
            Pc = np.clip(P, 1e-15, 1 - 1e-15)
            ll = -(Y * np.log(Pc) + (1 - Y) * np.log(1 - Pc)).ravel()
        else:
            P = softmax(Z)
            ll = -np.sum(Y * np.log(np.clip(P, 1e-15, 1)), axis=1)
        loss = float(np.dot(sw, ll) / S + 0.5 * self.alpha * np.sum(W * W))
        R = (P - Y) * sw[:, None] / S
        return loss, {"W": X.T @ R + self.alpha * W, "b": R.sum(axis=0)}

    def fit(self, X, y):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y).ravel()
        self.classes_ = np.unique(y)
        K = len(self.classes_)
        out = 1 if K == 2 else K
        Y = self._encode(y)
        sw = self._sample_weight(y)
        rng = np.random.default_rng(self.seed)
        params = {"W": np.zeros((X.shape[1], out)), "b": np.zeros(out)}
        opt = make_optimizer(self.optimizer, lr=self.lr)
        n = len(y)
        bs = min(self.batch_size or n, n)
        prev = np.inf
        for ep in range(self.epochs):
            order = rng.permutation(n)
            for s in range(0, n, bs):
                idx = order[s:s + bs]
                _, g = self.loss_and_grad(params, X[idx], Y[idx], sw[idx])
                opt.step(params, g)
            loss, _ = self.loss_and_grad(params, X, Y, sw)
            self.loss_history_.append(loss)
            if self.verbose and ep % 20 == 0:
                print(f"epoch {ep} loss {loss:.5f}")
            if abs(prev - loss) < self.tol:
                break
            prev = loss
        self.W, self.b = params["W"], params["b"]
        return self

    def decision_function(self, X):
        return np.asarray(X, dtype=float) @ self.W + self.b

    def predict_proba(self, X):
        Z = self.decision_function(X)
        if self.W.shape[1] == 1:
            p = sigmoid(Z).ravel()
            return np.column_stack([1 - p, p])
        return softmax(Z)

    def predict(self, X):
        return self.classes_[np.argmax(self.predict_proba(X), axis=1)]

    def to_dict(self):
        return {"type": "LogisticRegression", "alpha": self.alpha, "classes": self.classes_.tolist(),
                "W": self.W.tolist(), "b": self.b.tolist()}

    @classmethod
    def from_dict(cls, d):
        m = cls(alpha=d["alpha"])
        m.classes_ = np.asarray(d["classes"])
        m.W = np.asarray(d["W"], dtype=float)
        m.b = np.asarray(d["b"], dtype=float)
        return m
