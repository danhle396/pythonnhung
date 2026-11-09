"""Holt-Winters (triple exponential smoothing), dạng cộng, chu kỳ mùa m (mặc định 24h).

    Mức      : ℓ_t = α (y_t − s_{t−m}) + (1 − α)(ℓ_{t−1} + b_{t−1})
    Xu hướng : b_t = β (ℓ_t − ℓ_{t−1}) + (1 − β) φ b_{t−1}
    Mùa      : s_t = γ (y_t − ℓ_t) + (1 − γ) s_{t−m}
    Dự báo   : ŷ_{t+h|t} = ℓ_t + (φ + φ² + … + φ^h) b_t + s_{t+h−m(k+1)},  k = ⌊(h−1)/m⌋

φ là hệ số giảm chấn xu hướng (damped trend, φ = 1 là Holt-Winters gốc).
Tham số (α, β, γ) được chọn bằng grid search cực tiểu tổng bình phương sai số dự báo h bước.
"""
from __future__ import annotations

import itertools

import numpy as np


class HoltWinters:
    def __init__(self, season_length=24, alpha=0.3, beta=0.01, gamma=0.1, phi=0.98):
        self.m = season_length
        self.alpha, self.beta, self.gamma, self.phi = alpha, beta, gamma, phi
        self.level_ = None
        self.trend_ = None
        self.season_ = None

    def _init_state(self, y):
        m = self.m
        if len(y) < 2 * m:
            raise ValueError("Cần ít nhất 2 chu kỳ mùa để khởi tạo")
        level = y[:m].mean()
        trend = (y[m:2 * m].mean() - y[:m].mean()) / m
        season = y[:m] - level
        return level, trend, season.copy()

    def _run(self, y, horizon=None):
        """Chạy bộ lọc qua chuỗi y. Nếu horizon != None, trả về dự báo h bước tại mỗi thời điểm t
        (preds[t] = ŷ_{t+h|t}), dùng để đánh giá rolling-origin mà không cần fit lại."""
        a, b_, g, phi, m = self.alpha, self.beta, self.gamma, self.phi, self.m
        level, trend, season = self._init_state(y)
        season = list(season)
        n = len(y)
        preds = np.full(n, np.nan) if horizon is not None else None
        if horizon is not None:
            damp = sum(phi ** i for i in range(1, horizon + 1))
        for t in range(m, n):
            s_old = season[t - m]
            yt = y[t]
            if np.isnan(yt):  # thiếu dữ liệu -> dùng giá trị dự báo 1 bước
                yt = level + phi * trend + s_old
            new_level = a * (yt - s_old) + (1 - a) * (level + phi * trend)
            trend = b_ * (new_level - level) + (1 - b_) * phi * trend
            level = new_level
            season.append(g * (yt - level) + (1 - g) * s_old)
            if horizon is not None:
                preds[t] = level + damp * trend + season[t + horizon - m * ((horizon - 1) // m + 1)]
        self.level_, self.trend_ = level, trend
        self.season_ = np.asarray(season[-m:])
        self._n = n
        return preds

    def fit(self, y, optimize=True, horizon=1, grid=None):
        y = np.asarray(y, dtype=float)
        if optimize:
            grid = grid or {"alpha": [0.1, 0.3, 0.5, 0.8], "beta": [0.0, 0.01, 0.05],
                            "gamma": [0.05, 0.1, 0.3]}
            best = (np.inf, None)
            for a, b_, g in itertools.product(grid["alpha"], grid["beta"], grid["gamma"]):
                self.alpha, self.beta, self.gamma = a, b_, g
                p = self._run(y, horizon)
                err = y[horizon:] - p[:-horizon]
                sse = np.nanmean(err[2 * self.m:] ** 2)
                if sse < best[0]:
                    best = (sse, (a, b_, g))
            self.alpha, self.beta, self.gamma = best[1]
        self._run(y)
        return self

    def forecast(self, steps):
        """Dự báo `steps` bước tiếp theo sau điểm cuối của chuỗi đã fit."""
        out = np.empty(steps)
        for h in range(1, steps + 1):
            damp = sum(self.phi ** i for i in range(1, h + 1))
            out[h - 1] = self.level_ + damp * self.trend_ + self.season_[(h - 1) % self.m]
        return out

    def rolling_forecast(self, y, horizon):
        """preds[t] = dự báo cho thời điểm t+horizon được lập tại t (dùng tham số đã fit)."""
        return self._run(np.asarray(y, dtype=float), horizon)

    def to_dict(self):
        return {"type": "HoltWinters", "m": self.m, "alpha": self.alpha, "beta": self.beta,
                "gamma": self.gamma, "phi": self.phi, "level": self.level_, "trend": self.trend_,
                "season": None if self.season_ is None else self.season_.tolist()}

    @classmethod
    def from_dict(cls, d):
        m = cls(d["m"], d["alpha"], d["beta"], d["gamma"], d["phi"])
        m.level_, m.trend_ = d["level"], d["trend"]
        m.season_ = None if d["season"] is None else np.asarray(d["season"])
        return m


def exponential_smoothing(x, alpha):
    """EWMA đơn: s_t = α x_t + (1 − α) s_{t−1}."""
    x = np.asarray(x, dtype=float)
    s = np.empty_like(x)
    s[0] = x[0]
    for t in range(1, len(x)):
        s[t] = alpha * x[t] + (1 - alpha) * s[t - 1]
    return s
