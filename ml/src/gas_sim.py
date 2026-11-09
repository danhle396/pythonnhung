"""Bộ mô phỏng vật lý cảm biến MQ-2 + môi trường, sinh dữ liệu có nhãn cho kịch bản khí/khói.

⚠ DỮ LIỆU MÔ PHỎNG — chỉ dùng để phát triển pipeline khi chưa có MQ-2 thật. Khi đã thu dữ liệu thật
bằng tools/label_logger.py (cùng định dạng CSV), chạy train_gas_edge.py với --data <csv thật>.

Mô hình hoá:
  - Nồng độ thật c(t): khi nguồn bật, c tiến tới mức đích với τ = 5 s, nhân nhiễu rối log-normal AR(1);
    khi tắt nguồn, c giảm dần với τ = 20 s.
  - Đáp ứng cảm biến (MOS) bậc 1: τ_tăng = 6 s, τ_giảm = 15 s.
  - Ảnh hưởng nhiệt/ẩm lên Rs: Rs/Rs(20°C, 65%) ≈ 1 − 0.008·(T − 20) − 0.003·(RH − 65).
  - Firmware KHÔNG bù nhiệt ẩm ⇒ ppm "biểu kiến" lệch theo T/H — model học bù qua feature temp/hum.
  - Chuỗi tín hiệu: ppm → Rs/R0 → Vout = Vc·RL/(Rs + RL) → phân áp 2/3 → ADC (nhiễu 4 mV, lượng tử 1 mV)
    → firmware tính ngược Rs/R0 và ppm.
Kịch bản (nhãn = cấp cảnh báo đúng):
  clean 0 | lpg_far (50 cm) 1 | lpg_mid (20 cm) 2 | lpg_near (5 cm) 3 | slow_leak 1
  smoke (nhang/giấy trong hộp) 2 | smoke_fire (khói + nhiệt tăng nhanh) 3
  steam 0 | alcohol 0 | perfume 0   (nhiễu, dùng để đo báo động giả)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .gas_edge import MQ2_CLEAN_AIR_RATIO, ppm_from_ratio, ratio_from_ppm

SCENARIOS = {
    #  tên         nhãn  (ppm đích min, max)  thời lượng nguồn (s)
    "clean":      (0, (0, 0), (60, 180)),
    "lpg_far":    (1, (380, 850), (30, 120)),
    "lpg_mid":    (2, (1150, 1900), (30, 90)),
    "lpg_near":   (3, (2400, 6000), (15, 60)),
    "slow_leak":  (1, (450, 900), (180, 400)),
    "smoke":      (2, (220, 800), (60, 180)),
    "smoke_fire": (3, (400, 1400), (60, 150)),
    "steam":      (0, (40, 200), (40, 120)),
    "alcohol":    (0, (300, 850), (20, 60)),
    "perfume":    (0, (150, 500), (5, 15)),
}
DEFAULT_MIX = {"clean": 0.22, "lpg_far": 0.1, "lpg_mid": 0.1, "lpg_near": 0.07, "slow_leak": 0.06,
               "smoke": 0.1, "smoke_fire": 0.06, "steam": 0.1, "alcohol": 0.1, "perfume": 0.09}

RL_KOHM, VC = 5.0, 5.0       # điện trở tải module MQ-2 (5 kΩ), nguồn 5 V
DIVIDER = 2.0 / 3.0          # cầu phân áp 10k/20k


class Mq2Simulator:
    def __init__(self, seed=0, r0_kohm=10.0):
        self.rng = np.random.default_rng(seed)
        self.r0 = r0_kohm
        self.c_true = 0.0
        self.c_sens = 0.0
        self.turb = 0.0
        self.T = float(self.rng.uniform(24, 32))
        self.H = float(self.rng.uniform(60, 90))
        self.lux = float(self.rng.choice([30.0, 300.0, 800.0]))  # trong hộp / trong nhà / gần cửa sổ
        self.t = 0

    def _sensor_reading(self, extra_ppm):
        """Trả về (ppm biểu kiến, Rs/R0) như firmware tính từ ADC."""
        f_th = 1 - 0.008 * (self.T - 20) - 0.003 * (self.H - 65)
        clean_ppm = ppm_from_ratio(MQ2_CLEAN_AIR_RATIO)
        ratio = ratio_from_ppm(clean_ppm + max(extra_ppm, 0.0)) * f_th
        rs = ratio * self.r0
        vout = VC * RL_KOHM / (rs + RL_KOHM)
        adc_mv = np.round(vout * DIVIDER * 1000 + self.rng.normal(0, 4.0))
        vout_meas = max(adc_mv, 1.0) / 1000 / DIVIDER
        rs_meas = RL_KOHM * (VC - vout_meas) / vout_meas
        r = rs_meas / self.r0
        return float(ppm_from_ratio(r)), float(r)

    def session(self, kind, label_override=None):
        """Sinh 1 phiên: tiền sự kiện sạch → nguồn bật → nguồn tắt và phân rã. Trả về list dict 1 Hz."""
        rng = self.rng
        label, (lo, hi), (dmin, dmax) = SCENARIOS[kind]
        label = label if label_override is None else label_override
        pre = int(rng.integers(30, 90))
        dur = int(rng.integers(dmin, dmax + 1))
        post = int(rng.integers(60, 150))
        target = float(rng.uniform(lo, hi)) if hi > 0 else 0.0
        dT_total = {"steam": rng.uniform(1.0, 3.0), "smoke": rng.uniform(0.2, 1.2),
                    "smoke_fire": rng.uniform(2.0, 5.0)}.get(kind, 0.0)
        dH_target = {"steam": rng.uniform(92, 99)}.get(kind)
        lux_drop = {"smoke": rng.uniform(0.1, 0.4), "smoke_fire": rng.uniform(0.15, 0.5)}.get(kind, 0.0)
        T0, H0, L0 = self.T, self.H, self.lux
        rows = []
        peak = 1e-9
        for k in range(pre + dur + post):
            on = pre <= k < pre + dur
            # --- nồng độ thật
            if kind == "slow_leak" and on:
                goal = target * (k - pre) / dur
                self.c_true += (goal - self.c_true) / 5.0
            elif kind == "perfume" and on:
                self.c_true += (target - self.c_true) / 2.0
            elif on:
                self.c_true += (target - self.c_true) / 5.0
            else:
                self.c_true += (0.0 - self.c_true) / 20.0
            self.turb = 0.85 * self.turb + rng.normal(0, 0.06)
            c_eff = self.c_true * float(np.exp(self.turb)) if kind not in ("clean",) else 0.0
            # --- đáp ứng cảm biến
            tau = 6.0 if c_eff > self.c_sens else 15.0
            self.c_sens += (c_eff - self.c_sens) / tau
            # --- môi trường
            prog = min(max((k - pre) / max(dur, 1), 0.0), 1.0) if k >= pre else 0.0
            if dT_total and on:
                self.T = T0 + dT_total * prog
            elif dT_total and k >= pre + dur:
                self.T += (T0 - self.T) / 120.0
            if dH_target is not None and on:
                self.H += (dH_target - self.H) / 10.0
            elif dH_target is not None and k >= pre + dur:
                self.H += (H0 - self.H) / 60.0
            lux = L0 * (1 - lux_drop * (self.c_true / max(target, 1.0))) if lux_drop else L0
            lux = max(lux * (1 + rng.normal(0, 0.01)), 0.0)
            T_meas = self.T + rng.normal(0, 0.05)
            H_meas = float(np.clip(self.H + rng.normal(0, 0.3), 0, 100))
            ppm, ratio = self._sensor_reading(self.c_sens)
            if k >= pre:
                peak = max(peak, self.c_true)
            # nhãn: như người thao tác giữ phím từ lúc mở nguồn đến khi khí giảm còn < 40% đỉnh
            active = on or (k >= pre and label > 0 and self.c_true > 0.4 * peak and target > 0)
            rows.append({"t": self.t, "gas_ppm": ppm, "rs_r0": ratio, "temp": T_meas, "hum": H_meas, "lux": lux,
                         "label": label if (active and label > 0) else 0, "scenario": kind,
                         "event_active": int(on)})
            self.t += 1
        # trôi chậm điều kiện nền giữa các phiên
        self.T = float(np.clip(self.T + rng.normal(0, 0.4), 20, 38))
        self.H = float(np.clip(self.H + rng.normal(0, 2.0), 40, 98))
        self.lux = float(max(self.lux * np.exp(rng.normal(0, 0.1)), 5))
        return rows, (pre, dur, post, target)


def generate_stream(n_sessions, seed, mix=None):
    """Chuỗi liên tục gồm nhiều phiên nối tiếp (giống thiết bị chạy thật), kèm id sự kiện."""
    mix = mix or DEFAULT_MIX
    sim = Mq2Simulator(seed=seed)
    kinds = list(mix)
    p = np.array([mix[k] for k in kinds])
    p = p / p.sum()
    rows = []
    for s in range(n_sessions):
        kind = kinds[int(sim.rng.choice(len(kinds), p=p))]
        r, _ = sim.session(kind)
        for x in r:
            x["event_id"] = s
        rows.extend(r)
    df = pd.DataFrame(rows)
    df["stream_seed"] = seed
    return df


def generate_long_term(days=30, seed=0, leak_days=(), drift_start_day=None, drift_per_day=0.004, step_s=60):
    """Chuỗi dài hạn (1 mẫu/phút) cho cloud anomaly: chu kỳ ngày của T/H, ppm nền,
    rò rỉ chậm cài vào các ngày `leak_days`, và trôi R0 (lão hoá) từ `drift_start_day`."""
    rng = np.random.default_rng(seed)
    n = int(days * 86400 / step_s)
    t = np.arange(n) * step_s
    hours = (t / 3600.0) % 24
    day = t / 86400.0
    T = 27 + 3.5 * np.sin(2 * np.pi * (hours - 9) / 24) + rng.normal(0, 0.15, n)
    H = 80 - 10 * np.sin(2 * np.pi * (hours - 9) / 24) + rng.normal(0, 0.8, n)
    # hoạt động nấu ăn buổi sáng/trưa/tối tạo nền ppm nhỏ có tính chu kỳ (bình thường)
    cook = sum(np.exp(-0.5 * ((hours - c) / 0.4) ** 2) * a for c, a in [(6.5, 40), (11.3, 60), (18.2, 80)])
    extra = cook * (0.7 + 0.6 * rng.random(n))
    leak = np.zeros(n)
    leak_mask = np.zeros(n, dtype=bool)
    for d in leak_days:
        start = rng.uniform(d + 0.05, d + 0.6)
        dur_h = rng.uniform(1.5, 4.0)
        amp = rng.uniform(60, 220)
        m = (day >= start) & (day < start + dur_h / 24)
        leak[m] = amp * (day[m] - start) / (dur_h / 24)
        leak_mask |= m
    r0_factor = np.ones(n)
    if drift_start_day is not None:
        r0_factor = np.where(day >= drift_start_day, 1 - drift_per_day * (day - drift_start_day), 1.0)
    f_th = 1 - 0.008 * (T - 20) - 0.003 * (H - 65)
    clean_ppm = ppm_from_ratio(MQ2_CLEAN_AIR_RATIO)
    ratio = ratio_from_ppm(clean_ppm + extra + leak) * f_th * r0_factor * np.exp(rng.normal(0, 0.01, n))
    ppm = ppm_from_ratio(ratio)
    ts = pd.Timestamp("2026-11-01", tz="Asia/Ho_Chi_Minh") + pd.to_timedelta(t, unit="s")
    return pd.DataFrame({"ts": ts, "gas_ppm": ppm, "rs_r0": ratio, "temp": T, "hum": H,
                         "leak": leak_mask.astype(int), "r0_factor": r0_factor})
