from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass

import numpy as np

LEVEL_NAMES = ["Normal", "Advisory", "Warning", "Danger"]

MQ2_A, MQ2_B = 574.25, -2.222
MQ2_CLEAN_AIR_RATIO = 9.83


def ppm_from_ratio(ratio):
    return MQ2_A * np.power(np.maximum(ratio, 1e-3), MQ2_B)


def ratio_from_ppm(ppm):
    return np.power(np.maximum(ppm, 1e-6) / MQ2_A, 1.0 / MQ2_B)


def _slope(buf):
    n = len(buf)
    if n < 2:
        return 0.0
    y = np.fromiter(buf, dtype=float, count=n)
    t = np.arange(n, dtype=float)
    tc = t - t.mean()
    return float(np.dot(tc, y - y.mean()) / np.dot(tc, tc))


class GasTrend:
    """Bản tham chiếu của firmware/src/edge_gas.py: độ dốc ppm 10 mẫu và tốc độ tăng nhiệt độ (°C/phút, 60 mẫu)."""

    def __init__(self):
        self.ppm = deque(maxlen=10)
        self.temp = deque(maxlen=60)

    def update(self, ppm, temp):
        self.ppm.append(ppm)
        self.temp.append(temp)
        return _slope(self.ppm), _slope(self.temp) * 60.0


@dataclass
class RuleConfig:
    th1: float = 300.0
    th2: float = 1000.0
    th3: float = 2000.0
    slope1: float = 15.0
    dtemp3: float = 1.0
    hyst: float = 0.15
    debounce_up: int = 3
    debounce_down: int = 5


class RuleEngine:
    def __init__(self, cfg: RuleConfig | None = None):
        self.cfg = cfg or RuleConfig()
        self.level = 0
        self.up_cnt = 0
        self.down_cnt = 0
        self.cause = []

    def raw_level(self, ppm, slope, dtemp, scale=1.0):
        c = self.cfg
        cause = []
        lvl = 0
        if ppm >= c.th1 * scale:
            lvl, cause = 1, [f"gas_ppm>{c.th1:g}"]
        if slope >= c.slope1 * scale:
            lvl = max(lvl, 1)
            cause.append("slope_high")
        if ppm >= c.th2 * scale:
            lvl = 2
            cause.append(f"gas_ppm>{c.th2:g}")
        if ppm >= c.th3 * scale:
            lvl = 3
            cause.append(f"gas_ppm>{c.th3:g}")
        elif lvl >= 2 and dtemp >= c.dtemp3:
            lvl = 3
            cause.append("temp_rising")
        return lvl, cause

    def update(self, ppm, slope, dtemp):
        c = self.cfg
        up, cause = self.raw_level(ppm, slope, dtemp, 1.0)
        if up > self.level:
            self.down_cnt = 0
            if up == 3:
                self.level, self.up_cnt, self.cause = 3, 0, cause
            else:
                self.up_cnt += 1
                if self.up_cnt >= c.debounce_up:
                    self.level, self.up_cnt, self.cause = up, 0, cause
            return self.level
        self.up_cnt = 0
        down, _ = self.raw_level(ppm, slope, dtemp, 1.0 - c.hyst)
        if down < self.level:
            self.down_cnt += 1
            if self.down_cnt >= c.debounce_down:
                self.level, self.down_cnt = down, 0
                self.cause = [] if down == 0 else self.cause
        else:
            self.down_cnt = 0
        return self.level


class EdgeGas:
    """Cảnh báo khí 4 cấp chỉ bằng luật, giống firmware."""

    def __init__(self, rule_cfg: RuleConfig | None = None, warmup_s=0):
        self.trend = GasTrend()
        self.rules = RuleEngine(rule_cfg)
        self.warmup_s, self.t = warmup_s, 0

    def step(self, ppm, temp):
        self.t += 1
        slope, dtemp = self.trend.update(ppm, temp)
        level = self.rules.update(ppm, slope, dtemp)
        return (0 if self.t <= self.warmup_s else level), slope


def rule_config_dict(cfg: RuleConfig | None = None):
    return asdict(cfg or RuleConfig())
