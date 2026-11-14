import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest


def find_mosquitto():
    cands = [os.environ.get("MOSQUITTO_BIN"), shutil.which("mosquitto"),
             r"C:\Program Files\mosquitto\mosquitto.exe", str(Path.home() / "mosquitto" / "mosquitto.exe")]
    return next((c for c in cands if c and Path(c).exists()), None)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_until(fn, timeout=10.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = fn()
        if v:
            return v
        time.sleep(0.2)
    return fn()


@pytest.fixture()
def broker(tmp_path):
    exe = find_mosquitto()
    if not exe:
        pytest.skip("không tìm thấy mosquitto")
    port = free_port()
    conf = tmp_path / "m.conf"
    conf.write_text(f"listener {port} 127.0.0.1\nallow_anonymous true\npersistence false\n")
    proc = subprocess.Popen([exe, "-c", str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ok = wait_until(lambda: socket.socket().connect_ex(("127.0.0.1", port)) == 0, 5)
    if not ok:
        proc.kill()
        pytest.skip("mosquitto không khởi động được")
    yield port
    proc.kill()


@pytest.fixture()
def live_app(tmp_path, monkeypatch, broker):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'it.db').as_posix()}")
    monkeypatch.setenv("MQTT_ENABLED", "true")
    monkeypatch.setenv("MQTT_HOST", "127.0.0.1")
    monkeypatch.setenv("MQTT_PORT", str(broker))
    monkeypatch.setenv("MQTT_USER", "")
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_TOKEN", "")
    monkeypatch.setenv("USE_OPEN_METEO", "false")
    from app.core.config import get_settings
    get_settings.cache_clear()
    from app.db import session
    session.init_engine(os.environ["DATABASE_URL"])
    from fastapi.testclient import TestClient
    from app.main import app
    from app.runtime import rt
    with TestClient(app) as c:
        assert wait_until(lambda: rt().mqtt.stats["connected"], 10)
        yield c, broker
    get_settings.cache_clear()


def device_client(port, dev="itdev01", will=True):
    c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=dev)
    if will:
        c.will_set(f"vku/aiot/{dev}/status", json.dumps({"state": "offline"}), qos=1, retain=True)
    c.connect("127.0.0.1", port, keepalive=2)
    c.loop_start()
    return c


def test_end_to_end_ingest_alert_cmd_and_lwt(live_app):
    client, port = live_app
    dev = device_client(port)
    got_cmd = []
    dev.on_message = lambda c, u, m: got_cmd.append(json.loads(m.payload))
    dev.subscribe("vku/aiot/itdev01/cmd", qos=1)
    dev.publish("vku/aiot/itdev01/status", json.dumps({"state": "online", "rssi": -50}), qos=1, retain=True)
    now = int(time.time())
    for i in range(10):
        dev.publish("vku/aiot/itdev01/telemetry", json.dumps({"device_id": "itdev01", "ts": now - 10 + i, "seq": i + 1,
                                                              "temp_dht": 28.0, "hum": 80, "gas_ppm": 5.0}), qos=1)
    dev.publish("vku/aiot/itdev01/telemetry", json.dumps({"device_id": "itdev01", "ts": now - 1, "seq": 10,
                                                          "temp_dht": 28.0}), qos=1)
    rows = wait_until(lambda: len(client.get("/api/telemetry", params={"device_id": "itdev01"}).json()) >= 10 and
                      client.get("/api/telemetry", params={"device_id": "itdev01"}).json())
    assert len(rows) == 10
    t_pub = time.time()
    dev.publish("vku/aiot/itdev01/alert", json.dumps({"device_id": "itdev01", "ts": int(t_pub), "seq": 100, "level": 2,
                                                      "prev_level": 0, "cause": ["gas_ppm>1000"], "gas_ppm": 1300}), qos=1)
    al = wait_until(lambda: client.get("/api/alerts", params={"device_id": "itdev01", "min_level": 2}).json())
    assert al and al[0]["level"] == 2
    assert time.time() - t_pub < 5
    tok = client.post("/api/auth/token", data={"username": "admin", "password": "admin123"}).json()["access_token"]
    client.post("/api/devices/itdev01/cmd", json={"cmd": "mute"}, headers={"Authorization": f"Bearer {tok}"})
    assert wait_until(lambda: got_cmd)[0]["cmd"] == "mute"
    assert client.get("/api/devices/itdev01").json()["status"] == "online"
    dev._sock.close()
    dev.loop_stop()
    st = wait_until(lambda: client.get("/api/devices/itdev01").json()["status"] == "offline", 15)
    assert st
    types = [a["type"] for a in client.get("/api/alerts", params={"device_id": "itdev01"}).json()]
    assert "device_offline" in types
