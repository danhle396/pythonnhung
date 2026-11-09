"""Feature engineering cho dự báo thời tiết theo giờ.

Lược đồ chuẩn (canonical) — cả Open-Meteo lẫn dữ liệu trạm đều quy về các cột sau, theo giờ:
    temp   : nhiệt độ (°C)
    hum    : độ ẩm tương đối (%)
    pres   : áp suất quy về mực nước biển (hPa)
    dew    : điểm sương (°C)
    sky    : chỉ số trời quang = bức xạ đo / bức xạ khi trời quang (0..1.5), ban đêm = NaN -> 0
    is_rain: 1 nếu có mưa trong giờ vừa qua (Open-Meteo: precipitation ≥ 0.1 mm; trạm: rain_level ≥ 1)
Chỉ dùng những đại lượng mà trạm thật cũng đo được (task.md mục 8.3).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from mlcore import preprocessing as pp

from .config import STATION

TARGETS = ["temp", "hum", "pres"]
HORIZONS = [1, 3, 6]
RAIN_MM = 0.1
LUX_PER_WM2 = 120.0  # ánh sáng mặt trời ≈ 120 lux / (W/m²)


# --------------------------------------------------------------------- vật lý
def dew_point(temp_c, rh):
    """Công thức Magnus: γ = ln(RH/100) + a·T/(b+T),  Td = b·γ/(a−γ),  a=17.62, b=243.12."""
    a, b = 17.62, 243.12
    rh = np.clip(np.asarray(rh, dtype=float), 1e-3, 100)
    g = np.log(rh / 100.0) + a * np.asarray(temp_c, dtype=float) / (b + np.asarray(temp_c, dtype=float))
    return b * g / (a - g)


def heat_index(temp_c, rh):
    """Heat index (NOAA Rothfusz), trả về °C. Dưới 27°C trả về chính nhiệt độ."""
    T = np.asarray(temp_c, dtype=float) * 9 / 5 + 32
    R = np.asarray(rh, dtype=float)
    hi = (-42.379 + 2.04901523 * T + 10.14333127 * R - 0.22475541 * T * R - 6.83783e-3 * T * T
          - 5.481717e-2 * R * R + 1.22874e-3 * T * T * R + 8.5282e-4 * T * R * R - 1.99e-6 * T * T * R * R)
    out = (hi - 32) * 5 / 9
    return np.where(np.asarray(temp_c) < 27, temp_c, out)


def sea_level_pressure(p_station_hpa, temp_c, alt_m=STATION["alt_m"]):
    """Quy áp suất trạm về mực nước biển (công thức khí áp, như datasheet BMP280/Bosch):
        P0 = P · (1 − 0.0065·h / (T + 0.0065·h + 273.15))^(−5.257)"""
    p = np.asarray(p_station_hpa, dtype=float)
    t = np.asarray(temp_c, dtype=float)
    return p * (1 - 0.0065 * alt_m / (t + 0.0065 * alt_m + 273.15)) ** (-5.257)


def solar_cos_zenith(times: pd.DatetimeIndex, lat=STATION["lat"], lon=STATION["lon"], tz_offset_h=7.0):
    """cos(góc thiên đỉnh) của mặt trời tại giữa mỗi giờ (giờ địa phương), công thức NOAA rút gọn."""
    t = pd.DatetimeIndex(times) - pd.Timedelta(minutes=30)  # precipitation/radiation là tổng giờ trước
    doy = t.day_of_year.values
    hour = t.hour.values + t.minute.values / 60.0
    gamma = 2 * np.pi / 365 * (doy - 1 + (hour - 12) / 24)
    decl = (0.006918 - 0.399912 * np.cos(gamma) + 0.070257 * np.sin(gamma) - 0.006758 * np.cos(2 * gamma)
            + 0.000907 * np.sin(2 * gamma) - 0.002697 * np.cos(3 * gamma) + 0.00148 * np.sin(3 * gamma))
    eqt = 229.18 * (0.000075 + 0.001868 * np.cos(gamma) - 0.032077 * np.sin(gamma)
                    - 0.014615 * np.cos(2 * gamma) - 0.040849 * np.sin(2 * gamma))
    tst = hour * 60 + eqt + 4 * lon - 60 * tz_offset_h  # giờ mặt trời thực (phút)
    ha = np.deg2rad(tst / 4 - 180)
    phi = np.deg2rad(lat)
    return np.clip(np.sin(phi) * np.sin(decl) + np.cos(phi) * np.cos(decl) * np.cos(ha), -1, 1)


def clear_sky_ghi(cos_z):
    """Mô hình Haurwitz: GHI_clear = 1098·cos z·exp(−0.057/cos z)  (W/m²)."""
    cz = np.asarray(cos_z, dtype=float)
    out = np.zeros_like(cz)
    m = cz > 0.02
    out[m] = 1098 * cz[m] * np.exp(-0.057 / cz[m])
    return out


# --------------------------------------------------------------------- chuẩn hoá nguồn dữ liệu
def open_meteo_to_canonical(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["temp"] = df["temperature_2m"]
    out["hum"] = df["relative_humidity_2m"]
    out["pres"] = df["pressure_msl"]
    out["dew"] = df["dew_point_2m"]
    cz = solar_cos_zenith(df.index)
    ghi_c = clear_sky_ghi(cz)
    out["sky"] = np.where(ghi_c > 50, np.clip(df["shortwave_radiation"] / np.maximum(ghi_c, 1), 0, 1.5), np.nan)
    out["is_rain"] = (df["precipitation"].fillna(0) >= RAIN_MM).astype(float)
    out["precip_mm"] = df["precipitation"]
    return out


def station_to_canonical(tel: pd.DataFrame, alt_m=STATION["alt_m"]) -> pd.DataFrame:
    """tel: telemetry trạm (index thời gian, cột temp_dht, temp_bmp, hum, pressure, lux, rain_level).
    Resample về giờ (giá trị cuối khoảng giống quy ước Open-Meteo: nhãn giờ t = khoảng (t−1h, t])."""
    t = tel.copy()
    temp = t["temp_dht"].where(t["temp_dht"].notna(), t.get("temp_bmp"))
    t["temp"] = temp
    t["pres"] = sea_level_pressure(t["pressure"], temp, alt_m) if "pressure_msl" not in t else t["pressure_msl"]
    hourly = pd.DataFrame({
        "temp": t["temp"].resample("1h", label="right", closed="right").mean(),
        "hum": t["hum"].resample("1h", label="right", closed="right").mean(),
        "pres": t["pres"].resample("1h", label="right", closed="right").mean(),
        "lux": t["lux"].resample("1h", label="right", closed="right").mean(),
        "is_rain": (t["rain_level"] >= 1).astype(float).resample("1h", label="right", closed="right").max(),
    })
    hourly["dew"] = dew_point(hourly["temp"], hourly["hum"])
    cz = solar_cos_zenith(hourly.index)
    ghi_c = clear_sky_ghi(cz)
    hourly["sky"] = np.where(ghi_c > 50, np.clip(hourly["lux"] / LUX_PER_WM2 / np.maximum(ghi_c, 1), 0, 1.5), np.nan)
    return hourly.drop(columns=["lux"])


def clean(df: pd.DataFrame, max_gap_h=3) -> pd.DataFrame:
    """Đưa về lưới giờ đều, loại ngoại lai (z-score cục bộ robust), nội suy khoảng trống ngắn."""
    df = df.asfreq("1h")
    out = df.copy()
    for c in ["temp", "hum", "pres", "dew"]:
        x = out[c].to_numpy(dtype=float, copy=True)
        x[pp.rolling_zscore_outlier_mask(x, window=49, z_thr=6.0)] = np.nan
        out[c] = pp.interpolate_gaps(x, max_gap=max_gap_h)
    out["is_rain"] = out["is_rain"].fillna(0.0)
    return out


# --------------------------------------------------------------------- feature
def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Tạo bảng feature tại mỗi thời điểm t chỉ từ dữ liệu ≤ t (không rò rỉ tương lai)."""
    f = pd.DataFrame(index=df.index)
    T, H, P, D = (df[c].to_numpy(dtype=float) for c in ["temp", "hum", "pres", "dew"])
    R = df["is_rain"].to_numpy(dtype=float)
    S = np.nan_to_num(df["sky"].to_numpy(dtype=float), nan=0.0)
    f["temp"], f["hum"], f["pres"], f["dew"] = T, H, P, D
    f["dpd"] = T - D  # chênh lệch nhiệt độ – điểm sương (càng nhỏ càng gần bão hoà)
    f["sky"] = S
    f["is_rain"] = R
    for name, x in [("temp", T), ("hum", H), ("pres", P)]:
        L = pp.lag_matrix(x, [1, 2, 3, 6, 12, 24])
        for j, lag in enumerate([1, 2, 3, 6, 12, 24]):
            f[f"{name}_d{lag}"] = x - L[:, j]  # thay đổi so với lag giờ trước
        for w in (3, 6, 24):
            f[f"{name}_mean{w}"] = pp.rolling_stat(x, w, "mean") - x
            f[f"{name}_std{w}"] = pp.rolling_stat(x, w, "std")
    f["pres_trend3"] = f["pres_d3"]  # xu hướng áp suất 3h (Zambretti)
    f["dpd_d3"] = f["dpd"] - pp.lag_matrix(f["dpd"].to_numpy(), [3])[:, 0]
    for w in (3, 6, 24):
        f[f"rain_frac{w}"] = pp.rolling_stat(R, w, "mean")
    # số giờ kể từ lần mưa gần nhất (giới hạn 72)
    since = np.zeros(len(R))
    c = 72.0
    for i, r in enumerate(R):
        c = 0.0 if r > 0 else min(c + 1.0, 72.0)
        since[i] = c
    f["hours_since_rain"] = since
    f["sky_mean3"] = pp.rolling_stat(S, 3, "mean")
    f["sky_d1"] = S - pp.lag_matrix(S, [1])[:, 0]
    idx = pd.DatetimeIndex(df.index)
    f["hour_sin"], f["hour_cos"] = pp.cyclic_encode(idx.hour.values, 24)
    f["doy_sin"], f["doy_cos"] = pp.cyclic_encode(idx.day_of_year.values, 365.25)
    f["cos_zenith"] = solar_cos_zenith(idx)
    return f


def build_targets(df: pd.DataFrame, horizons=HORIZONS) -> pd.DataFrame:
    """Target hồi quy dạng thay đổi: y = x(t+h) − x(t); target mưa: có mưa trong (t, t+h]."""
    t = pd.DataFrame(index=df.index)
    for c in TARGETS:
        x = df[c].to_numpy(dtype=float)
        for h in horizons:
            fut = np.full(len(x), np.nan)
            fut[:-h] = x[h:]
            t[f"{c}_{h}h"] = fut - x
    R = df["is_rain"].to_numpy(dtype=float)
    for h in horizons:
        fut = np.full(len(R), np.nan)
        win = np.lib.stride_tricks.sliding_window_view(R, h)  # win[i] = R[i..i+h-1]
        fut[:len(R) - h] = win[1:].max(axis=1) if h > 0 else R
        t[f"rain_{h}h"] = fut
    return t


def seasonal_naive(df: pd.DataFrame, target: str, h: int) -> np.ndarray:
    """Dự báo thay đổi theo seasonal naive: x̂(t+h) = x(t+h−24) ⇒ Δ̂ = x(t+h−24) − x(t)."""
    x = df[target].to_numpy(dtype=float)
    pred = np.full(len(x), np.nan)
    lag = 24 - h
    pred[lag:] = x[:-lag] - x[lag:]
    return pred


FEATURE_COLUMNS: list[str] | None = None


def feature_columns(f: pd.DataFrame) -> list[str]:
    return list(f.columns)
