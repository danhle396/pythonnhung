"""Xử lý chuỗi thời gian dùng chung cho feature (NumPy): lấp khoảng trống, lọc ngoại lai, trễ, cửa sổ trượt.

Đây là bước chuẩn bị dữ liệu, không phải mô hình học máy — các mô hình lấy từ scikit-learn, LightGBM,
statsmodels, PyTorch (xem train_forecast.py).
"""
from __future__ import annotations

import numpy as np

_EPS = 1e-12


def interpolate_gaps(x, max_gap=None):
    """Nội suy tuyến tính các đoạn NaN bên trong chuỗi, chỉ lấp đoạn dài ≤ max_gap mẫu."""
    x = np.asarray(x, dtype=float).copy()
    n = len(x)
    isnan = np.isnan(x)
    if not isnan.any() or isnan.all():
        return x
    idx = np.arange(n)
    good = ~isnan
    filled = np.interp(idx, idx[good], x[good])
    first, last = idx[good][0], idx[good][-1]
    fill_mask = isnan & (idx > first) & (idx < last)
    if max_gap is not None:
        run_id = np.cumsum(~isnan)
        lengths = np.bincount(run_id, weights=isnan.astype(float))
        fill_mask &= lengths[run_id] <= max_gap
    x[fill_mask] = filled[fill_mask]
    return x


def rolling_zscore_outlier_mask(x, window=25, z_thr=4.0):
    """Ngoại lai theo z-score bền (median/MAD) trong cửa sổ trượt có tâm."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    half = window // 2
    pad = np.pad(x, half, mode="edge")
    win = np.lib.stride_tricks.sliding_window_view(pad, window)[:n]
    med = np.nanmedian(win, axis=1)
    mad = np.nanmedian(np.abs(win - med[:, None]), axis=1) * 1.4826
    mad = np.where(mad < _EPS, np.inf, mad)
    return np.abs(x - med) / mad > z_thr


def cyclic_encode(values, period):
    v = np.asarray(values, dtype=float)
    ang = 2.0 * np.pi * v / period
    return np.sin(ang), np.cos(ang)


def lag_matrix(x, lags):
    x = np.asarray(x, dtype=float)
    out = np.full((len(x), len(lags)), np.nan)
    for j, L in enumerate(lags):
        if L == 0:
            out[:, j] = x
        elif L < len(x):
            out[L:, j] = x[:-L]
    return out


def rolling_stat(x, window, stat="mean"):
    """Thống kê cửa sổ trượt chỉ nhìn quá khứ (giá trị tại t dùng x[t-window+1..t])."""
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    if len(x) < window:
        return out
    win = np.lib.stride_tricks.sliding_window_view(x, window)
    fn = {"mean": np.mean, "std": np.std, "min": np.min, "max": np.max, "sum": np.sum}[stat]
    out[window - 1:] = fn(win, axis=1)
    return out


def linear_slope(y, dt=1.0):
    """Hệ số góc bình phương tối thiểu của y theo thời gian."""
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 2:
        return 0.0
    t = np.arange(n) * dt
    tc = t - t.mean()
    return float(np.dot(tc, y - y.mean()) / np.dot(tc, tc))


class HourlyZScore:
    """Ngưỡng thống kê theo giờ trong ngày: z = (x − μ_giờ) / σ_giờ."""

    def __init__(self, z_thr=3.0):
        self.z_thr = z_thr
        self.mu_ = self.sd_ = None

    def fit(self, x, hours):
        x, hours = np.asarray(x, dtype=float), np.asarray(hours, dtype=int)
        self.mu_ = np.array([np.nanmean(x[hours == h]) if np.any(hours == h) else np.nanmean(x) for h in range(24)])
        self.sd_ = np.array([np.nanstd(x[hours == h]) if np.sum(hours == h) > 1 else np.nanstd(x) for h in range(24)])
        self.sd_ = np.maximum(self.sd_, 1e-9)
        return self

    def score(self, x, hours):
        hours = np.asarray(hours, dtype=int)
        return (np.asarray(x, dtype=float) - self.mu_[hours]) / self.sd_[hours]


class CUSUM:
    """CUSUM hai phía (Page, 1954) trên chuỗi đã chuẩn hoá theo đoạn tham chiếu."""

    def __init__(self, k=0.5, h=5.0):
        self.k, self.h = k, h
        self.mu_ = self.sigma_ = None

    def fit(self, ref):
        ref = np.asarray(ref, dtype=float)
        self.mu_ = float(np.nanmean(ref))
        self.sigma_ = float(max(np.nanstd(ref), 1e-9))
        return self

    def detect(self, x):
        sp = sn = 0.0
        alarms = []
        for i, v in enumerate(np.asarray(x, dtype=float)):
            if np.isnan(v):
                continue
            z = (v - self.mu_) / self.sigma_
            sp, sn = max(0.0, sp + z - self.k), max(0.0, sn - z - self.k)
            a = 1 if sp > self.h else (-1 if sn > self.h else 0)
            if a:
                alarms.append((i, a))
                sp = sn = 0.0
        return {"alarms": alarms}
