import numpy as np
import pandas as pd
import pytest

from aiot_ml import features as fe
from aiot_ml.gas_edge import EdgeGas, GasTrend, RuleConfig, RuleEngine, ppm_from_ratio, ratio_from_ppm


def _toy_hourly(n=24 * 6, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-11-01", periods=n, freq="1h")
    h = idx.hour.values
    df = pd.DataFrame({"temp": 26 + 3 * np.sin(2 * np.pi * (h - 9) / 24) + rng.normal(0, 0.2, n),
                       "hum": 80 + rng.normal(0, 2, n), "pres": 1010 + rng.normal(0, 0.5, n)}, index=idx)
    df["dew"] = fe.dew_point(df["temp"], df["hum"])
    df["sky"] = 0.5
    df["is_rain"] = (rng.random(n) < 0.3).astype(float)
    return df


def test_features_do_not_use_future():
    df = _toy_hourly()
    F1 = fe.build_features(df)
    df2 = df.copy()
    df2.iloc[100:] += 50.0
    F2 = fe.build_features(df2)
    pd.testing.assert_frame_equal(F1.iloc[:100], F2.iloc[:100])


def test_targets_alignment():
    df = _toy_hourly()
    Y = fe.build_targets(df, [1, 3])
    assert np.isclose(Y["temp_3h"].iloc[10], df["temp"].iloc[13] - df["temp"].iloc[10])
    assert Y["rain_3h"].iloc[10] == df["is_rain"].iloc[11:14].max()
    assert Y["temp_3h"].iloc[-3:].isna().all()


def test_physics_helpers():
    assert abs(fe.dew_point(25.0, 100.0) - 25.0) < 0.01
    assert abs(fe.dew_point(30.0, 70.0) - 23.9) < 0.3
    p0 = fe.sea_level_pressure(1009.0, 28.0, 8.0)
    assert 1009.8 < p0 < 1010.1
    cz = fe.solar_cos_zenith(pd.DatetimeIndex(["2025-06-21 12:30", "2025-06-21 00:30"]))
    assert cz[0] > 0.9 and cz[1] < 0


def test_rule_debounce_up_and_immediate_danger():
    r = RuleEngine(RuleConfig(debounce_up=3))
    assert [r.update(1200, 0, 0) for _ in range(3)] == [0, 0, 2]
    r2 = RuleEngine()
    assert r2.update(2500, 0, 0) == 3


def test_rule_hysteresis_and_debounce_down():
    r = RuleEngine(RuleConfig(debounce_up=1, debounce_down=3, hyst=0.15))
    assert r.update(1100, 0, 0) == 2
    assert [r.update(950, 0, 0) for _ in range(5)] == [2] * 5
    assert [r.update(800, 0, 0) for _ in range(3)] == [2, 2, 1]


def test_rule_spike_does_not_trigger():
    r = RuleEngine()
    seq = [10, 10, 1500, 10, 10, 1500, 10]
    assert max(r.update(p, 0, 0) for p in seq) == 0


def test_rule_temp_rising_escalates_to_danger():
    r = RuleEngine(RuleConfig(debounce_up=1))
    assert r.update(1200, 0, 0.2) == 2
    assert r.update(1200, 0, 1.5) == 3


def test_edge_gas_rule_only_with_warmup():
    eng = EdgeGas(rule_cfg=RuleConfig(debounce_up=1), warmup_s=2)
    lv = [eng.step(2500, 28)[0] for _ in range(3)]
    assert lv == [0, 0, 3]


def test_mq2_curve_roundtrip_and_trend():
    assert np.isclose(ppm_from_ratio(ratio_from_ppm(1234.0)), 1234.0)
    tr = GasTrend()
    for i in range(20):
        slope, dtemp = tr.update(100 + 10 * i, 28.0 + i / 60.0)
    assert np.isclose(slope, 10.0) and np.isclose(dtemp, 1.0)
