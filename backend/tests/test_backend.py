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
         "fw": "2.1.0"}
    d.update(kw)
    return json.dumps(d).encode()


def rt():
    from app.runtime import rt as _rt
    return _rt()


def test_schema_rejects_out_of_range():
    t = TelemetryIn.model_validate({"device_id": "x", "ts": 1762671600, "seq": 1, "temp_dht": 99.0,
                                    "pressure": 1009, "hum": 120, "foo": "bar"})
    assert t.temp_dht is None and t.hum is None and t.pressure == 1009
    assert any("temp_dht" in r for r in t.rejected)
    assert t.extra_fields()["foo"] == "bar"
    with pytest.raises(Exception):
        AlertIn.model_validate({"device_id": "x", "ts": 1, "level": 7})


def test_ingest_dedupe_and_api(app_client):
    m = rt().mqtt
    rows = [m.handle("vku/aiot/station01/telemetry", tel(i, now_ts() - 60 + i)) for i in range(1, 6)]
    rows.append(m.handle("vku/aiot/station01/telemetry", tel(3, now_ts() - 60 + 3)))
    assert rows[-1] is None and m.stats["duplicates"] == 1
    assert m.flush([r for r in rows if r]) == 5
    assert m.flush([r for r in rows[:2] if r]) == 0
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
    m.handle("vku/aiot/station01/status", json.dumps({"state": "offline"}).encode())
    assert app_client.get("/api/devices/station01").json()["status"] == "offline"
    a = app_client.get("/api/alerts", params={"device_id": "station01"}).json()
    assert a[0]["type"] == "device_offline"


def test_sensor_health_reports_each_sensor(app_client):
    r = rt()
    ok = {"dht": True, "bmp": True, "bh": True, "rain": True, "gas": True}
    t0 = now_ts() - 50
    rows = []
    for i in range(5):
        flags = dict(ok, gas=i < 3, bh=i != 1)
        kw = {"sensor_ok": flags, "gas_raw": 142}
        if i == 4:
            kw["temp_dht"] = None
        rows.append(r.mqtt.handle("vku/aiot/station01/telemetry", tel(100 + i, t0 + i * 10, **kw)))
    r.mqtt.flush(rows)
    h = app_client.get("/api/sensors/station01").json()
    st = {s["sensor"]: s for s in h["sensors"]}
    assert h["online"] is True
    assert st["dht"]["status"] == "error" and "Mất dữ liệu" in st["dht"]["message"]
    assert st["gas"]["status"] == "error" and "142 mV" in st["gas"]["message"]
    assert st["bh"]["status"] == "warn" and "1/5" in st["bh"]["message"]
    assert st["bmp"]["status"] == st["rain"]["status"] == "ok"
    assert st["gas"]["last_ok"] is not None
    assert app_client.get("/api/sensors/khongco").json()["sensors"][0]["status"] == "unknown"


def test_sensor_health_dry_rain_plate_at_adc_ceiling_is_ok(app_client):
    r = rt()
    t0 = now_ts() - 50
    rows = [r.mqtt.handle("vku/aiot/station01/telemetry", tel(200 + i, t0 + i * 10, rain_raw=3134))
            for i in range(5)]
    r.mqtt.flush(rows)
    st = {s["sensor"]: s for s in app_client.get("/api/sensors/station01").json()["sensors"]}
    assert st["rain"]["status"] == "ok"
    rows = [r.mqtt.handle("vku/aiot/station01/telemetry", tel(300, t0 + 55, rain_raw=3010))]
    r.mqtt.flush(rows)
    st = {s["sensor"]: s for s in app_client.get("/api/sensors/station01").json()["sensors"]}
    assert st["rain"]["status"] == "ok"


def test_unsynced_device_time_replaced_by_server_time(app_client):
    m = rt().mqtt
    before = int(time.time())
    row = m.handle("vku/aiot/station01/telemetry", tel(7, ts=74))
    assert row is not None and int(row["ts"].timestamp()) >= before
    assert row["extra"]["ts_server"] is True


def test_empty_payload_is_retained_clear_not_status(app_client):
    m = rt().mqtt
    invalid = m.stats["invalid"]
    for kind in ("status", "telemetry", "forecast"):
        m.handle(f"vku/aiot/ghost99/{kind}", b"")
    assert app_client.get("/api/devices/ghost99").status_code == 404
    assert m.stats["invalid"] == invalid


def alert_payload(level, prev, seq, ppm=1200.0):
    return json.dumps({"device_id": "station01", "ts": now_ts(), "seq": seq, "type": "gas", "level": level,
                       "prev_level": prev, "cause": ["gas_ppm>1000"], "gas_ppm": ppm,
                       "action": ["buzzer_intermittent"]}).encode()


def test_test_alarm_not_notified_or_reminded(app_client):
    r = rt()
    p = json.loads(alert_payload(3, 0, 900))
    p.update(type="test", cause=["test_alarm"])
    r.mqtt.handle("vku/aiot/station01/alert", json.dumps(p).encode())
    a = app_client.get("/api/alerts", params={"device_id": "station01"}).json()[0]
    assert a["type"] == "test" and a["notify_count"] == 0
    assert r.alerts.reminders() == 0


def test_notification_policy_and_cooldown(app_client):
    r = rt()
    r.notifier.sent.clear()
    r.mqtt.handle("vku/aiot/station01/alert", alert_payload(1, 0, 101, 400))
    assert r.notifier.sent == []
    r.mqtt.handle("vku/aiot/station01/alert", alert_payload(2, 1, 102))
    assert [s["channel"] for s in r.notifier.sent] == ["telegram"]
    r.mqtt.handle("vku/aiot/station01/alert", alert_payload(2, 2, 103))
    assert len(r.notifier.sent) == 1
    r.mqtt.handle("vku/aiot/station01/alert", alert_payload(3, 2, 104, 2500))
    assert [s["channel"] for s in r.notifier.sent[1:]] == ["telegram", "email"]
    r.mqtt.handle("vku/aiot/station01/alert", alert_payload(3, 2, 104, 2500))
    alerts = app_client.get("/api/alerts", params={"device_id": "station01"}).json()
    assert len(alerts) == 4


def test_level3_reminders_until_ack(app_client, token):
    r = rt()
    r.settings.reminder_every_s = 0
    r.mqtt.handle("vku/aiot/station01/alert", alert_payload(3, 0, 201, 3000))
    n0 = len(r.notifier.sent)
    assert r.alerts.reminders() == 1 and len(r.notifier.sent) > n0
    aid = app_client.get("/api/alerts", params={"min_level": 3}).json()[0]["id"]
    assert app_client.post(f"/api/alerts/{aid}/ack").status_code == 401
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
    for i in range(60):
        ppm = 300 + 40 * (i * 10 / 60)
        rows.append(m.handle("vku/aiot/station01/telemetry", tel(1000 + i, t0 + i * 10, gas_ppm=ppm, edge_risk=1)))
    m.flush(rows)
    lvl = r.alerts.evaluate("station01")
    assert lvl == 2
    cloud = app_client.get("/api/alerts", params={"source": "cloud"}).json()
    assert cloud and cloud[0]["level"] == 2 and cloud[0]["prev_level"] == 1
    assert any(t.endswith("/cmd") and p["cmd"] == "escalate" and p["level"] == 2 for t, p, _ in r.publisher.published)
    assert r.alerts.evaluate("station01") == 0


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


def test_delete_device_removes_all_its_data(app_client, token):
    r = rt()
    rows = [r.mqtt.handle("vku/aiot/loadtest000/telemetry", tel(i, device_id="loadtest000")) for i in range(1, 4)]
    r.mqtt.flush([x for x in rows if x])
    r.mqtt.flush([r.mqtt.handle("vku/aiot/station01/telemetry", tel(1))])
    assert app_client.delete("/api/devices/loadtest000").status_code == 401
    res = app_client.delete("/api/devices/loadtest000", headers=token).json()
    assert res["deleted"]["telemetry"] == 3 and res["deleted"]["device"] == 1
    assert app_client.get("/api/devices/loadtest000").status_code == 404
    assert app_client.get("/api/telemetry", params={"device_id": "loadtest000"}).json() == []
    assert len(app_client.get("/api/telemetry", params={"device_id": "station01"}).json()) == 1
    assert ("vku/aiot/loadtest000/forecast", {}, True) in r.publisher.published


def test_config_and_cmd_require_auth_and_publish(app_client, token):
    r = rt()
    assert app_client.put("/api/devices/station01/config", json={"th1": 250}).status_code == 401
    bad = app_client.put("/api/devices/station01/config", json={"th1": 900, "th2": 800, "th3": 2000}, headers=token)
    assert bad.status_code == 422
    ok = app_client.put("/api/devices/station01/config", json={"th1": 250}, headers=token).json()
    assert ok["version"] == 1 and ok["config"]["th1"] == 250
    t, p, retain = r.publisher.published[-1]
    assert t == "vku/aiot/station01/config" and retain and p["version"] == 1
    ok2 = app_client.put("/api/devices/station01/config", json={"telemetry_ms": 5000}, headers=token).json()
    assert ok2["config"] == {"th1": 250, "telemetry_ms": 5000, "version": 2}
    r.mqtt.handle("vku/aiot/station01/ack", json.dumps({"ref": "config", "ok": True, "msg": "v2"}).encode())
    assert app_client.get("/api/devices/station01").json()["config"]["acked"] is True
    c = app_client.post("/api/devices/station01/cmd", json={"cmd": "test_alarm"}, headers=token).json()
    r.mqtt.handle("vku/aiot/station01/ack", json.dumps({"ref": "cmd", "id": c["id"], "ok": True}).encode())
    cmds = app_client.get("/api/devices/station01/commands").json()
    assert cmds[0]["acked"] is True
    assert app_client.post("/api/devices/station01/cmd", json={"cmd": "format_disk"}, headers=token).status_code == 422


def _open_meteo_frame(hours=96, temp_mean=24.0):
    """Khung Open-Meteo giả (đã chuẩn hoá) cho test, không gọi mạng."""
    import pandas as pd
    from aiot_ml import features as fe
    idx = pd.date_range(end=pd.Timestamp.now().floor("h"), periods=hours, freq="1h")
    hr = idx.hour.to_numpy()
    raw = pd.DataFrame({
        "temperature_2m": temp_mean + 3 * np.sin(2 * np.pi * (hr - 9) / 24),
        "relative_humidity_2m": 80 - 8 * np.sin(2 * np.pi * (hr - 9) / 24),
        "pressure_msl": 1010 + 0.5 * np.sin(np.arange(hours) / 20),
        "dew_point_2m": temp_mean - 4.0,
        "shortwave_radiation": np.clip(800 * np.sin(np.pi * (hr - 6) / 12), 0, None),
        "precipitation": 0.0,
        "cloud_cover": 40.0,
    }, index=idx)
    return fe.open_meteo_to_canonical(raw)


def test_forecast_uses_open_meteo_not_station(app_client, monkeypatch):
    r = rt()
    m = r.mqtt
    start = now_ts() - 40 * 3600
    rows = [m.handle("vku/aiot/station01/telemetry", tel(5000 + i, start + i * 600, temp_dht=33.0, hum=55.0, lux=150.0))
            for i in range(40 * 6)]
    m.flush(rows)
    monkeypatch.setattr(r.forecast.s, "use_open_meteo", True)
    monkeypatch.setattr(r.forecast, "_open_meteo_recent", lambda: _open_meteo_frame(temp_mean=24.0))
    p = r.forecast.run_once("station01")
    assert p["source"] == "open-meteo"
    targets = {(i["target"], i["h"]) for i in p["items"]}
    assert ("temp", 1) in targets and ("hum", 6) in targets and ("rain_prob", 3) in targets
    assert not any(t == "pres" for t, _ in targets)
    t1 = next(i for i in p["items"] if i["target"] == "temp" and i["h"] == 1)
    assert 18 < t1["value"] < 30, "dự báo phải theo Open-Meteo (≈24 °C), không theo số đo trong nhà 33 °C"
    assert t1["lower"] < t1["value"] < t1["upper"]
    assert any(t.endswith("/forecast") for t, _, ret in r.publisher.published)
    fc = app_client.get("/api/forecast/station01").json()
    assert len(fc["latest"]) == len(p["items"])


def test_forecast_skipped_when_open_meteo_unavailable(app_client, monkeypatch):
    r = rt()
    n_pub = len(r.publisher.published)
    p = r.forecast.run_once("station01")
    assert p["source"] == "unavailable" and p["items"] == []

    def boom():
        raise OSError("mất mạng")
    monkeypatch.setattr(r.forecast.s, "use_open_meteo", True)
    monkeypatch.setattr(r.forecast, "_open_meteo_recent", boom)
    assert r.forecast.run_once("station01")["source"] == "unavailable"
    assert len(r.publisher.published) == n_pub
    assert app_client.get("/api/forecast/station01").json()["latest"] == []


def _members(fracs, n=10):
    """Ensemble giả theo giờ địa phương (giờ hiện tại = fracs[0]): tỉ lệ thành viên mưa 5 mm = fracs[k], không gọi mạng."""
    import pandas as pd
    t0 = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").tz_localize(None).floor("h")
    idx = [t0 + pd.Timedelta(hours=k) for k in range(len(fracs))]
    rows = [[5.0 if j < round(f * n) else 0.0 for j in range(n)] for f in fracs]
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(idx), columns=[f"m{j}" for j in range(n)])
    return {"ecmwf": df, "gfs": df.copy(), "icon": df.copy()}


FRACS = [0.6, 0.1, 0.5, 0.3, 0.5, 0.6, 0.7, 0.8]


def test_rain_from_free_ensemble_with_station_adjustment(app_client, monkeypatch):
    r = rt()
    monkeypatch.setattr(r.forecast.s, "use_open_meteo", True)
    monkeypatch.setattr(r.forecast.s, "use_rain_ensemble", True)
    monkeypatch.setattr(r.forecast, "_open_meteo_recent", lambda: _open_meteo_frame(temp_mean=24.0))
    monkeypatch.setattr(r.forecast, "_ensemble_members", lambda: _members(FRACS))
    p = r.forecast.run_once("station01")
    assert p["source"] == "open-meteo+ensemble" and p["rain_source"] == "ensemble"
    get = {(i["target"], i["h"]): i["value"] for i in p["items"]}
    for h in (1, 3, 6):
        assert get[("rain_ens", h)] == pytest.approx(FRACS[h]), "mặc định: gộp 3 mô hình, ngưỡng 1 mm"
        assert get[("rain_prob", h)] == pytest.approx(FRACS[h]), "trạm không báo mưa → giữ nguyên"
        assert ("rain_ml", h) in get
    assert ("temp", 1) in get
    fc = app_client.get("/api/forecast/station01").json()
    assert {x["target"] for x in fc["latest"]} >= {"rain_prob", "rain_ens", "rain_ml", "temp", "hum"}

    # YL-83 đang báo mưa → +10 điểm ở +1h, +5 ở +3h, 0 ở +6h
    m = r.mqtt
    m.flush([m.handle("vku/aiot/station01/telemetry", tel(9000, rain_level=2))])
    get = {(i["target"], i["h"]): i["value"] for i in r.forecast.run_once("station01")["items"]}
    assert get[("rain_prob", 1)] == pytest.approx(0.20)
    assert get[("rain_prob", 3)] == pytest.approx(0.35)
    assert get[("rain_prob", 6)] == pytest.approx(0.70)


def test_rain_ensemble_without_open_meteo_and_lightgbm_fallback(app_client, monkeypatch):
    r = rt()
    monkeypatch.setattr(r.forecast.s, "use_rain_ensemble", True)
    monkeypatch.setattr(r.forecast, "_ensemble_members", lambda: _members([0.5] * 8))
    p = r.forecast.run_once("station01")
    assert p["source"] == "ensemble"
    assert {i["target"] for i in p["items"]} == {"rain_prob", "rain_ens"}

    def boom():
        raise OSError("mất mạng")
    monkeypatch.setattr(r.forecast, "_ensemble_members", boom)
    monkeypatch.setattr(r.forecast.s, "use_open_meteo", True)
    monkeypatch.setattr(r.forecast, "_open_meteo_recent", lambda: _open_meteo_frame(temp_mean=24.0))
    p = r.forecast.run_once("station01")
    assert p["source"] == "open-meteo" and p["rain_source"] == "lightgbm"
    assert ("rain_prob", 3) in {(i["target"], i["h"]) for i in p["items"]}


def test_google_numbers_entered_by_hand_then_calibrate(app_client, token, monkeypatch):
    import pandas as pd
    r = rt()
    fracs = [0.1 * (k % 11) for k in range(60)]
    monkeypatch.setattr(r.forecast, "_ensemble_members", lambda: _members(fracs))
    t0 = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").tz_localize(None).floor("h")
    google = lambda k: 20 + 50 * fracs[k]  # "Google" nén thang xác suất: 0 % → 20 %, 100 % → 70 %
    body = {"items": [{"valid_at": (t0 + pd.Timedelta(hours=k)).isoformat(), "pct": google(k)} for k in range(1, 6)]}
    assert app_client.post("/api/rain/google", json=body).status_code == 401
    res = app_client.post("/api/rain/google", json=body, headers=token).json()
    assert len(res["saved"]) == 5 and res["skipped"] == []
    out = app_client.get("/api/rain/google").json()
    assert out["metrics"]["n"] == 5 and out["calibration"]["version"] == "ens-default"
    assert app_client.post("/api/rain/calibrate", headers=token).status_code == 422, "chưa đủ dữ liệu"
    bad = {"items": [{"valid_at": t0.isoformat(), "pct": 130}]}
    assert app_client.post("/api/rain/google", json=bad, headers=token).status_code == 422

    body = {"items": [{"valid_at": (t0 + pd.Timedelta(hours=k)).isoformat(), "pct": google(k)} for k in range(6, 54)]}
    assert len(app_client.post("/api/rain/google", json=body, headers=token).json()["saved"]) == 48
    before = app_client.get("/api/rain/google").json()["metrics"]
    c = app_client.post("/api/rain/calibrate", headers=token).json()
    assert c["version"].startswith("ens-") and c["n"] == 53
    after = app_client.get("/api/rain/google").json()
    assert after["calibration"]["version"] == c["version"]
    assert after["metrics"]["MAE"] < before["MAE"] and after["metrics"]["within10"] == 1.0

    # lượt dự báo sau dùng ngay hiệu chỉnh mới
    monkeypatch.setattr(r.forecast.s, "use_rain_ensemble", True)
    get = {(i["target"], i["h"]): i["value"] for i in r.forecast.run_once("station01")["items"]}
    assert get[("rain_ens", 1)] * 100 == pytest.approx(google(1), abs=2)


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
