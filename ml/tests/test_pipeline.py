"""Test cho pipeline: feature không rò rỉ tương lai, logic cảnh báo (hysteresis, debounce), bias correction."""
import numpy as np
import pandas as pd
import pytest

from aiot_ml import features as fe
from aiot_ml.forecast_infer import BiasCorrector
from aiot_ml.gas_edge import (EdgeEngine, FeatureExtractor, ModelLevelFilter, RuleConfig, RuleEngine,
                              ppm_from_ratio, ratio_from_ppm)


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
    df2.iloc[100:] += 50.0  # thay đổi tương lai
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
    assert 1009.8 < p0 < 1010.1  # ≈ +0.12 hPa/m
    cz = fe.solar_cos_zenith(pd.DatetimeIndex(["2025-06-21 12:30", "2025-06-21 00:30"]))
    assert cz[0] > 0.9 and cz[1] < 0


def test_bias_corrector_learns_offset():
    om = _toy_hourly()
    st = om.copy()
    st["temp"] = om["temp"] + 1.5  # trạm đọc cao hơn 1.5°C
    bc = BiasCorrector(alpha=0.0).fit(st, om)
    assert np.allclose(bc.to_om(st)["temp"], om["temp"], atol=1e-6)
    assert np.isclose(bc.to_station("temp", 25.0), 26.5)


def test_bias_corrector_falls_back_to_offset_when_uncorrelated():
    om = _toy_hourly()
    st = om.copy()
    rng = np.random.default_rng(0)
    st["temp"] = om["temp"].mean() + 2.0 + rng.normal(0, 1, len(om))  # trạm gần như không tương quan với OM
    bc = BiasCorrector(alpha=0.0).fit(st, om)
    a, b = bc.coef["temp"]
    assert a == 1.0 and np.isclose(b, (om["temp"] - st["temp"]).mean())


# ------------------------------------------------------------------ rule engine
def test_rule_debounce_up_and_immediate_danger():
    r = RuleEngine(RuleConfig(debounce_up=3))
    assert [r.update(1200, 0, 0) for _ in range(3)] == [0, 0, 2]
    r2 = RuleEngine()
    assert r2.update(2500, 0, 0) == 3  # cấp 3 tăng ngay, không debounce


def test_rule_hysteresis_and_debounce_down():
    r = RuleEngine(RuleConfig(debounce_up=1, debounce_down=3, hyst=0.15))
    assert r.update(1100, 0, 0) == 2
    # 950 < 1000 nhưng > 1000·0.85 = 850 -> giữ cấp 2 (hysteresis)
    assert [r.update(950, 0, 0) for _ in range(5)] == [2] * 5
    # 800 < 850 -> hạ cấp sau 3 mẫu liên tiếp, xuống cấp 1 (800 > 300)
    assert [r.update(800, 0, 0) for _ in range(3)] == [2, 2, 1]


def test_rule_spike_does_not_trigger():
    r = RuleEngine()
    seq = [10, 10, 1500, 10, 10, 1500, 10]
    assert max(r.update(p, 0, 0) for p in seq) == 0


def test_rule_temp_rising_escalates_to_danger():
    r = RuleEngine(RuleConfig(debounce_up=1))
    assert r.update(1200, 0, 0.2) == 2
    assert r.update(1200, 0, 1.5) == 3


def test_model_filter_and_fusion_never_lowers_rule():
    f = ModelLevelFilter(n_up=2, n_down=2)
    assert [f.update(x) for x in [2, 2, 0, 0]] == [0, 2, 2, 0]

    class Const:
        classes_ = np.array([0, 1, 2, 3])

        def predict_proba(self, X):
            return np.array([[1.0, 0, 0, 0]])  # model luôn nói "an toàn"

    eng = EdgeEngine(model=Const(), mode="hybrid", rule_cfg=RuleConfig(debounce_up=1))
    lv = [eng.step(2500, 0.5, 28, 70, 100)[0] for _ in range(3)]
    assert lv[-1] == 3  # model không được hạ cấp do rule đưa ra


def test_mq2_curve_roundtrip_and_extractor():
    assert np.isclose(ppm_from_ratio(ratio_from_ppm(1234.0)), 1234.0)
    fx = FeatureExtractor()
    for i in range(20):
        f = fx.update(100 + 10 * i, 5.0, 28.0, 70.0, 300.0)
    assert np.isclose(f[2], 10.0)  # slope10 = 10 ppm/s
