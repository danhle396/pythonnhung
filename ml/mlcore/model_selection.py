"""Chia dữ liệu theo thời gian, cross-validation chuỗi thời gian, grid/random search.

Với chuỗi thời gian KHÔNG được xáo trộn: tập sau luôn nằm sau tập trước về thời gian,
nếu không model sẽ "nhìn thấy tương lai" (data leakage).
"""
from __future__ import annotations

import itertools
import random as _random
import time

import numpy as np


def time_train_val_test_split(n, val_frac=0.15, test_frac=0.15, gap=0):
    """Trả về (idx_train, idx_val, idx_test) liên tiếp theo thời gian.

    `gap` mẫu bị bỏ giữa các tập để tránh rò rỉ qua lag/target dịch thời gian.
    """
    n_test = int(round(n * test_frac))
    n_val = int(round(n * val_frac))
    n_train = n - n_val - n_test - 2 * gap
    if n_train <= 0:
        raise ValueError("Dữ liệu quá ít để chia")
    i_tr = np.arange(0, n_train)
    i_va = np.arange(n_train + gap, n_train + gap + n_val)
    i_te = np.arange(n - n_test, n)
    return i_tr, i_va, i_te


class TimeSeriesSplit:
    """Cross-validation cửa sổ mở rộng (expanding window).

    Fold k: train = [0, end_k),  test = [end_k + gap, end_k + gap + test_size)
    """

    def __init__(self, n_splits=5, test_size=None, gap=0, max_train_size=None):
        self.n_splits = n_splits
        self.test_size = test_size
        self.gap = gap
        self.max_train_size = max_train_size

    def split(self, X):
        n = len(X)
        test_size = self.test_size or n // (self.n_splits + 1)
        first_test_start = n - self.n_splits * test_size
        if first_test_start - self.gap <= 0:
            raise ValueError("Không đủ mẫu cho số fold yêu cầu")
        for k in range(self.n_splits):
            test_start = first_test_start + k * test_size
            train_end = test_start - self.gap
            train_start = 0 if self.max_train_size is None else max(0, train_end - self.max_train_size)
            yield np.arange(train_start, train_end), np.arange(test_start, test_start + test_size)


class ParameterGrid:
    """Tích Đề-các của các giá trị tham số: {'a': [1, 2], 'b': [3]} -> [{'a':1,'b':3}, {'a':2,'b':3}]."""

    def __init__(self, grid: dict):
        self.grid = grid

    def __iter__(self):
        keys = sorted(self.grid)
        for vals in itertools.product(*(self.grid[k] for k in keys)):
            yield dict(zip(keys, vals))

    def __len__(self):
        n = 1
        for v in self.grid.values():
            n *= len(v)
        return n


def cross_val_score(make_model, params, X, y, cv, scorer, fit_kwargs=None):
    scores = []
    for tr, te in cv.split(X):
        m = make_model(**params)
        m.fit(X[tr], y[tr], **(fit_kwargs or {}))
        scores.append(scorer(m, X[te], y[te]))
    return float(np.mean(scores)), scores


def grid_search(make_model, param_grid, X, y, cv, scorer, greater_is_better=False, verbose=False):
    """Thử mọi tổ hợp tham số, trả về (best_params, best_score, history)."""
    return _search(make_model, list(ParameterGrid(param_grid)), X, y, cv, scorer, greater_is_better, verbose)


def random_search(make_model, param_dist, n_iter, X, y, cv, scorer, greater_is_better=False,
                  seed=42, verbose=False):
    """Lấy ngẫu nhiên n_iter tổ hợp. param_dist: {name: list | callable(rng)}."""
    rng = _random.Random(seed)
    cands = []
    for _ in range(n_iter):
        p = {}
        for k, v in param_dist.items():
            p[k] = v(rng) if callable(v) else rng.choice(list(v))
        cands.append(p)
    return _search(make_model, cands, X, y, cv, scorer, greater_is_better, verbose)


def _search(make_model, candidates, X, y, cv, scorer, greater_is_better, verbose):
    history = []
    best, best_score = None, None
    for p in candidates:
        t0 = time.perf_counter()
        score, folds = cross_val_score(make_model, p, X, y, cv, scorer)
        history.append({"params": p, "score": score, "folds": folds, "time_s": time.perf_counter() - t0})
        better = best_score is None or (score > best_score if greater_is_better else score < best_score)
        if better:
            best, best_score = p, score
        if verbose:
            print(f"  {p} -> {score:.4f}")
    return best, best_score, history
