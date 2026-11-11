"""Bản tham chiếu Python cho logic Edge AI cảnh báo khí/khói — firmware/src/edge_ai.cpp và alert.cpp
cài đặt Y HỆT các công thức dưới đây (cùng tên biến, cùng thứ tự feature).

MQ-2:  Rs = RL·(Vc − Vout)/Vout,  ratio = Rs/R0,  ppm(LPG) = A·ratio^B  (A = 574.25, B = −2.222)
Feature (lấy mẫu 1 Hz):
    x0 gas_ppm   : ppm sau lọc median-5 + EWMA
    x1 rs_r0     : Rs/R0
    x2 slope10   : độ dốc bình phương tối thiểu của ppm trong 10 s gần nhất (ppm/s)
    x3 std30     : độ lệch chuẩn ppm trong 30 s
    x4 dev_base  : ppm − baseline động (baseline EWMA α=0.005, chỉ cập nhật khi |ppm − baseline| < 100)
    x5 temp      : nhiệt độ (°C)
    x6 dtemp_min : độ dốc nhiệt độ trong 60 s (°C/phút)
    x7 hum       : độ ẩm (%)
    x8 dhum_min  : độ dốc độ ẩm trong 60 s (%/phút)
    x9 lux_rel   : (lux − lux_base) / (lux_base + 10), lux_base = EWMA α=0.005, chỉ cập nhật khi |lux_rel| < 0.08
                   (khói che sáng làm lux giảm so với nền chậm; nền không bị kéo theo khi đang có khói)
Rule engine 4 cấp với hysteresis & debounce; fusion: level = max(rule_level, model_level)
(model không bao giờ hạ cấp do rule đưa ra). Không có model (chưa có dữ liệu đo thật để huấn luyện,
GAS_MODEL_AVAILABLE = 0 trong firmware) -> mọi chế độ đều chạy như 'rule'.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass

import numpy as np

EDGE_FEATURES = ["gas_ppm", "rs_r0", "slope10", "std30", "dev_base", "temp", "dtemp_min", "hum",
                 "dhum_min", "lux_rel"]
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


class FeatureExtractor:
    def __init__(self):
        self.ppm = deque(maxlen=30)
        self.temp = deque(maxlen=60)
        self.hum = deque(maxlen=60)
        self.baseline = None
        self.lux_base = None

    def update(self, ppm, rs_r0, temp, hum, lux):
        self.ppm.append(ppm)
        self.temp.append(temp)
        self.hum.append(hum)
        if self.lux_base is None:
            self.lux_base = lux
        lux_rel = (lux - self.lux_base) / (self.lux_base + 10.0)
        if abs(lux_rel) < 0.08:
            self.lux_base += 0.005 * (lux - self.lux_base)
        if self.baseline is None:
            self.baseline = ppm
        elif abs(ppm - self.baseline) < 100.0:
            self.baseline += 0.005 * (ppm - self.baseline)
        last10 = list(self.ppm)[-10:]
        return np.array([
            ppm, rs_r0, _slope(last10), float(np.std(self.ppm)), ppm - self.baseline,
            temp, _slope(self.temp) * 60.0, hum, _slope(self.hum) * 60.0, lux_rel])


@dataclass
class RuleConfig:
    th1: float = 300.0      # ppm: Advisory
    th2: float = 1000.0     # ppm: Warning
    th3: float = 2000.0     # ppm: Danger (≈10% LEL của LPG)
    slope1: float = 15.0    # ppm/s: tăng bất thường -> Advisory
    dtemp3: float = 1.0     # °C/phút: Warning + nhiệt tăng nhanh -> Danger
    hyst: float = 0.15      # phải xuống dưới ngưỡng·(1 − hyst) mới hạ cấp
    debounce_up: int = 3    # số mẫu liên tiếp để tăng cấp (cấp 3 tăng ngay)
    debounce_down: int = 5  # số mẫu liên tiếp để hạ cấp


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


class ModelLevelFilter:
    """Debounce cho đầu ra model: tăng cấp khi model dự đoán ≥ cấp đó N mẫu liên tiếp, hạ cấp sau M mẫu."""

    def __init__(self, n_up=3, n_down=5):
        self.n_up, self.n_down = n_up, n_down
        self.level, self.up_cnt, self.down_cnt = 0, 0, 0
        self.cand = 0

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


class EdgeEngine:
    """Bản Python của toàn bộ chuỗi xử lý tại ESP32. mode: 'rule' | 'model' | 'hybrid' ('rule' nếu model=None)."""

    def __init__(self, model=None, mode="hybrid", rule_cfg: RuleConfig | None = None, warmup_s=0):
        self.fx = FeatureExtractor()
        self.rules = RuleEngine(rule_cfg)
        self.mfilter = ModelLevelFilter()
        self.model, self.mode = model, (mode if model is not None else "rule")
        self.warmup_s, self.t = warmup_s, 0

    def step(self, ppm, rs_r0, temp, hum, lux):
        self.t += 1
        f = self.fx.update(ppm, rs_r0, temp, hum, lux)
        rl = self.rules.update(f[0], f[2], f[6])
        ml, score = 0, 0.0
        if self.model is not None and self.mode != "rule":
            p = self.model.predict_proba(f.reshape(1, -1))[0]
            ml = self.mfilter.update(int(self.model.classes_[int(np.argmax(p))]))
            score = float(1.0 - p[0])
        if self.t <= self.warmup_s:
            return 0, rl, ml, score, f
        level = {"rule": rl, "model": ml, "hybrid": max(rl, ml)}[self.mode]
        return level, rl, ml, score, f


def extract_features_stream(df):
    """Tính feature cho cả chuỗi (DataFrame 1 Hz có gas_ppm, rs_r0, temp, hum, lux)."""
    fx = FeatureExtractor()
    cols = [df[c].to_numpy(dtype=float) for c in ["gas_ppm", "rs_r0", "temp", "hum", "lux"]]
    return np.vstack([fx.update(*vals) for vals in zip(*cols)])


def run_levels_vectorized(F, model_classes_pred, mode, rule_cfg=None):
    """Chạy rule engine + debounce model trên ma trận feature đã tính sẵn (nhanh hơn EdgeEngine)."""
    rules = RuleEngine(rule_cfg)
    mf = ModelLevelFilter()
    out = np.zeros(len(F), dtype=int)
    rl_all = np.zeros(len(F), dtype=int)
    for i in range(len(F)):
        rl = rules.update(F[i, 0], F[i, 2], F[i, 6])
        ml = mf.update(int(model_classes_pred[i])) if model_classes_pred is not None else 0
        rl_all[i] = rl
        out[i] = rl if mode == "rule" else (ml if mode == "model" else max(rl, ml))
    return out, rl_all


def rule_config_dict(cfg: RuleConfig | None = None):
    return asdict(cfg or RuleConfig())
