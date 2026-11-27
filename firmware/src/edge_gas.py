import math

from alert import RuleEngine
from filters import RingBuffer

FAULT_NONE, FAULT_STUCK, FAULT_DISCONNECTED, FAULT_SATURATED = 0, 1, 2, 3


class Mq2Params:
    def __init__(self, rl_kohm=5.0, vc=5.0, divider=1.0, r0_kohm=10.0, curve_a=574.25, curve_b=-2.222):
        self.rl_kohm, self.vc, self.divider, self.r0_kohm = rl_kohm, vc, divider, r0_kohm
        self.curve_a, self.curve_b = curve_a, curve_b


class Mq2Reading:
    def __init__(self, vout=0.0, rs=0.0, ratio=0.0, ppm=0.0):
        self.vout, self.rs, self.ratio, self.ppm = vout, rs, ratio, ppm


def mq2_convert(adc_mv, p):
    v = adc_mv / 1000.0 / p.divider
    if v < 0.001:
        v = 0.001
    if v > p.vc - 0.001:
        v = p.vc - 0.001
    rs = p.rl_kohm * (p.vc - v) / v
    ratio = rs / p.r0_kohm
    if ratio < 1e-3:
        ratio = 1e-3
    ppm = p.curve_a * math.pow(ratio, p.curve_b)
    return Mq2Reading(v, rs, ratio, ppm)


def mq2_calibrate_r0(rs_clean_kohm, clean_air_ratio=9.83):
    return rs_clean_kohm / clean_air_ratio


class GasTrend:
    """Đầu vào của luật: độ dốc ppm trên 10 mẫu gần nhất (ppm/mẫu) và tốc độ tăng nhiệt độ (°C/phút, 60 mẫu)."""

    def __init__(self):
        self.ppm = RingBuffer(10)
        self.temp = RingBuffer(60)
        self.slope = 0.0
        self.dtemp = 0.0

    def update(self, ppm, temp):
        self.ppm.push(ppm)
        self.temp.push(temp)
        self.slope = self.ppm.slope()
        self.dtemp = self.temp.slope() * 60.0
        return self.slope, self.dtemp


class Mq2FaultDetector:

    def __init__(self):
        self.last = -1.0
        self.same = self.low = self.high = 0
        self.fault = FAULT_NONE

    def update(self, mv):
        self.same = self.same + 1 if (self.last >= 0 and abs(mv - self.last) < 0.5) else 0
        self.last = mv
        self.low = self.low + 1 if mv < 5.0 else 0
        self.high = self.high + 1 if mv > 3250.0 else 0
        if self.low >= 5:
            self.fault = FAULT_DISCONNECTED
        elif self.high >= 5:
            self.fault = FAULT_SATURATED
        elif self.same >= 300:
            self.fault = FAULT_STUCK
        else:
            self.fault = FAULT_NONE
        return self.fault


class EdgeOutput:
    def __init__(self):
        self.level = 0
        self.cause = 0
        self.slope = 0.0
        self.warming_up = True


class EdgeGas:
    """Cảnh báo khí 4 cấp tại edge chỉ bằng luật (ngưỡng ppm, độ dốc, nhiệt độ tăng + hysteresis + debounce)."""

    def __init__(self, rules=None, warmup_samples=60):
        self.rules = rules or RuleEngine()
        self.warmup_samples = warmup_samples
        self.trend = GasTrend()
        self.t = 0

    def step(self, ppm, temp, gas_ok=True):
        o = EdgeOutput()
        self.t += 1
        slope, dtemp = self.trend.update(ppm, temp)
        o.slope = slope
        level = self.rules.update(ppm, slope, dtemp)
        o.cause = self.rules.cause
        o.warming_up = self.t <= self.warmup_samples or not gas_ok
        o.level = 0 if o.warming_up else level
        return o
