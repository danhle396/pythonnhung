"""Tiền xử lý dữ liệu, tự cài đặt bằng NumPy.

Công thức:
    StandardScaler : z = (x - mu) / sigma,  mu = (1/n) Σ x_i,  sigma = sqrt((1/n) Σ (x_i - mu)^2)
    MinMaxScaler   : x' = (x - min) / (max - min)  -> [0, 1]
    IQR outlier    : x ngoại lai nếu x < Q1 - k·IQR hoặc x > Q3 + k·IQR, IQR = Q3 - Q1
    z-score outlier: x ngoại lai nếu |x - mu| / sigma > z_thr
    Mã hoá chu kỳ  : sin(2π·t/P), cos(2π·t/P) — giữ tính liên tục giữa 23h và 0h
"""
from __future__ import annotations

import numpy as np

_EPS = 1e-12


def _as2d(X):
    X = np.asarray(X, dtype=float)
    return X.reshape(-1, 1) if X.ndim == 1 else X


class StandardScaler:
    """Chuẩn hoá z-score theo từng cột. Chỉ fit trên tập train."""

    def __init__(self):
        self.mean_ = None
        self.scale_ = None

    def fit(self, X, y=None):
        X = _as2d(X)
        self.mean_ = np.nanmean(X, axis=0)
        std = np.nanstd(X, axis=0)
        self.scale_ = np.where(std < _EPS, 1.0, std)  # cột hằng số -> không chia cho 0
        return self

    def transform(self, X):
        return (_as2d(X) - self.mean_) / self.scale_

    def fit_transform(self, X, y=None):
        return self.fit(X).transform(X)

    def inverse_transform(self, Z):
        return _as2d(Z) * self.scale_ + self.mean_

    def to_dict(self):
        return {"type": "StandardScaler", "mean": self.mean_.tolist(), "scale": self.scale_.tolist()}

    @classmethod
    def from_dict(cls, d):
        s = cls()
        s.mean_ = np.asarray(d["mean"], dtype=float)
        s.scale_ = np.asarray(d["scale"], dtype=float)
        return s


class MinMaxScaler:
    """Đưa từng cột về khoảng [lo, hi] (mặc định [0, 1])."""

    def __init__(self, feature_range=(0.0, 1.0)):
        self.feature_range = feature_range
        self.min_ = None
        self.max_ = None

    def fit(self, X, y=None):
        X = _as2d(X)
        self.min_ = np.nanmin(X, axis=0)
        self.max_ = np.nanmax(X, axis=0)
        return self

    def transform(self, X):
        lo, hi = self.feature_range
        rng = np.where((self.max_ - self.min_) < _EPS, 1.0, self.max_ - self.min_)
        return lo + (_as2d(X) - self.min_) / rng * (hi - lo)

    def fit_transform(self, X, y=None):
        return self.fit(X).transform(X)

    def inverse_transform(self, Z):
        lo, hi = self.feature_range
        rng = np.where((self.max_ - self.min_) < _EPS, 1.0, self.max_ - self.min_)
        return (_as2d(Z) - lo) / (hi - lo) * rng + self.min_

    def to_dict(self):
        return {"type": "MinMaxScaler", "min": self.min_.tolist(), "max": self.max_.tolist(),
                "feature_range": list(self.feature_range)}

    @classmethod
    def from_dict(cls, d):
        s = cls(tuple(d["feature_range"]))
        s.min_ = np.asarray(d["min"], dtype=float)
        s.max_ = np.asarray(d["max"], dtype=float)
        return s


def interpolate_gaps(x, max_gap=None):
    """Nội suy tuyến tính các giá trị NaN trong chuỗi 1 chiều.

    Chỉ lấp các khoảng trống dài không quá `max_gap` mẫu (None = lấp tất cả).
    Khoảng trống ở đầu/cuối chuỗi không được ngoại suy (giữ NaN).
    """
    x = np.asarray(x, dtype=float).copy()
    n = len(x)
    isnan = np.isnan(x)
    if not isnan.any() or isnan.all():
        return x
    idx = np.arange(n)
    good = ~isnan
    filled = np.interp(idx, idx[good], x[good])
    # không ngoại suy ra ngoài đoạn có dữ liệu
    first, last = idx[good][0], idx[good][-1]
    fill_mask = isnan & (idx > first) & (idx < last)
    if max_gap is not None:
        # tính độ dài từng đoạn NaN liên tiếp
        run_id = np.cumsum(~isnan)  # các NaN liên tiếp có chung run_id
        lengths = np.bincount(run_id, weights=isnan.astype(float))
        fill_mask &= lengths[run_id] <= max_gap
    x[fill_mask] = filled[fill_mask]
    return x


def iqr_outlier_mask(x, k=1.5):
    """True tại vị trí là ngoại lai theo quy tắc IQR (Tukey fences)."""
    x = np.asarray(x, dtype=float)
    q1, q3 = np.nanpercentile(x, [25, 75])
    iqr = q3 - q1
    return (x < q1 - k * iqr) | (x > q3 + k * iqr)


def zscore_outlier_mask(x, z_thr=4.0):
    """True tại vị trí có |z| > z_thr."""
    x = np.asarray(x, dtype=float)
    mu, sd = np.nanmean(x), np.nanstd(x)
    if sd < _EPS:
        return np.zeros_like(x, dtype=bool)
    return np.abs(x - mu) / sd > z_thr


def rolling_zscore_outlier_mask(x, window=25, z_thr=4.0):
    """Ngoại lai theo z-score cục bộ dựa trên median/MAD trượt (robust, hợp với chuỗi thời gian)."""
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
    """Trả về (sin, cos) của giá trị chu kỳ, ví dụ giờ trong ngày (period=24)."""
    v = np.asarray(values, dtype=float)
    ang = 2.0 * np.pi * v / period
    return np.sin(ang), np.cos(ang)


def lag_matrix(x, lags):
    """Ma trận lag: cột j = x dịch trễ lags[j] bước (NaN ở đầu)."""
    x = np.asarray(x, dtype=float)
    out = np.full((len(x), len(lags)), np.nan)
    for j, L in enumerate(lags):
        if L == 0:
            out[:, j] = x
        elif L < len(x):
            out[L:, j] = x[:-L]
    return out


def rolling_stat(x, window, stat="mean"):
    """Thống kê trượt (cửa sổ kết thúc tại t, gồm cả t). NaN khi chưa đủ cửa sổ."""
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    if len(x) < window:
        return out
    win = np.lib.stride_tricks.sliding_window_view(x, window)
    if stat == "mean":
        out[window - 1:] = win.mean(axis=1)
    elif stat == "std":
        out[window - 1:] = win.std(axis=1)
    elif stat == "min":
        out[window - 1:] = win.min(axis=1)
    elif stat == "max":
        out[window - 1:] = win.max(axis=1)
    elif stat == "sum":
        out[window - 1:] = win.sum(axis=1)
    else:
        raise ValueError(stat)
    return out


def linear_slope(y, dt=1.0):
    """Hệ số góc bình phương tối thiểu của y theo thời gian (đơn vị: y / dt).

    b = Σ (t - t̄)(y - ȳ) / Σ (t - t̄)^2
    """
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 2:
        return 0.0
    t = np.arange(n) * dt
    tc = t - t.mean()
    return float(np.dot(tc, y - y.mean()) / np.dot(tc, tc))
