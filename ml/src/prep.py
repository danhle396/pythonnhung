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
