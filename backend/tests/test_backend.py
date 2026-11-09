"""Test backend: validate schema, ingest + chống trùng, logic cảnh báo (cấp, cooldown, leo thang, offline, ack),
API (JWT, config, cmd, telemetry, export), forecast service, WebSocket."""
import datetime as dt
import json
import time

import numpy as np
import pytest

from app.schemas.payloads import AlertIn, TelemetryIn


def now_ts():
    return int(time.time())


def tel(seq, ts=None, **kw):
    d = {"device_id": "station01", "ts": ts or now_ts(), "seq": seq, "temp_dht": 28.5, "hum": 80.0,
         "temp_bmp": 29.0, "pressure": 1009.0, "pressure_msl": 1010.0, "lux": 1200.0, "rain_raw": 3000,
         "rain_level": 0, "gas_raw": 300, "gas_rs_r0": 9.1, "gas_ppm": 5.0, "gas_slope": 0.0, "edge_risk": 0,
         "edge_score": 0.01, "fw": "1.0.0", "model_ver": "gas-v1"}
    d.update(kw)
    return json.dumps(d).encode()


def rt():
    from app.runtime import rt as _rt
    return _rt()


# ------------------------------------------------------------------ schema
def test_schema_rejects_out_of_range():
    t = TelemetryIn.model_validate({"device_id": "x", "ts": 1762671600, "seq": 1, "temp_dht": 99.0,
                                    "pressure": 1009, "hum": 120, "foo": "bar"})
    assert t.temp_dht is None and t.hum is None and t.pressure == 1009
    assert any("temp_dht" in r for r in t.rejected)
    assert t.extra_fields()["foo"] == "bar"
    with pytest.raises(Exception):
        AlertIn.model_validate({"device_id": "x", "ts": 1, "level": 7})


# ------------------------------------------------------------------ ingest
def test_ingest_dedupe_and_api(app_client):
    m = rt().mqtt
    rows = [m.handle("vku/aiot/station01/telemetry", tel(i, now_ts() - 60 + i)) for i in range(1, 6)]
    rows.append(m.handle("vku/aiot/station01/telemetry", tel(3, now_ts() - 60 + 3)))  # trùng
    assert rows[-1] is None and m.stats["duplicates"] == 1
    assert m.flush([r for r in rows if r]) == 5
    assert m.flush([r for r in rows[:2] if r]) == 0  # chống trùng ở DB
    data = app_client.get("/api/telemetry", params={"device_id": "station01"}).json()
    assert len(data) == 5 and data[0]["temp_dht"] == 28.5
    latest = app_client.get("/api/telemetry/latest", params={"device_id": "station01"}).json()
    assert latest["seq"] == 5
    dev = app_client.get("/api/devices/station01").json()
    assert dev["status"] == "online"
    agg = app_client.get("/api/telemetry", params={"device_id": "station01", "resolution": "1h"}).json()
    assert len(agg) >= 1
    csv = app_client.get("/api/export.csv", params={"device_id": "station01"})
    assert csv.status_code == 200 and csv.text.startswith("device_id")


def test_ingest_invalid_json_and_status(app_client):
    m = rt().mqtt
    m.handle("vku/aiot/station01/telemetry", b"not json")
    assert m.stats["invalid"] >= 1
    m.handle("vku/aiot/station01/status", json.dumps({"state": "online", "rssi": -60, "fw": "1.0.0"}).encode())
    assert app_client.get("/api/devices/station01").json()["rssi"] == -60
    m.handle("vku/aiot/station01/status", json.dumps({"state": "offline"}).encode())  # LWT
    assert app_client.get("/api/devices/station01").json()["status"] == "offline"
    a = app_client.get("/api/alerts", params={"device_id": "station01"}).json()
    assert a[0]["type"] == "device_offline"


# ------------------------------------------------------------------ alerts
def alert_payload(level, prev, seq, ppm=1200.0):
    return json.dumps({"device_id": "station01", "ts": now_ts(), "seq": seq, "type": "gas", "level": level,
                       "prev_level": prev, "cause": ["gas_ppm>1000"], "gas_ppm": ppm, "score": 0.9,
                       "action": ["buzzer_intermittent"]}).encode()


def test_notification_policy_and_cooldown(app_client):
    r = rt()
    r.notifier.sent.clear()
    r.mqtt.handle("vku/aiot/station01/alert", alert_payload(1, 0, 101, 400))
    assert r.notifier.sent == []  # cấp 1: chỉ log/dashboard
    r.mqtt.handle("vku/aiot/station01/alert", alert_payload(2, 1, 102))
    assert [s["channel"] for s in r.notifier.sent] == ["telegram"]
    r.mqtt.handle("vku/aiot/station01/alert", alert_payload(2, 2, 103))  # lặp trong cooldown
    assert len(r.notifier.sent) == 1
    r.mqtt.handle("vku/aiot/station01/alert", alert_payload(3, 2, 104, 2500))
    assert [s["channel"] for s in r.notifier.sent[1:]] == ["telegram", "email"]
    r.mqtt.handle("vku/aiot/station01/alert", alert_payload(3, 2, 104, 2500))  # trùng seq -> bỏ
    alerts = app_client.get("/api/alerts", params={"device_id": "station01"}).json()
    assert len(alerts) == 4


def test_level3_reminders_until_ack(app_client, token):
    r = rt()
    r.settings.reminder_every_s = 0
    r.mqtt.handle("vku/aiot/station01/alert", alert_payload(3, 0, 201, 3000))
    n0 = len(r.notifier.sent)
    assert r.alerts.reminders() == 1 and len(r.notifier.sent) > n0
    aid = app_client.get("/api/alerts", params={"min_level": 3}).json()[0]["id"]
    assert app_client.post(f"/api/alerts/{aid}/ack").status_code == 401  # cần JWT
    assert app_client.post(f"/api/alerts/{aid}/ack", headers=token).json()["ok"]
    assert r.alerts.reminders() == 0
    a = app_client.get("/api/alerts", params={"min_level": 3}).json()[0]
    assert a["acknowledged_by"] == "admin" and a["ack_ts"]


def test_back_to_normal_resolves_and_notifies(app_client):
    r = rt()
    r.mqtt.handle("vku/aiot/station01/alert", alert_payload(2, 0, 301))
    r.notifier.sent.clear()
    r.mqtt.handle("vku/aiot/station01/alert", alert_payload(0, 2, 302, 50))
    assert r.notifier.sent and "Bình thường" in r.notifier.sent[0]["text"]
    open_ = [a for a in app_client.get("/api/alerts").json() if a["level"] > 0 and not a["resolved_at"]]
    assert open_ == []


def test_cloud_escalation_on_sustained_rise(app_client):
    r = rt()
    m = r.mqtt
    t0 = now_ts() - 600
    rows = []
    for i in range(60):  # 10 phút, ppm tăng đều 40 ppm/phút từ 300
        ppm = 300 + 40 * (i * 10 / 60)
        rows.append(m.handle("vku/aiot/station01/telemetry", tel(1000 + i, t0 + i * 10, gas_ppm=ppm, edge_risk=1)))
    m.flush(rows)
    lvl = r.alerts.evaluate("station01")
    assert lvl == 2
    cloud = app_client.get("/api/alerts", params={"source": "cloud"}).json()
    assert cloud and cloud[0]["level"] == 2 and cloud[0]["prev_level"] == 1
    assert any(t.endswith("/cmd") and p["cmd"] == "escalate" and p["level"] == 2 for t, p, _ in r.publisher.published)
    assert r.alerts.evaluate("station01") == 0  # không lặp lại


def test_no_escalation_when_flat(app_client):
    r = rt()
    t0 = now_ts() - 600
    rows = [r.mqtt.handle("vku/aiot/station01/telemetry", tel(2000 + i, t0 + i * 10, gas_ppm=400 + np.sin(i), edge_risk=1))
            for i in range(60)]
    r.mqtt.flush(rows)
    assert r.alerts.evaluate("station01") == 0


def test_offline_detection(app_client):
    from app.db.models import Device
    from app.db.session import session_scope
    with session_scope() as s:
        d = s.get(Device, "station01")
        d.status, d.last_seen = "online", dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=120)
    assert rt().alerts.check_offline() == ["station01"]
    assert app_client.get("/api/devices/station01").json()["status"] == "offline"


# ------------------------------------------------------------------ config & cmd
def test_config_and_cmd_require_auth_and_publish(app_client, token):
    r = rt()
    assert app_client.put("/api/devices/station01/config", json={"th1": 250}).status_code == 401
    bad = app_client.put("/api/devices/station01/config", json={"th1": 900, "th2": 800, "th3": 2000}, headers=token)
    assert bad.status_code == 422
    ok = app_client.put("/api/devices/station01/config", json={"th1": 250, "mode": "hybrid"}, headers=token).json()
    assert ok["version"] == 1 and ok["config"]["th1"] == 250
    t, p, retain = r.publisher.published[-1]
    assert t == "vku/aiot/station01/config" and retain and p["version"] == 1
    ok2 = app_client.put("/api/devices/station01/config", json={"telemetry_ms": 5000}, headers=token).json()
    assert ok2["config"] == {"th1": 250, "mode": "hybrid", "telemetry_ms": 5000, "version": 2}
    # ack từ thiết bị
    r.mqtt.handle("vku/aiot/station01/ack", json.dumps({"ref": "config", "ok": True, "msg": "v2"}).encode())
    assert app_client.get("/api/devices/station01").json()["config"]["acked"] is True
    c = app_client.post("/api/devices/station01/cmd", json={"cmd": "test_alarm"}, headers=token).json()
    r.mqtt.handle("vku/aiot/station01/ack", json.dumps({"ref": "cmd", "id": c["id"], "ok": True}).encode())
    cmds = app_client.get("/api/devices/station01/commands").json()
    assert cmds[0]["acked"] is True
    assert app_client.post("/api/devices/station01/cmd", json={"cmd": "format_disk"}, headers=token).status_code == 422


# ------------------------------------------------------------------ forecast
def test_forecast_from_station_data(app_client):
    r = rt()
    m = r.mqtt
    start = now_ts() - 40 * 3600
    rows = []
    for i in range(40 * 6):  # 40 giờ, 1 mẫu / 10 phút
        ts = start + i * 600
        h = ((ts + 7 * 3600) % 86400) / 3600
        rows.append(m.handle("vku/aiot/station01/telemetry",
                             tel(5000 + i, ts, temp_dht=27 + 3 * np.sin(2 * np.pi * (h - 9) / 24),
                                 hum=80 - 8 * np.sin(2 * np.pi * (h - 9) / 24), pressure_msl=1010 + 0.5 * np.sin(i / 20),
                                 lux=max(0.0, 40000 * np.sin(np.pi * (h - 6) / 12)) if 6 < h < 18 else 0.0)))
    m.flush(rows)
    p = r.forecast.run_once("station01")
    assert p["source"] == "station"
    targets = {(i["target"], i["h"]) for i in p["items"]}
    assert ("temp", 1) in targets and ("rain_prob", 3) in targets
    t1 = next(i for i in p["items"] if i["target"] == "temp" and i["h"] == 1)
    assert 15 < t1["value"] < 40 and t1["lower"] < t1["value"] < t1["upper"]
    assert any(t.endswith("/forecast") for t, _, ret in r.publisher.published)
    fc = app_client.get("/api/forecast/station01").json()
    assert len(fc["latest"]) == len(p["items"])


def test_forecast_fallback_when_no_data(app_client):
    p = rt().forecast.run_once("station01")
    assert p["source"] == "fallback"


def test_models_endpoint_and_health(app_client):
    ms = app_client.get("/api/models").json()
    assert any(m["name"] == "forecast_temp_1h" and m["active"] for m in ms)
    assert app_client.get("/api/health").json()["status"] == "ok"


def test_websocket_receives_telemetry(app_client):
    with app_client.websocket_connect("/ws/live") as wsc:
        assert wsc.receive_json()["type"] == "hello"
        r = rt()
        r.mqtt.flush([r.mqtt.handle("vku/aiot/station01/telemetry", tel(9001))])
        msg = wsc.receive_json()
        assert msg["type"] == "telemetry" and msg["data"]["seq"] == 9001
