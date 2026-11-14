from __future__ import annotations

USAGE = """Ghi log nhãn cho thí nghiệm khí/khói (task.md 8.3).

Đặt thiết bị gửi telemetry 1 giây/lần (PUT /api/devices/station01/config {"telemetry_ms": 1000}), chạy:
    python tools/label_logger.py --device station01 --out ml/data/raw/gas_labeled.csv --session 1

Rồi gõ lệnh + Enter trong lúc thí nghiệm:
    1 lpg_far     bắt đầu sự kiện nhãn 1 (bật lửa gas cách 50 cm, KHÔNG đốt)
    2 lpg_mid     nhãn 2 (20 cm)          3 lpg_near   nhãn 3 (5 cm)
    2 smoke       khói nhang/giấy trong hộp kín
    0 alcohol     nhiễu (cồn) — nhãn 0 nhưng ghi lại tên kịch bản để đo báo động giả
    0             kết thúc sự kiện, về không khí sạch
    q             thoát
⚠ An toàn: lượng nhỏ, nơi thoáng, không có nguồn lửa khi xả gas, luôn có người giám sát.
CSV đầu ra dùng trực tiếp cho: python -m aiot_ml.train_gas_edge --data <csv>
"""

import argparse
import csv
import json
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

FIELDS = ["t", "ts", "gas_ppm", "rs_r0", "temp", "hum", "lux", "label", "scenario", "event_id", "stream_seed"]


def main():
    ap = argparse.ArgumentParser(description=USAGE, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--user", default="backend")
    ap.add_argument("--password", default="backend-pass")
    ap.add_argument("--device", default="station01")
    ap.add_argument("--out", default="ml/data/raw/gas_labeled.csv")
    ap.add_argument("--session", type=int, required=True, help="mã buổi thí nghiệm (dùng để chia train/test)")
    a = ap.parse_args()
    state = {"label": 0, "scenario": "clean", "event": 0}
    lock = threading.Lock()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    new = not out.exists()
    fh = out.open("a", newline="", encoding="utf-8")
    w = csv.DictWriter(fh, fieldnames=FIELDS)
    if new:
        w.writeheader()
    t0 = time.time()
    n = [0]

    def on_msg(c, u, m):
        j = json.loads(m.payload)
        with lock:
            w.writerow({"t": round(time.time() - t0, 1), "ts": j.get("ts"), "gas_ppm": j.get("gas_ppm"),
                        "rs_r0": j.get("gas_rs_r0"), "temp": j.get("temp_dht") or j.get("temp_bmp"),
                        "hum": j.get("hum"), "lux": j.get("lux"), "label": state["label"],
                        "scenario": state["scenario"], "event_id": state["event"], "stream_seed": a.session})
            n[0] += 1
            if n[0] % 10 == 0:
                fh.flush()
                print(f"\r  {n[0]} mẫu | nhãn {state['label']} ({state['scenario']}) | ppm {j.get('gas_ppm')}   ",
                      end="", flush=True)

    c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="label-logger")
    c.username_pw_set(a.user, a.password)
    c.on_message = on_msg
    c.connect(a.host, a.port)
    c.subscribe(f"vku/aiot/{a.device}/telemetry", qos=1)
    c.loop_start()
    print(USAGE.split("Rồi gõ")[1])
    try:
        while True:
            cmd = input().strip().split()
            if not cmd:
                continue
            if cmd[0] == "q":
                break
            with lock:
                state["label"] = int(cmd[0])
                state["scenario"] = cmd[1] if len(cmd) > 1 else ("clean" if cmd[0] == "0" else f"level{cmd[0]}")
                state["event"] += 1
            print(f"\n>>> sự kiện #{state['event']}: nhãn {state['label']} ({state['scenario']})")
    except (KeyboardInterrupt, EOFError):
        pass
    c.loop_stop()
    fh.close()
    print(f"\nĐã ghi {n[0]} mẫu vào {out}")


if __name__ == "__main__":
    main()
