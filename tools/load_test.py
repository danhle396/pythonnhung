"""Load test (task.md 12.1): giả lập N thiết bị, mỗi thiết bị gửi 1 msg/giây trong D giây.

Đo:
  - độ trễ broker (publish -> subscriber giám sát nhận được), P50/P95/P99
  - tỉ lệ mất gói theo seq (QoS 0 hoặc 1)
  - (tuỳ chọn --api) số bản ghi backend thực sự ghi vào DB và độ trễ ingest (received_at − t_pub)
  - CPU/RAM của process backend nếu có psutil và --backend-pid

    python tools/load_test.py --devices 50 --duration 60 --qos 1 --api http://localhost:8000
"""
from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

ROOT = Path(__file__).resolve().parents[1]


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    k = min(len(xs) - 1, max(0, int(round(p / 100 * (len(xs) - 1)))))
    return xs[k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--user", default="backend")
    ap.add_argument("--password", default="backend-pass")
    ap.add_argument("--devices", type=int, default=20)
    ap.add_argument("--duration", type=int, default=30)
    ap.add_argument("--rate", type=float, default=1.0, help="msg/s mỗi thiết bị")
    ap.add_argument("--qos", type=int, default=1)
    ap.add_argument("--prefix", default="loadtest")
    ap.add_argument("--api", default=None, help="URL backend để kiểm tra số bản ghi đã ghi DB")
    ap.add_argument("--backend-pid", type=int, default=None)
    ap.add_argument("--out", default=str(ROOT / "docs" / "report" / "results_load.md"))
    a = ap.parse_args()

    lat, seen, lock = [], {}, threading.Lock()

    def on_msg(c, u, m):
        t = time.time() * 1000
        try:
            j = json.loads(m.payload)
        except Exception:
            return
        if not str(j.get("device_id", "")).startswith(a.prefix) or "t_pub_ms" not in j:
            return  # bỏ qua thiết bị thật / simulator khác đang chạy song song
        with lock:
            lat.append(t - j["t_pub_ms"])
            seen.setdefault(j["device_id"], set()).add(j["seq"])

    mon = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="lt-monitor")
    mon.username_pw_set(a.user, a.password)
    mon.on_message = on_msg
    mon.connect(a.host, a.port)
    mon.subscribe("vku/aiot/+/telemetry", qos=a.qos)
    mon.loop_start()
    time.sleep(0.5)

    sent = {}
    cpu = []
    proc = None
    if a.backend_pid:
        try:
            import psutil
            proc = psutil.Process(a.backend_pid)
            proc.cpu_percent(None)
        except Exception as e:
            print("Không đo CPU:", e)

    def device(i, stop):
        did = f"{a.prefix}{i:03d}"
        c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=f"lt-{did}")
        c.username_pw_set(a.user, a.password)
        c.connect(a.host, a.port)
        c.loop_start()
        seq, start = 0, time.time() + i * (1.0 / a.devices)  # dàn đều thời điểm gửi
        while not stop.is_set():
            if time.time() < start:
                time.sleep(0.005)
                continue
            seq += 1
            payload = {"device_id": did, "ts": int(time.time()), "seq": seq, "temp_dht": 28.0, "hum": 80.0,
                       "pressure_msl": 1010.0, "gas_ppm": 5.0, "edge_risk": 0, "t_pub_ms": time.time() * 1000}
            c.publish(f"vku/aiot/{did}/telemetry", json.dumps(payload), qos=a.qos)
            start += 1.0 / a.rate
        sent[did] = seq
        time.sleep(1.0)
        c.loop_stop()
        c.disconnect()

    stop = threading.Event()
    th = [threading.Thread(target=device, args=(i, stop)) for i in range(a.devices)]
    t0 = time.time()
    for t in th:
        t.start()
    while time.time() - t0 < a.duration:
        time.sleep(1)
        if proc:
            cpu.append(proc.cpu_percent(None))
    stop.set()
    for t in th:
        t.join()
    time.sleep(3)
    mon.loop_stop()
    total_sent = sum(sent.values())
    total_recv = sum(len(v) for v in seen.values())
    loss = 1 - total_recv / total_sent if total_sent else 0
    res = {"devices": a.devices, "duration_s": a.duration, "rate_per_device": a.rate, "qos": a.qos,
           "sent": total_sent, "received": total_recv, "loss_pct": 100 * loss,
           "throughput_msg_s": total_recv / a.duration,
           "broker_latency_ms": {"p50": pct(lat, 50), "p95": pct(lat, 95), "p99": pct(lat, 99),
                                 "mean": statistics.mean(lat) if lat else None}}
    if cpu:
        res["backend_cpu_pct"] = {"mean": statistics.mean(cpu), "max": max(cpu)}
        res["backend_rss_mb"] = proc.memory_info().rss / 1e6
    if a.api:
        import httpx
        time.sleep(2)
        n_db = 0
        for did in sent:
            rows = httpx.get(f"{a.api}/api/telemetry", params={"device_id": did, "from": t0 - 5}, timeout=30).json()
            n_db += len(rows)
        res["db_rows"] = n_db
        res["db_loss_pct"] = 100 * (1 - n_db / total_sent) if total_sent else 0
    print(json.dumps(res, indent=2))
    L = [f"# Load test — {a.devices} thiết bị × {a.rate} msg/s × {a.duration} s (QoS {a.qos})", "",
         "| Chỉ số | Giá trị |", "|---|---|",
         f"| Gửi / nhận | {total_sent} / {total_recv} |", f"| Mất gói (broker) | {res['loss_pct']:.3f} % |",
         f"| Thông lượng | {res['throughput_msg_s']:.1f} msg/s |"]
    for k in ("p50", "p95", "p99"):
        v = res["broker_latency_ms"][k]
        L.append(f"| Độ trễ broker {k.upper()} | {v:.1f} ms |" if v is not None else f"| {k} | — |")
    if "db_rows" in res:
        L.append(f"| Bản ghi vào DB | {res['db_rows']} (mất {res['db_loss_pct']:.3f} %) |")
    if "backend_cpu_pct" in res:
        L.append(f"| CPU backend TB / max | {res['backend_cpu_pct']['mean']:.1f} % / {res['backend_cpu_pct']['max']:.1f} % |")
        L.append(f"| RAM backend | {res['backend_rss_mb']:.0f} MB |")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
