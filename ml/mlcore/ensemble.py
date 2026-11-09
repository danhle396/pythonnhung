"""Mô hình tổ hợp (ensemble) tự cài đặt: Random Forest và Gradient Boosting Trees.

Random Forest (Breiman 2001)
    Mỗi cây học trên một mẫu bootstrap (lấy n mẫu có hoàn lại) và tại mỗi nút chỉ xét một tập con
    ngẫu nhiên max_features feature. Dự đoán = trung bình xác suất (phân loại) / giá trị (hồi quy).
    Bootstrap được cài bằng trọng số: mẫu i xuất hiện c_i lần ⇒ trọng số c_i (không cần nhân bản dữ liệu).

Gradient Boosting (Friedman 2001, dạng Newton như XGBoost)
    F_0(x) = argmin_c Σ L(y_i, c)          (MSE: mean(y);  log-loss: log(p̄/(1−p̄)))
    Vòng m = 1..M:
        g_i = ∂L/∂F(x_i),  h_i = ∂²L/∂F(x_i)²
            MSE      : L = ½(y−F)²             ⇒ g = F − y,  h = 1
            log-loss : L = −y ln p − (1−y) ln(1−p),  p = σ(F) ⇒ g = p − y,  h = p(1−p)
        Dựng cây hồi quy trên (g, h) với tập con hàng ngẫu nhiên (subsample),
        giá trị lá w_j = −Σ_{i∈j} g_i / (Σ_{i∈j} h_i + λ)
        F_m(x) = F_{m−1}(x) + η · f_m(x)
    Early stopping: dừng khi loss trên tập validation không giảm sau `early_stopping_rounds` vòng,
    giữ lại số cây tốt nhất.
"""
from __future__ import annotations

import time

import numpy as np

from .linear import sigmoid
from .tree import (Binner, Tree, build_class_tree, build_gradient_tree, class_weight_vector)


# ======================================================================= Random Forest
class RandomForestClassifier:
    def __init__(self, n_estimators=10, max_depth=6, min_samples_leaf=1, max_features="sqrt",
                 criterion="gini", class_weight=None, bootstrap=True, max_bins=64, seed=42):
        self.n_estimators, self.max_depth, self.min_samples_leaf = n_estimators, max_depth, min_samples_leaf
        self.max_features, self.criterion, self.class_weight = max_features, criterion, class_weight
        self.bootstrap, self.max_bins, self.seed = bootstrap, max_bins, seed
        self.trees_ = []
        self.classes_ = None
        self.n_features_ = None

    def fit(self, X, y):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y).ravel()
        self.classes_ = np.unique(y)
        K = len(self.classes_)
        y_idx = np.searchsorted(self.classes_, y)
        binner = Binner(self.max_bins).fit(X)
        Xb = binner.transform(X)
        cw = self.class_weight
        if isinstance(cw, dict):
            cw = {int(np.searchsorted(self.classes_, k)): v for k, v in cw.items() if k in set(self.classes_.tolist())}
        base_w = class_weight_vector(y_idx, K, cw)
        rng = np.random.default_rng(self.seed)
        n = len(y)
        self.trees_ = []
        for _ in range(self.n_estimators):
            if self.bootstrap:
                counts = np.bincount(rng.integers(0, n, n), minlength=n).astype(float)
            else:
                counts = np.ones(n)
            w = base_w * counts
            self.trees_.append(build_class_tree(Xb, binner.edges_, y_idx, K, sample_weight=w,
                                                rows=np.flatnonzero(w > 0), max_depth=self.max_depth,
                                                min_samples_leaf=self.min_samples_leaf, criterion=self.criterion,
                                                max_features=self.max_features, rng=rng))
        self.n_features_ = X.shape[1]
        return self

    def predict_proba(self, X, threshold_dtype=None):
        X = np.asarray(X)
        return np.mean([t.predict_value(X, threshold_dtype) for t in self.trees_], axis=0)

    def predict(self, X, threshold_dtype=None):
        return self.classes_[np.argmax(self.predict_proba(X, threshold_dtype), axis=1)]

    @property
    def feature_importances_(self):
        imps = []
        for t in self.trees_:
            imp = t.feature_gain(self.n_features_)
            imps.append(imp / imp.sum() if imp.sum() > 0 else imp)
        return np.mean(imps, axis=0)

    def to_dict(self):
        return {"type": "RandomForestClassifier", "classes": self.classes_.tolist(),
                "n_features": self.n_features_, "max_depth": self.max_depth,
                "trees": [t.to_dict() for t in self.trees_]}

    @classmethod
    def from_dict(cls, d):
        m = cls(n_estimators=len(d["trees"]), max_depth=d["max_depth"])
        m.classes_ = np.asarray(d["classes"])
        m.n_features_ = d["n_features"]
        m.trees_ = [Tree.from_dict(t) for t in d["trees"]]
        return m


class RandomForestRegressor:
    def __init__(self, n_estimators=50, max_depth=8, min_samples_leaf=5, max_features=0.5,
                 bootstrap=True, max_bins=64, seed=42):
        self.n_estimators, self.max_depth, self.min_samples_leaf = n_estimators, max_depth, min_samples_leaf
        self.max_features, self.bootstrap, self.max_bins, self.seed = max_features, bootstrap, max_bins, seed
        self.trees_ = []
        self.n_features_ = None

    def fit(self, X, y):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float).ravel()
        binner = Binner(self.max_bins).fit(X)
        Xb = binner.transform(X)
        rng = np.random.default_rng(self.seed)
        n = len(y)
        self.trees_ = []
        for _ in range(self.n_estimators):
            w = np.bincount(rng.integers(0, n, n), minlength=n).astype(float) if self.bootstrap else np.ones(n)
            self.trees_.append(build_gradient_tree(Xb, binner.edges_, -y * w, w, rows=np.flatnonzero(w > 0),
                                                   max_depth=self.max_depth, min_samples_leaf=self.min_samples_leaf,
                                                   min_child_weight=0.0, reg_lambda=0.0,
                                                   max_features=self.max_features, rng=rng))
        self.n_features_ = X.shape[1]
        return self

    def predict(self, X):
        X = np.asarray(X, dtype=float)
        return np.mean([t.predict_value(X) for t in self.trees_], axis=0)

    @property
    def feature_importances_(self):
        imp = sum(t.feature_gain(self.n_features_) for t in self.trees_)
        return imp / imp.sum() if imp.sum() > 0 else imp

    def to_dict(self):
        return {"type": "RandomForestRegressor", "n_features": self.n_features_,
                "trees": [t.to_dict() for t in self.trees_]}

    @classmethod
    def from_dict(cls, d):
        m = cls(n_estimators=len(d["trees"]))
        m.n_features_ = d["n_features"]
        m.trees_ = [Tree.from_dict(t) for t in d["trees"]]
        return m


# ======================================================================= Gradient Boosting
class _GBDTBase:
    loss_name = None

    def __init__(self, n_estimators=500, learning_rate=0.05, max_depth=5, min_samples_leaf=20,
                 min_child_weight=1e-3, reg_lambda=1.0, subsample=0.8, colsample=1.0, max_bins=64,
                 early_stopping_rounds=30, seed=42, verbose=0):
        self.n_estimators, self.learning_rate, self.max_depth = n_estimators, learning_rate, max_depth
        self.min_samples_leaf, self.min_child_weight, self.reg_lambda = min_samples_leaf, min_child_weight, reg_lambda
        self.subsample, self.colsample, self.max_bins = subsample, colsample, max_bins
        self.early_stopping_rounds, self.seed, self.verbose = early_stopping_rounds, seed, verbose
        self.trees_ = []
        self.init_ = 0.0
        self.n_features_ = None
        self.train_loss_, self.val_loss_ = [], []
        self.best_iteration_ = None
        self.fit_time_s_ = None

    # các lớp con cài đặt
    def _init_score(self, y, w):
        raise NotImplementedError

    def _grad_hess(self, y, F, w):
        raise NotImplementedError

    def _loss(self, y, F, w):
        raise NotImplementedError

    def fit(self, X, y, sample_weight=None, eval_set=None):
        t0 = time.perf_counter()
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float).ravel()
        n, F_ = X.shape
        w = np.ones(n) if sample_weight is None else np.asarray(sample_weight, dtype=float)
        binner = Binner(self.max_bins).fit(X)
        Xb = binner.transform(X)
        rng = np.random.default_rng(self.seed)
        self.init_ = self._init_score(y, w)
        Fx = np.full(n, self.init_)
        if eval_set is not None:
            Xv = np.asarray(eval_set[0], dtype=float)
            yv = np.asarray(eval_set[1], dtype=float).ravel()
            Fv = np.full(len(yv), self.init_)
        self.trees_, self.train_loss_, self.val_loss_ = [], [], []
        best_loss, best_it, since_best = np.inf, 0, 0
        mf = None if self.colsample >= 1.0 else self.colsample
        for m in range(self.n_estimators):
            g, h = self._grad_hess(y, Fx, w)
            rows = np.flatnonzero(rng.random(n) < self.subsample) if self.subsample < 1.0 else np.arange(n)
            tree = build_gradient_tree(Xb, binner.edges_, g, h, rows=rows, max_depth=self.max_depth,
                                       min_samples_leaf=self.min_samples_leaf,
                                       min_child_weight=self.min_child_weight, reg_lambda=self.reg_lambda,
                                       max_features=mf, rng=rng)
            tree.value *= self.learning_rate  # shrinkage được "nướng" vào lá
            self.trees_.append(tree)
            Fx += tree.predict_value(X)
            self.train_loss_.append(self._loss(y, Fx, w))
            if eval_set is not None:
                Fv += tree.predict_value(Xv)
                vl = self._loss(yv, Fv, None)
                self.val_loss_.append(vl)
                if vl < best_loss - 1e-12:
                    best_loss, best_it, since_best = vl, m + 1, 0
                else:
                    since_best += 1
                if self.verbose and m % self.verbose == 0:
                    print(f"  [{m}] train={self.train_loss_[-1]:.5f} val={vl:.5f}")
                if self.early_stopping_rounds and since_best >= self.early_stopping_rounds:
                    break
            elif self.verbose and m % self.verbose == 0:
                print(f"  [{m}] train={self.train_loss_[-1]:.5f}")
        if eval_set is not None and best_it > 0:
            self.trees_ = self.trees_[:best_it]
            self.best_iteration_ = best_it
        else:
            self.best_iteration_ = len(self.trees_)
        self.n_features_ = F_
        self.fit_time_s_ = time.perf_counter() - t0
        return self

    def raw_predict(self, X):
        X = np.asarray(X, dtype=float)
        F = np.full(X.shape[0], self.init_)
        for t in self.trees_:
            F += t.predict_value(X)
        return F

    @property
    def feature_importances_(self):
        imp = sum(t.feature_gain(self.n_features_) for t in self.trees_)
        return imp / imp.sum() if np.sum(imp) > 0 else imp

    def to_dict(self):
        return {"type": type(self).__name__, "init": self.init_, "learning_rate": self.learning_rate,
                "n_features": self.n_features_, "best_iteration": self.best_iteration_,
                "trees": [t.to_dict() for t in self.trees_]}

    @classmethod
    def from_dict(cls, d):
        m = cls(learning_rate=d["learning_rate"])
        m.init_ = d["init"]
        m.n_features_ = d["n_features"]
        m.best_iteration_ = d.get("best_iteration")
        m.trees_ = [Tree.from_dict(t) for t in d["trees"]]
        return m


class GradientBoostingRegressor(_GBDTBase):
    loss_name = "mse"

    def _init_score(self, y, w):
        return float(np.average(y, weights=w))

    def _grad_hess(self, y, F, w):
        return (F - y) * w, w.copy()

    def _loss(self, y, F, w):
        return float(np.average((y - F) ** 2, weights=w))

    def predict(self, X):
        return self.raw_predict(X)


class GradientBoostingClassifier(_GBDTBase):
    """Nhị phân, log-loss. Nhãn y ∈ {0, 1}. scale_pos_weight > 1 tăng trọng số lớp dương."""
    loss_name = "logloss"

    def __init__(self, scale_pos_weight=1.0, **kw):
        super().__init__(**kw)
        self.scale_pos_weight = scale_pos_weight
        self.classes_ = np.array([0, 1])

    def fit(self, X, y, sample_weight=None, eval_set=None):
        y = np.asarray(y, dtype=float).ravel()
        w = np.ones(len(y)) if sample_weight is None else np.asarray(sample_weight, dtype=float)
        w = w * np.where(y > 0.5, self.scale_pos_weight, 1.0)
        return super().fit(X, y, sample_weight=w, eval_set=eval_set)

    def _init_score(self, y, w):
        p = np.clip(np.average(y, weights=w), 1e-6, 1 - 1e-6)
        return float(np.log(p / (1 - p)))

    def _grad_hess(self, y, F, w):
        p = sigmoid(F)
        return (p - y) * w, np.maximum(p * (1 - p), 1e-12) * w

    def _loss(self, y, F, w):
        p = np.clip(sigmoid(F), 1e-15, 1 - 1e-15)
        ll = -(y * np.log(p) + (1 - y) * np.log(1 - p))
        return float(np.average(ll, weights=w))

    def predict_proba(self, X):
        p = sigmoid(self.raw_predict(X))
        return np.column_stack([1 - p, p])

    def predict(self, X, threshold=0.5):
        return (self.predict_proba(X)[:, 1] >= threshold).astype(int)

    def to_dict(self):
        d = super().to_dict()
        d["scale_pos_weight"] = self.scale_pos_weight
        return d
