from __future__ import annotations

USAGE = """Tải lịch sử thời tiết theo giờ tại VKU từ Open-Meteo Historical API (miễn phí, không cần key).

    python -m aiot_ml.fetch_open_meteo --start 2021-01-01 --end 2025-12-31
Kết quả: ml/data/external/vku_hourly_<start>_<end>.csv
"""

import argparse
import datetime as dt
import time
from pathlib import Path

import pandas as pd
import requests

from .config import DATA_DIR, STATION

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARS = ["temperature_2m", "relative_humidity_2m", "dew_point_2m", "surface_pressure",
               "pressure_msl", "precipitation", "rain", "shortwave_radiation", "cloud_cover"]


def _get(url, params, retries=4):
    for k in range(retries):
        try:
            r = requests.get(url, params=params, timeout=60, headers={"User-Agent": "vku-aiot-station/1.0"})
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if k == retries - 1:
                raise
            wait = 2 ** k * 3
            print(f"  lỗi {e!r}, thử lại sau {wait}s")
            time.sleep(wait)


def fetch_archive(start: str, end: str, lat=STATION["lat"], lon=STATION["lon"]) -> pd.DataFrame:
    frames = []
    s = dt.date.fromisoformat(start)
    e = dt.date.fromisoformat(end)
    while s <= e:
        chunk_end = min(dt.date(s.year, 12, 31), e)
        print(f"  tải {s} -> {chunk_end}")
        js = _get(ARCHIVE_URL, {"latitude": lat, "longitude": lon, "start_date": s.isoformat(),
                                "end_date": chunk_end.isoformat(), "hourly": ",".join(HOURLY_VARS),
                                "timezone": STATION["tz"]})
        frames.append(pd.DataFrame(js["hourly"]))
        s = chunk_end + dt.timedelta(days=1)
    df = pd.concat(frames, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"])
    return df.drop_duplicates("time").set_index("time").sort_index()


def fetch_recent(past_days=7, lat=STATION["lat"], lon=STATION["lon"]) -> pd.DataFrame:
    js = _get(FORECAST_URL, {"latitude": lat, "longitude": lon, "past_days": past_days, "forecast_days": 1,
                             "hourly": ",".join(HOURLY_VARS), "timezone": STATION["tz"]})
    df = pd.DataFrame(js["hourly"])
    df["time"] = pd.to_datetime(df["time"])
    return df.set_index("time").sort_index()


def main(argv=None):
    ap = argparse.ArgumentParser(description=USAGE)
    ap.add_argument("--start", default="2021-01-01")
    ap.add_argument("--end", default="2025-12-31")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    out = Path(a.out) if a.out else DATA_DIR / "external" / f"vku_hourly_{a.start[:4]}_{a.end[:4]}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df = fetch_archive(a.start, a.end)
    df.to_csv(out)
    print(f"Đã lưu {len(df)} dòng ({df.index.min()} -> {df.index.max()}) vào {out}")
    print(df.describe().T[["mean", "min", "max"]].round(2))


if __name__ == "__main__":
    main()
