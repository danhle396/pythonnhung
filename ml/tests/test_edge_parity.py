"""Firmware MicroPython (firmware/src/edge_ai.py, alert.py) và bản tham chiếu NumPy (aiot_ml.gas_edge) phải cho
cùng feature và cùng cấp cảnh báo trên cùng chuỗi đầu vào — model huấn luyện bằng gas_edge mới phản ánh đúng thiết bị."""
import importlib
import sys
from pathlib import Path

import numpy as np

from aiot_ml import gas_edge

FW_SRC = Path(__file__).resolve().parents[2] / "firmware" / "src"


def _firmware():
    sys.path.insert(0, str(FW_SRC))
    try:
        return importlib.import_module("edge_ai"), importlib.import_module("alert")
    finally:
        sys.path.remove(str(FW_SRC))


def _stream(seed, n=600):
    """Chuỗi đầu vào tổng hợp chỉ để so sánh hai bản cài đặt (không dùng để huấn luyện/báo cáo)."""
    rng = np.random.default_rng(seed)
    ppm = np.clip(80 + np.cumsum(rng.normal(0, 25, n)), 0, None)
    ppm[200:260] += np.linspace(0, 2600, 60)  # đoạn tăng nhanh để đi qua mọi cấp
    temp = 28 + np.cumsum(rng.normal(0, 0.02, n))
    hum = 75 + np.cumsum(rng.normal(0, 0.05, n))
    lux = np.abs(300 + np.cumsum(rng.normal(0, 3, n)))
    rs = gas_edge.ratio_from_ppm(ppm)
    return ppm, rs, temp, hum, lux


def test_features_and_rule_levels_identical():
    edge_ai, alert = _firmware()
    for seed in range(3):
        ppm, rs, temp, hum, lux = _stream(seed)
        fx_ref, fx_fw = gas_edge.FeatureExtractor(), edge_ai.FeatureExtractor()
        re_ref, re_fw = gas_edge.RuleEngine(), alert.RuleEngine()
        levels = set()
        for i in range(len(ppm)):
            a = fx_ref.update(ppm[i], rs[i], temp[i], hum[i], lux[i])
            b = np.array(fx_fw.update(float(ppm[i]), float(rs[i]), float(temp[i]), float(hum[i]), float(lux[i])))
            np.testing.assert_allclose(a, b, rtol=1e-9, atol=1e-9)
            la = re_ref.update(a[0], a[2], a[6])
            lb = re_fw.update(b[0], b[2], b[6])
            assert la == lb, (seed, i)
            levels.add(la)
        assert levels == {0, 1, 2, 3}


def test_rule_config_defaults_identical():
    _, alert = _firmware()
    ref, fw = gas_edge.RuleConfig(), alert.RuleConfig()
    for k in ("th1", "th2", "th3", "slope1", "dtemp3", "hyst", "debounce_up", "debounce_down"):
        assert getattr(ref, k) == getattr(fw, k), k
