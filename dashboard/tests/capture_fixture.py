from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

OUT = Path(__file__).with_name("api_fixture.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--device", default="station01")
    a = ap.parse_args()
    dev = a.device
    calls = {
        "/api/devices": {},
        f"/api/devices/{dev}": {},
        "/api/telemetry/latest": {"device_id": dev},
        f"/api/sensors/{dev}": {"minutes": 10},
        f"/api/forecast/{dev}": {"history_h": 72},
        "/api/alerts": {"device_id": dev, "limit": 50},
        "/api/telemetry": {"device_id": dev, "resolution": "1m", "from": time.time() - 24 * 3600},
        f"/api/devices/{dev}/configs": {},
        f"/api/devices/{dev}/commands": {},
        "/api/models": {},
    }
    fix = {}
    for path, params in calls.items():
        r = requests.get(a.api + path, params=params, timeout=15)
        r.raise_for_status()
        fix[path] = r.json()
        print(f"{path:32s} {len(fix[path]) if hasattr(fix[path], '__len__') else ''}")
    OUT.write_text(json.dumps(fix, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Đã ghi", OUT)


if __name__ == "__main__":
    main()
