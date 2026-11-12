"""MQTT client tự viết (giao thức kiểm tra bằng broker tối giản trong tiến trình + Mosquitto thật nếu có)
và kiểm tra toàn bộ firmware biên dịch được bằng mpy-cross (cú pháp MicroPython)."""
import os
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from mqtt import MQTTClient, _varlen

FW = Path(__file__).resolve().parents[1]


def _read_packet(conn):
    first = conn.recv(1)
    n = sh = 0
    while True:
        b = conn.recv(1)[0]
        n |= (b & 0x7F) << sh
        if not b & 0x80:
            break
        sh += 7
    body = b""
    while len(body) < n:
        body += conn.recv(n - len(body))
    return first[0], body


def test_varlen_encoding():
    assert _varlen(0) == b"\x00"
    assert _varlen(127) == b"\x7f"
    assert _varlen(128) == b"\x80\x01"
    assert _varlen(16383) == b"\xff\x7f"


def test_protocol_with_minimal_broker():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    seen = {}

    def broker():
        conn, _ = srv.accept()
        h, body = _read_packet(conn)  # CONNECT
        seen["connect"] = (h, body)
        conn.sendall(b"\x20\x02\x00\x00")
        h, body = _read_packet(conn)  # SUBSCRIBE
        pid = body[:2]
        conn.sendall(b"\x90\x03" + pid + b"\x01")
        topic, msg = b"vku/aiot/st/cmd", b'{"cmd":"mute"}'
        pkt = struct.pack("!H", len(topic)) + topic + b"\x00\x07" + msg
        conn.sendall(bytes([0x32]) + _varlen(len(pkt)) + pkt)  # PUBLISH QoS 1
        seen["puback"] = _read_packet(conn)
        seen["publish"] = _read_packet(conn)
        conn.close()

    th = threading.Thread(target=broker, daemon=True)
    th.start()
    got = []
    c = MQTTClient("st-1", "127.0.0.1", port, "station01", "pw", keepalive=15, timeout_s=2)
    c.set_last_will("vku/aiot/st/status", '{"state":"offline"}', retain=True, qos=1)
    c.set_callback(lambda t, p: got.append((t, p)))
    c.connect()
    c.subscribe("vku/aiot/st/cmd", 1)
    for _ in range(50):
        c.check_msg()
        if got:
            break
        time.sleep(0.02)
    c.publish("vku/aiot/st/telemetry", '{"x":1}', retain=True)
    th.join(3)
    c.close()
    h, body = seen["connect"]
    assert h == 0x10 and body[2:6] == b"MQTT" and body[6] == 4
    assert body[7] == 0x80 | 0x40 | 0x20 | 0x08 | 0x04 | 0x02  # user, pass, will retain, will QoS1, will, clean
    assert got == [("vku/aiot/st/cmd", b'{"cmd":"mute"}')]
    assert seen["puback"] == (0x40, b"\x00\x07")
    h, body = seen["publish"]
    assert h == 0x31 and body.endswith(b'{"x":1}')


def _mosquitto_up(port=1883):
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
        return True
    except OSError:
        return False


@pytest.mark.skipif(not _mosquitto_up(int(os.environ.get("MQTT_PORT", 1883))), reason="không có Mosquitto local")
def test_roundtrip_real_mosquitto():
    port = int(os.environ.get("MQTT_PORT", 1883))
    got = []
    sub = MQTTClient("fwtest-sub", "127.0.0.1", port, "backend", os.environ.get("MQTT_PASS", "backend-pass"))
    sub.set_callback(lambda t, p: got.append((t, p)))
    try:
        sub.connect()
    except Exception as e:
        pytest.skip(f"Mosquitto từ chối đăng nhập: {e}")
    sub.subscribe("vku/aiot/station01/telemetry", 1)
    pub = MQTTClient("fwtest-pub", "127.0.0.1", port, "station01", os.environ.get("MQTT_DEVICE_PASS", "change-me"))
    try:
        pub.connect()
    except Exception as e:
        pytest.skip(f"Mosquitto từ chối tài khoản thiết bị: {e}")
    pub.publish("vku/aiot/station01/telemetry", '{"probe":1}')
    for _ in range(100):
        sub.check_msg()
        if got:
            break
        time.sleep(0.02)
    pub.disconnect()
    sub.disconnect()
    assert got == [("vku/aiot/station01/telemetry", b'{"probe":1}')]


def test_all_firmware_compiles_for_micropython():
    pytest.importorskip("mpy_cross")
    r = subprocess.run([sys.executable, str(FW / "deploy.py"), "--check"], capture_output=True, text=True,
                       env={**os.environ, "PYTHONUTF8": "1"})
    assert r.returncode == 0, r.stdout + r.stderr


def test_no_c_sources_left():
    bad = [p for p in FW.rglob("*") if p.suffix in (".c", ".cpp", ".h", ".ino", ".ini") and "build" not in p.parts]
    assert not bad, bad


def test_gas_model_placeholder_or_real():
    import gas_model
    assert gas_model.N_FEATURES == 10 and len(gas_model.CLASS_LABEL) == gas_model.N_CLASSES
    k, p = gas_model.predict_proba([0.0] * 10)
    assert 0 <= k < gas_model.N_CLASSES and abs(sum(p) - 1.0) < 1e-5
    vec = FW / "tests" / "gas_model_testvec.json"
    if gas_model.AVAILABLE and vec.exists():  # vector kiểm thử do train_gas_edge sinh ra
        import json
        tv = json.loads(vec.read_text())
        bad = sum(gas_model.predict_proba(x)[0] != c for x, c in zip(tv["x"], tv["class_idx"]))
        assert bad == 0
