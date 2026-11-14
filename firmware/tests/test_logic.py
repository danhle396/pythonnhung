import math

import pytest

from alert import (BUZZER_CONTINUOUS, BUZZER_INTERMITTENT, BUZZER_OFF, LED_RED_BLINK, AlertManager, RuleConfig,
                   RuleEngine)
from edge_ai import FAULT_DISCONNECTED, FAULT_SATURATED, EdgeAI, Mq2FaultDetector, Mq2Params, mq2_convert
from filters import Ewma, Median5, RingBuffer, dew_point, sea_level_pressure


def test_median_removes_spike():
    m = Median5()
    out = 0
    for v in (10, 10, 500, 10, 10):
        out = m.update(v)
    assert out == 10


def test_ewma_and_ring_slope():
    e = Ewma(0.5)
    e.update(0)
    assert e.update(10) == 5
    r = RingBuffer(10)
    for i in range(15):
        r.push(3.0 * i + 1)
    assert r.slope() == pytest.approx(3.0, abs=1e-6)
    assert r.size() == 10
    assert r.last() == 43


def test_ring_stdev_matches_population_std():
    r = RingBuffer(5)
    vals = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0]
    for v in vals:
        r.push(v)
    last5 = vals[-5:]
    m = sum(last5) / 5
    assert r.stdev() == pytest.approx(math.sqrt(sum((v - m) ** 2 for v in last5) / 5))


def test_rule_debounce_and_immediate_danger():
    r = RuleEngine()
    assert r.update(1200, 0, 0) == 0
    assert r.update(1200, 0, 0) == 0
    assert r.update(1200, 0, 0) == 2
    assert RuleEngine().update(2500, 0, 0) == 3


def test_rule_hysteresis():
    r = RuleEngine(RuleConfig(debounce_up=1, debounce_down=3))
    assert r.update(1100, 0, 0) == 2
    for _ in range(5):
        assert r.update(950, 0, 0) == 2
    assert r.update(800, 0, 0) == 2
    assert r.update(800, 0, 0) == 2
    assert r.update(800, 0, 0) == 1


def test_rule_spike_rejected_and_temp_escalation():
    r = RuleEngine()
    assert max(r.update(p, 0, 0) for p in (10, 10, 1500, 10, 10, 1500, 10)) == 0
    r2 = RuleEngine(RuleConfig(debounce_up=1))
    assert r2.update(1200, 0, 0.2) == 2
    assert r2.update(1200, 0, 1.5) == 3


def test_alert_mute_and_reescalate():
    a = AlertManager(300000)
    x = a.update(2, 1000)
    assert x.level_changed and x.buzzer == BUZZER_INTERMITTENT
    a.press_mute(1100)
    x = a.update(2, 1200)
    assert x.buzzer == BUZZER_OFF
    assert x.led == LED_RED_BLINK
    x = a.update(3, 1300)
    assert x.buzzer == BUZZER_CONTINUOUS
    b = AlertManager(1000)
    b.update(2, 0)
    b.press_mute(0)
    assert b.update(2, 500).buzzer == BUZZER_OFF
    assert b.update(2, 1500).buzzer == BUZZER_INTERMITTENT


def test_cloud_escalation_never_lowers():
    a = AlertManager()
    a.cloud_escalate(1, 0)
    assert a.update(3, 10).level == 3
    a.cloud_escalate(3, 20)
    assert a.update(0, 30).level == 3


def test_alarm_test_is_flagged():
    m = AlertManager()
    m.test_alarm(1000)
    a = m.update(0, 1000)
    assert a.level == 3 and a.testing
    a = m.update(0, 4500)
    assert a.level == 0 and not a.testing
    m.cloud_escalate(2, 5000)
    a = m.update(0, 5000)
    assert a.level == 2 and not a.testing


def test_mq2_conversion_and_fault():
    p = Mq2Params()
    rs = p.r0_kohm
    v = p.vc * p.rl_kohm / (rs + p.rl_kohm)
    r = mq2_convert(v * p.divider * 1000.0, p)
    assert r.ratio == pytest.approx(1.0, abs=1e-3)
    assert r.ppm == pytest.approx(p.curve_a, abs=0.5)
    f = Mq2FaultDetector()
    for _ in range(5):
        f.update(0.0)
    assert f.fault == FAULT_DISCONNECTED
    for _ in range(5):
        f.update(3300.0)
    assert f.fault == FAULT_SATURATED


def test_edge_hybrid_never_below_rule():
    e = EdgeAI(warmup_samples=0)
    e.rules.cfg.debounce_up = 1
    for _ in range(5):
        o = e.step(2500.0, 0.5, 28.0, 70.0, 100.0, True)
    assert o.rule_level == 3
    assert o.level >= o.rule_level


def test_edge_warmup_and_sensor_fault_hold_level_zero():
    e = EdgeAI(warmup_samples=3)
    levels = [e.step(2500.0, 0.5, 28.0, 70.0, 100.0, True).level for _ in range(4)]
    assert levels == [0, 0, 0, 3]
    assert e.step(2500.0, 0.5, 28.0, 70.0, 100.0, False).level == 0


def test_derived_quantities():
    assert dew_point(25.0, 100.0) == pytest.approx(25.0, abs=0.05)
    p0 = sea_level_pressure(1009.0, 28.0, 8.0)
    assert 1009.8 < p0 < 1010.1
