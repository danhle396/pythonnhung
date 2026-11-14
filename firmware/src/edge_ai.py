import math

import gas_model
from alert import CAUSE_MODEL, RuleEngine
from compat import ticks_diff, ticks_us
from filters import RingBuffer

N_FEATURES = 10
MODE_RULE, MODE_MODEL, MODE_HYBRID = 0, 1, 2
MODE_NAMES = ("rule", "model", "hybrid")

FAULT_NONE, FAULT_STUCK, FAULT_DISCONNECTED, FAULT_SATURATED = 0, 1, 2, 3

if gas_model.N_FEATURES != N_FEATURES:
    raise ValueError("gas_model.py không khớp số feature của edge_ai")


class Mq2Params:
    def __init__(self, rl_kohm=5.0, vc=5.0, divider=2.0 / 3.0, r0_kohm=10.0, curve_a=574.25, curve_b=-2.222):
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


class FeatureExtractor:
    def __init__(self):
        self.ppm = RingBuffer(30)
        self.temp = RingBuffer(60)
        self.hum = RingBuffer(60)
        self.init = False
        self.lux_init = False
        self.baseline = 0.0
        self.lux_base = 0.0
        self.f = [0.0] * N_FEATURES

    def update(self, ppm, rs_r0, temp, hum, lux):
        self.ppm.push(ppm)
        self.temp.push(temp)
        self.hum.push(hum)
        if not self.lux_init:
            self.lux_base = lux
            self.lux_init = True
        lux_rel = (lux - self.lux_base) / (self.lux_base + 10.0)
        if abs(lux_rel) < 0.08:
            self.lux_base += 0.005 * (lux - self.lux_base)
        if not self.init:
            self.baseline = ppm
            self.init = True
        elif abs(ppm - self.baseline) < 100.0:
            self.baseline += 0.005 * (ppm - self.baseline)
        f = self.f
        f[0] = ppm
        f[1] = rs_r0
        f[2] = self.ppm.slope(10)
        f[3] = self.ppm.stdev()
        f[4] = ppm - self.baseline
        f[5] = temp
        f[6] = self.temp.slope() * 60.0
        f[7] = hum
        f[8] = self.hum.slope() * 60.0
        f[9] = lux_rel
        return f


class ModelLevelFilter:

    def __init__(self, n_up=3, n_down=5):
        self.n_up, self.n_down = n_up, n_down
        self.level = self.up_cnt = self.down_cnt = self.cand = 0

    def update(self, raw):
        if raw > self.level:
            self.down_cnt = 0
            self.cand = raw if self.up_cnt == 0 else min(self.cand, raw)
            self.up_cnt += 1
            if self.up_cnt >= self.n_up:
                self.level, self.up_cnt = self.cand, 0
        elif raw < self.level:
            self.up_cnt = 0
            self.down_cnt += 1
            if self.down_cnt >= self.n_down:
                self.level, self.down_cnt = raw, 0
        else:
            self.up_cnt = self.down_cnt = 0
        return self.level


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
        self.rule_level = 0
        self.model_level = 0
        self.score = 0.0
        self.cause = 0
        self.warming_up = True
        self.f = None


class EdgeAI:
    def __init__(self, rules=None, mode=MODE_HYBRID, warmup_samples=60, model=gas_model):
        self.rules = rules or RuleEngine()
        self.mode = mode
        self.warmup_samples = warmup_samples
        self.model = model
        self.fx = FeatureExtractor()
        self.mf = ModelLevelFilter()
        self.t = 0
        self.last_inference_us = 0

    def step(self, ppm, rs_r0, temp, hum, lux, gas_ok=True):
        o = EdgeOutput()
        self.t += 1
        f = self.fx.update(ppm, rs_r0, temp, hum, lux)
        o.f = f
        o.rule_level = self.rules.update(f[0], f[2], f[6])
        o.cause = self.rules.cause
        m = self.mode if self.model.AVAILABLE else MODE_RULE
        if m != MODE_RULE:
            t0 = ticks_us()
            k, p = self.model.predict_proba(f)
            self.last_inference_us = ticks_diff(ticks_us(), t0)
            o.model_level = self.mf.update(self.model.CLASS_LABEL[k])
            o.score = 1.0 - p[0]
        o.warming_up = self.t <= self.warmup_samples or not gas_ok
        if o.warming_up:
            o.level = 0
            return o
        if m == MODE_RULE:
            o.level = o.rule_level
        elif m == MODE_MODEL:
            o.level = o.model_level
        else:
            o.level = max(o.rule_level, o.model_level)
        if o.model_level > o.rule_level and m != MODE_RULE:
            o.cause |= CAUSE_MODEL
        return o
