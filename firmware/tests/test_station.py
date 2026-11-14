import json
import sys
from pathlib import Path

import pytest

import config
from display import COLS1, COLS2, N_ROWS, compose_rows
from readings import RawSample
from station import Station
from storage import Storage

BACKEND = Path(__file__).resolve().parents[2] / "backend"


class FakeLink:
    def __init__(self):
        self.up = True
        self.sent = []
        self.reconnects = 1

    def step(self, now):
        return self.up

    def publish(self, suffix, payload, retain=False):
        if not self.up:
            return False
        self.sent.append((suffix, json.loads(payload), retain))
        return True

    def connected(self):
        return self.up

    def wifi_connected(self):
        return self.up

    def rssi(self):
        return -60

    def of(self, suffix):
        return [p for s, p, _ in self.sent if s == suffix]


class FakeHW:
    def __init__(self):
        self.resets = 0

    def sysinfo(self):
        return {"uptime_s": 1, "free_heap": 100000, "min_free_heap": 90000, "reset_reason": 1}

    def mean_rs_kohm(self, mq2):
        return 98.3

    def ota(self, url, station):
        return False, "ota failed: test"

    def reset(self):
        self.resets += 1


def gas_mv_for_ppm(ppm, st):
    p = st.proc.mq2
    ratio = (ppm / p.curve_a) ** (1.0 / p.curve_b)
    rs = ratio * p.r0_kohm
    v = p.vc * p.rl_kohm / (rs + p.rl_kohm)
    return v * p.divider * 1000.0


def raw(st, ppm, t=28.0, h=75.0):
    return RawSample(dht=(t, h), bmp=(25.0, 1009.0), lux=300.0, rain_mv=3134, gas_mv=gas_mv_for_ppm(ppm, st),
                     bmp_present=True, bh_present=True)


@pytest.fixture
def station(tmp_path):
    return Station(Storage(str(tmp_path)), FakeHW())


def run(st, link, ppms, t0=0):
    now = t0
    for ppm in ppms:
        st.sample_step(raw(st, ppm), now)
        st.net_step(link, now)
        now += 1000
    return now


def test_warmup_then_gas_alert_and_telemetry(station):
    link = FakeLink()
    now = run(station, link, [50.0] * (config.MQ2_WARMUP_S + 5))
    tel = link.of("telemetry")
    assert tel and tel[0]["warming_up"] and not tel[-1]["warming_up"]
    assert tel[-1]["gas_ppm"] == pytest.approx(50.0, rel=0.05)
    assert link.of("status") and link.of("status")[0]["state"] == "online"
    assert not link.of("nowcast")
    run(station, link, [2500.0] * 15, now)
    alerts = [a for a in link.of("alert") if a["type"] == "gas"]
    assert alerts[-1]["level"] == 3 and "gas_ppm>2000" in alerts[-1]["cause"]
    assert "buzzer_continuous" in alerts[-1]["action"]
    assert station.actuator_states(now)[3]


def test_config_and_commands(station):
    link = FakeLink()
    station.on_message("config", b'{"th1": 250, "th2": 900, "th3": 1800, "version": 7, "mode": "rule"}')
    station.on_message("config", b'{"th1": 5000}')
    station.on_message("cmd", b'{"cmd": "mute", "id": "c1"}')
    station.on_message("cmd", b'{"cmd": "fly", "id": "c2"}')
    station.on_message("cmd", b'not json')
    station.on_message("cmd", b'{"cmd": "calibrate", "id": "c3"}')
    station.on_message("forecast", b'{"summary": "3h: 27.1C, mua 40%"}')
    run(station, link, [50.0])
    acks = link.of("ack")
    assert {"ref": "config", "ok": True} .items() <= acks[0].items() and "v7" in acks[0]["msg"]
    assert acks[1]["ok"] is False and acks[1]["msg"] == "invalid ranges"
    assert acks[2] == {**acks[2], "id": "c1", "ok": True}
    assert acks[3]["ok"] is False and acks[3]["msg"] == "unknown cmd"
    assert acks[4]["msg"] == "bad json"
    assert any(a["ref"] == "calibrate" and "R0=10.00" in a["msg"] for a in acks)
    assert station.edge.rules.cfg.th1 == 250 and station.edge.mode == 0
    assert station.dstate.cloud_forecast.startswith("3h:")
    assert Storage(station.storage.base).load_config().version == 7


def test_cloud_escalation_raises_level(station):
    link = FakeLink()
    now = run(station, link, [50.0] * (config.MQ2_WARMUP_S + 2))
    station.on_message("cmd", b'{"cmd": "escalate", "level": 2, "id": "e1"}')
    run(station, link, [50.0], now)
    a = link.of("alert")[-1]
    assert a["level"] == 2 and "cloud_escalation" in a["cause"]


def test_offline_buffer_then_replay(station):
    link = FakeLink()
    link.up = False
    now = run(station, link, [50.0] * 30)
    assert station.storage.pending() >= 3
    link.up = True
    run(station, link, [50.0], now)
    assert station.storage.pending() == 0
    seqs = [t["seq"] for t in link.of("telemetry")]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


def test_payloads_match_backend_schema(station):
    pytest.importorskip("pydantic")
    sys.path.insert(0, str(BACKEND))
    try:
        from app.schemas.payloads import AlertIn, StatusIn, TelemetryIn
    finally:
        sys.path.remove(str(BACKEND))
    link = FakeLink()
    run(station, link, [50.0] * (config.MQ2_WARMUP_S + 2) + [2500.0])
    for t in link.of("telemetry"):
        m = TelemetryIn.model_validate(t)
        assert not m.rejected, m.rejected
    for a in link.of("alert"):
        AlertIn.model_validate(a)
    for s in link.of("status"):
        StatusIn.model_validate(s)


@pytest.mark.parametrize("level,warming,muted", [(0, True, False), (1, False, False), (3, False, True)])
def test_display_rows_fit_screen(station, level, warming, muted):
    link = FakeLink()
    run(station, link, [50.0] * 3)
    ds = station.dstate
    ds.level, ds.warming_up, ds.muted = level, warming, muted
    ds.cloud_forecast = "Du bao 3h: 27.4C do am 82% kha nang mua 65% gio nhe tu bien"
    colors = {k: i for i, k in enumerate(("BLACK", "WHITE", "RED", "DARKGREEN", "YELLOW", "ORANGE", "CYAN", "GREY"))}
    for page in range(3):
        rows = compose_rows(ds, page, "12:34", colors)
        assert len(rows) == N_ROWS
        for r in rows:
            if r:
                y, size, fg, bg, text = r
                assert len(text) <= (COLS1 if size == 1 else COLS2), (page, text)
                assert 0 <= y and y + 8 * size <= 128
