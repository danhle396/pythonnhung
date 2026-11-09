"""Giả lập trạm ESP32 publish MQTT — để phát triển backend/dashboard khi chưa có phần cứng.

Chạy đúng logic edge (ml/src/gas_edge.py = bản Python của firmware/src/edge_ai.cpp + alert.cpp) với
model cây đã huấn luyện (ml/models/gas_edge.json) và bộ mô phỏng MQ-2 (gas_sim.py).

    python tools/simulator.py                                   # 1 trạm, thời tiết mô phỏng, khí sạch
    python tools/simulator.py --events "30:lpg_mid,240:smoke"   # rò gas ở giây 30, khói ở giây 240
    python tools/simulator.py --backfill-hours 48               # gửi trước 48h lịch sử (để forecast chạy ngay)
    python tools/simulator.py --devices 3 --speed 5

Hỗ trợ cmd (mute/test_alarm/calibrate/reboot/escalate), config (ghi đè ngưỡng) và gửi ack như firmware.
LWT: {"state":"offline"} retain trên .../status.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import threading
import time
from pathlib import Path

import numpy as np
import paho.mqtt.client as mqtt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
from aiot_ml.gas_edge import EdgeEngine, RuleConfig  # noqa: E402
from aiot_ml.gas_sim import Mq2Simulator  # noqa: E402
from aiot_ml.features import dew_point, heat_index, sea_level_pressure  # noqa: E402

LEVEL_NAME = ["normal", "advisory", "warning", "danger"]


def load_edge_model():
    try:
        from mlcore.serialize import load_model
        b, head = load_model(ROOT / "ml" / "models" / "gas_edge.json")
        return b["model"], head["model_ver"]
    except Exception as e:
        print("Không nạp được model edge, chỉ dùng rule:", e)
        return None, "rule-only"


class Weather:
    """Thời tiết mô phỏng tại VKU tháng 11: chu kỳ ngày + nhiễu + đợt mưa ngẫu nhiên."""

    def __init__(self, seed):
        self.rng = np.random.default_rng(seed)
        self.p_off = self.rng.normal(0, 1.5)
        self.rain_until = 0

    def at(self, ts):
        lt = time.localtime(ts)
        h = lt.tm_hour + lt.tm_min / 60
        day = ts / 86400
        T = 25.5 + 3.0 * math.sin(2 * math.pi * (h - 9) / 24) + 0.8 * math.sin(day / 3) + self.rng.normal(0, 0.05)
        H = 82 - 9 * math.sin(2 * math.pi * (h - 9) / 24) + self.rng.normal(0, 0.3)
        P = 1011 + self.p_off + 1.2 * math.sin(2 * math.pi * (h - 10) / 12) + 1.5 * math.sin(day / 2.5)
        if ts > self.rain_until and self.rng.random() < 0.0004:
            self.rain_until = ts + self.rng.uniform(1200, 7200)
        raining = ts < self.rain_until
        if raining:
            H = min(98, H + 10)
            T -= 1.5
        sun = max(0.0, math.sin(math.pi * (h - 5.8) / 12.4)) if 5.8 < h < 18.2 else 0.0
        lux = 60000 * sun * (0.25 if raining else self.rng.uniform(0.5, 1.0))
        return T, min(H, 100), P, lux, (2 if raining else 0)


class SimDevice:
    def __init__(self, device_id, args, model, model_ver, idx):
        self.id, self.a = device_id, args
        self.prefix = f"vku/aiot/{device_id}/"
        self.seq = int(time.time()) % 1_000_000 * 10
        self.weather = Weather(idx + 7)
        self.mq2 = Mq2Simulator(seed=idx + 100)
        self.engine = EdgeEngine(model=model, mode="hybrid", rule_cfg=RuleConfig(), warmup_s=args.warmup)
        self.model_ver = model_ver
        self.level = 0
        self.cloud_level, self.cloud_until = 0, 0
        self.muted_until, self.test_until = 0, 0
        self.telemetry_ms = args.period * 1000
        self.gas_queue: list[dict] = []
        self.events = sorted((float(t), k) for t, k in (e.split(":") for e in args.events.split(",") if e)) \
            if args.events else []
        self.t0 = time.time()
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=f"sim-{device_id}-{random.randint(0, 99999)}")
        self.client.username_pw_set(args.user or device_id, args.password)
        self.client.will_set(self.prefix + "status", json.dumps({"state": "offline"}), qos=1, retain=True)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.lock = threading.Lock()

    def on_connect(self, c, u, f, rc, p):
        for t in ("cmd", "config", "forecast"):
            c.subscribe(self.prefix + t, qos=1)
        print(f"[{self.id}] kết nối broker rc={rc}")
        self.status()

    def ack(self, ref, ok, msg, cid=None):
        self.pub("ack", {"device_id": self.id, "ts": int(time.time()), "ref": ref, "id": cid, "ok": ok, "msg": msg})

    def on_message(self, c, u, m):
        kind = m.topic.rsplit("/", 1)[-1]
        try:
            j = json.loads(m.payload)
        except Exception:
            return self.ack(kind, False, "bad json")
        now = time.time()
        if kind == "cmd":
            cmd = j.get("cmd")
            if cmd == "mute":
                self.muted_until = now + 300
            elif cmd == "test_alarm":
                self.test_until = now + 3
            elif cmd == "escalate":
                self.cloud_level, self.cloud_until = int(j.get("level", 0)), now + 60
            elif cmd == "calibrate":
                pass
            elif cmd == "reboot":
                self.engine = EdgeEngine(model=self.engine.model, mode="hybrid", rule_cfg=self.engine.rules.cfg,
                                         warmup_s=self.a.warmup)
            else:
                return self.ack("cmd", False, "unknown cmd", j.get("id"))
            print(f"[{self.id}] nhận cmd {cmd}")
            self.ack("cmd", True, cmd, j.get("id"))
        elif kind == "config":
            cfg = self.engine.rules.cfg
            for k_src, k_dst in [("th1", "th1"), ("th2", "th2"), ("th3", "th3"), ("slope1", "slope1"),
                                 ("dtemp3", "dtemp3"), ("hyst", "hyst"), ("debounce_up", "debounce_up"),
                                 ("debounce_down", "debounce_down")]:
                if k_src in j:
                    setattr(cfg, k_dst, type(getattr(cfg, k_dst))(j[k_src]))
            if "telemetry_ms" in j:
                self.telemetry_ms = int(j["telemetry_ms"])
            if j.get("mode") in ("rule", "model", "hybrid"):
                self.engine.mode = j["mode"]
            print(f"[{self.id}] áp dụng config v{j.get('version')}")
            self.ack("config", True, f"config v{j.get('version')} applied")
        elif kind == "forecast":
            print(f"[{self.id}] forecast từ cloud: {j.get('summary')}")

    def pub(self, suffix, payload, retain=False, qos=1):
        return self.client.publish(self.prefix + suffix, json.dumps(payload, ensure_ascii=False), qos=qos, retain=retain)

    def status(self):
        self.pub("status", {"state": "online", "device_id": self.id, "ts": int(time.time()), "rssi": -55 - random.randint(0, 15),
                            "uptime_s": int(time.time() - self.t0), "free_heap": 180000 - random.randint(0, 3000),
                            "fw": "sim-1.0.0", "model_ver": self.model_ver}, retain=True)

    def telemetry(self, ts, T, H, P, lux, rain, gas, level, score):
        self.seq += 1
        p_station = P / sea_level_pressure(1.0, T, 8.0)
        self.pub("telemetry", {
            "device_id": self.id, "ts": int(ts), "seq": self.seq, "temp_dht": round(T, 2), "hum": round(H, 1),
            "temp_bmp": round(T + 0.4, 2), "pressure": round(p_station, 2), "pressure_msl": round(P, 2),
            "lux": round(lux, 1), "dew_point": round(float(dew_point(T, H)), 2),
            "heat_index": round(float(heat_index(T, H)), 2), "rain_raw": 3000 - 700 * rain, "rain_level": rain,
            "gas_raw": None, "gas_rs_r0": round(gas["rs_r0"], 3), "gas_ppm": round(gas["gas_ppm"], 1),
            "gas_slope": round(float(gas.get("slope", 0)), 2), "edge_risk": level, "edge_score": round(score, 3),
            "fw": "sim-1.0.0", "model_ver": self.model_ver, "t_pub_ms": int(time.time() * 1000)}, qos=0)

    def backfill(self, hours):
        """Lịch sử thời tiết (1 mẫu/10 phút), khí sạch — để forecast service có ≥ 30 giờ dữ liệu."""
        now = time.time()
        n = int(hours * 6)
        for i in range(n):
            ts = now - (n - i) * 600
            T, H, P, lux, rain = self.weather.at(ts)
            self.telemetry(ts, T, H, P, lux, rain, {"gas_ppm": 4.0 + random.random(), "rs_r0": 9.6}, 0, 0.01)
            if i % 50 == 0:
                time.sleep(0.05)
        print(f"[{self.id}] đã gửi {n} bản ghi lịch sử ({hours} giờ)")

    def next_gas(self, elapsed):
        if self.events and elapsed >= self.events[0][0]:
            _, kind = self.events.pop(0)
            rows, _ = self.mq2.session(kind)
            self.gas_queue = rows  # bắt đầu kịch bản ngay, bỏ phần khí sạch đang chờ
            print(f"[{self.id}] >>> bắt đầu kịch bản '{kind}' ({len(rows)} s)")
        if not self.gas_queue:
            rows, _ = self.mq2.session("clean")
            self.gas_queue.extend(rows)
        return self.gas_queue.pop(0)

    def run(self, stop: threading.Event):
        self.client.connect(self.a.host, self.a.port, keepalive=15)
        self.client.loop_start()
        time.sleep(0.5)
        if self.a.backfill_hours:
            self.backfill(self.a.backfill_hours)
        last_tel = last_status = 0.0
        tick = 1.0 / self.a.speed
        while not stop.is_set():
            now = time.time()
            elapsed = (now - self.t0) * self.a.speed
            g = self.next_gas(elapsed)
            T, H, P, lux, rain = self.weather.at(now)
            # môi trường quanh cảm biến khí lấy từ kịch bản (khói/hơi nước làm đổi T/H/lux cục bộ)
            level, rl, ml, score, f = self.engine.step(g["gas_ppm"], g["rs_r0"], g["temp"], g["hum"], g["lux"])
            if now < self.cloud_until:
                level = max(level, self.cloud_level)
            if now < self.test_until:
                level = 3
            if level != self.level:
                cause = []
                c = self.engine.rules.cfg
                if f[0] >= c.th1: cause.append(f"gas_ppm>{c.th1:g}")
                if f[2] >= c.slope1: cause.append("slope_high")
                if f[0] >= c.th2: cause.append(f"gas_ppm>{c.th2:g}")
                if f[0] >= c.th3: cause.append(f"gas_ppm>{c.th3:g}")
                if ml > rl: cause.append("model")
                self.seq += 1
                action = {0: ["led_green"], 1: ["led_yellow"], 2: ["led_red_blink", "buzzer_intermittent", "fan_on"],
                          3: ["led_red_solid", "buzzer_continuous", "fan_on"]}[level]
                if now < self.muted_until:
                    action = [a for a in action if not a.startswith("buzzer")]
                self.pub("alert", {"device_id": self.id, "ts": int(now), "seq": self.seq, "type": "gas", "level": level,
                                   "prev_level": self.level, "level_name": LEVEL_NAME[level], "cause": cause,
                                   "gas_ppm": round(float(f[0]), 1), "score": round(score, 3), "rule_level": rl,
                                   "model_level": ml, "action": action, "t_pub_ms": int(now * 1000)})
                print(f"[{self.id}] CẢNH BÁO {self.level} -> {level} ({LEVEL_NAME[level]}) ppm={f[0]:.0f} "
                      f"rule={rl} model={ml} score={score:.2f}")
                self.level = level
            period = 1.0 if level >= 1 else self.telemetry_ms / 1000
            if now - last_tel >= period / self.a.speed:
                last_tel = now
                self.telemetry(now, T, H, P, lux, rain, {**g, "slope": f[2]}, level, score)
            if now - last_status >= 60:
                last_status = now
                self.status()
            stop.wait(tick)
        self.client.loop_stop()
        self.client.disconnect()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--user", default=None, help="mặc định = device_id")
    ap.add_argument("--password", default="change-me")
    ap.add_argument("--devices", type=int, default=1)
    ap.add_argument("--device-prefix", default="station")
    ap.add_argument("--period", type=float, default=10.0, help="chu kỳ telemetry khi bình thường (s)")
    ap.add_argument("--events", default="", help='"giây:kịch_bản,..." ví dụ "30:lpg_mid,300:smoke"')
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--backfill-hours", type=float, default=0)
    ap.add_argument("--duration", type=float, default=0, help="giây, 0 = chạy mãi")
    a = ap.parse_args()
    model, ver = load_edge_model()
    stop = threading.Event()
    devs = [SimDevice(f"{a.device_prefix}{i + 1:02d}", a, model, ver, i) for i in range(a.devices)]
    threads = [threading.Thread(target=d.run, args=(stop,), daemon=True) for d in devs]
    for t in threads:
        t.start()
    try:
        if a.duration:
            time.sleep(a.duration)
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    stop.set()
    for t in threads:
        t.join(timeout=3)


if __name__ == "__main__":
    main()
