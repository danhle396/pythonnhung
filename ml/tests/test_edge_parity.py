import importlib
import sys
from pathlib import Path

import numpy as np

from aiot_ml import gas_edge

FW_SRC = Path(__file__).resolve().parents[2] / "firmware" / "src"


def _firmware():
    sys.path.insert(0, str(FW_SRC))
    try:
        return importlib.import_module("edge_gas"), importlib.import_module("alert")
    finally:
        sys.path.remove(str(FW_SRC))


def _stream(seed, n=600):
    rng = np.random.default_rng(seed)
    ppm = np.clip(80 + np.cumsum(rng.normal(0, 25, n)), 0, None)
    ppm[200:260] += np.linspace(0, 2600, 60)
    temp = 28 + np.cumsum(rng.normal(0, 0.02, n))
    hum = 75 + np.cumsum(rng.normal(0, 0.05, n))
    lux = np.abs(300 + np.cumsum(rng.normal(0, 3, n)))
    rs = gas_edge.ratio_from_ppm(ppm)
    return ppm, rs, temp, hum, lux


def test_trend_and_rule_levels_identical():
    edge_gas, alert = _firmware()
    for seed in range(3):
        ppm, rs, temp, hum, lux = _stream(seed)
        tr_ref, tr_fw = gas_edge.GasTrend(), edge_gas.GasTrend()
        re_ref, re_fw = gas_edge.RuleEngine(), alert.RuleEngine()
        levels = set()
        for i in range(len(ppm)):
            a = tr_ref.update(ppm[i], temp[i])
            b = tr_fw.update(float(ppm[i]), float(temp[i]))
            np.testing.assert_allclose(a, b, rtol=1e-9, atol=1e-9)
            la = re_ref.update(ppm[i], a[0], a[1])
            lb = re_fw.update(float(ppm[i]), b[0], b[1])
            assert la == lb, (seed, i)
            levels.add(la)
        assert levels == {0, 1, 2, 3}


def test_rule_config_defaults_identical():
    _, alert = _firmware()
    ref, fw = gas_edge.RuleConfig(), alert.RuleConfig()
    for k in ("th1", "th2", "th3", "slope1", "dtemp3", "hyst", "debounce_up", "debounce_down"):
        assert getattr(ref, k) == getattr(fw, k), k
