"""Bộ tối ưu dựa trên gradient. Tham số và gradient là dict {tên: ndarray}; cập nhật tại chỗ.

SGD      : θ ← θ - η·g
Momentum : v ← μ·v - η·g ;  θ ← θ + v
Adam     : m ← β1·m + (1-β1)·g ;  v ← β2·v + (1-β2)·g² ;
           m̂ = m/(1-β1^t) ;  v̂ = v/(1-β2^t) ;  θ ← θ - η·m̂/(√v̂ + ε)
"""
from __future__ import annotations

import numpy as np


class SGD:
    def __init__(self, lr=0.01):
        self.lr = lr

    def step(self, params, grads):
        for k in params:
            params[k] -= self.lr * grads[k]


class Momentum:
    def __init__(self, lr=0.01, momentum=0.9):
        self.lr, self.mu = lr, momentum
        self.v = {}

    def step(self, params, grads):
        for k in params:
            v = self.v.setdefault(k, np.zeros_like(params[k]))
            v *= self.mu
            v -= self.lr * grads[k]
            params[k] += v


class Adam:
    def __init__(self, lr=1e-3, beta1=0.9, beta2=0.999, eps=1e-8):
        self.lr, self.b1, self.b2, self.eps = lr, beta1, beta2, eps
        self.m, self.v, self.t = {}, {}, 0

    def step(self, params, grads):
        self.t += 1
        for k in params:
            g = grads[k]
            m = self.m.setdefault(k, np.zeros_like(params[k]))
            v = self.v.setdefault(k, np.zeros_like(params[k]))
            m *= self.b1
            m += (1 - self.b1) * g
            v *= self.b2
            v += (1 - self.b2) * g * g
            mhat = m / (1 - self.b1 ** self.t)
            vhat = v / (1 - self.b2 ** self.t)
            params[k] -= self.lr * mhat / (np.sqrt(vhat) + self.eps)


def clip_grad_norm(grads, max_norm):
    """Gradient clipping theo chuẩn L2 toàn cục: g ← g · min(1, max_norm / ||g||)."""
    total = np.sqrt(sum(float(np.sum(g * g)) for g in grads.values()))
    if total > max_norm > 0:
        s = max_norm / (total + 1e-12)
        for k in grads:
            grads[k] *= s
    return total


def make_optimizer(name, **kw):
    name = name.lower()
    if name == "sgd":
        return SGD(**kw)
    if name == "momentum":
        return Momentum(**kw)
    if name == "adam":
        return Adam(**kw)
    raise ValueError(name)
