import socket
import struct

from compat import ticks_diff, ticks_ms

_WOULD_BLOCK = (11, 35, 115, 10035)
_TIMEOUT = (110, 116, 10060)


class MQTTException(Exception):
    pass


def _would_block(e):
    if e.__class__.__name__ in ("BlockingIOError", "timeout", "TimeoutError"):
        return True
    return bool(e.args) and e.args[0] in _WOULD_BLOCK + _TIMEOUT


def _str(s):
    b = s.encode() if isinstance(s, str) else bytes(s)
    return struct.pack("!H", len(b)) + b


def _varlen(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | 0x80 if n else b)
        if not n:
            return bytes(out)


class MQTTClient:
    def __init__(self, client_id, server, port=1883, user=None, password=None, keepalive=15,
                 ssl_context=None, timeout_s=5):
        self.client_id = client_id
        self.server, self.port = server, port
        self.user, self.password = user, password
        self.keepalive = keepalive
        self.ssl_context = ssl_context
        self.timeout_s = timeout_s
        self.sock = None
        self.cb = None
        self.lw = None
        self.pid = 0
        self.last_tx = self.last_rx = 0

    def set_callback(self, f):
        self.cb = f

    def set_last_will(self, topic, msg, retain=False, qos=0):
        self.lw = (topic, msg, retain, qos)

    def _send(self, data):
        mv = memoryview(data)
        sent = 0
        while sent < len(data):
            n = self.sock.write(mv[sent:]) if hasattr(self.sock, "write") else self.sock.send(mv[sent:])
            if n is None:
                n = 0
            sent += n
        self.last_tx = ticks_ms()

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.read(n - len(buf)) if hasattr(self.sock, "read") else self.sock.recv(n - len(buf))
            if chunk is None:
                raise OSError(11)
            if not chunk:
                raise MQTTException("socket closed")
            buf += chunk
        return buf

    def _read_varlen(self):
        n = sh = 0
        while True:
            b = self._recv_exact(1)[0]
            n |= (b & 0x7F) << sh
            if not b & 0x80:
                return n
            sh += 7

    def _packet(self, header, body):
        self._send(bytes([header]) + _varlen(len(body)) + body)

    def connect(self, clean_session=True):
        addr = socket.getaddrinfo(self.server, self.port)[0][-1]
        s = socket.socket()
        s.settimeout(self.timeout_s)
        try:
            s.connect(addr)
            if self.ssl_context is not None:
                s = self.ssl_context.wrap_socket(s, server_hostname=self.server)
        except Exception:
            s.close()
            raise
        self.sock = s
        flags = 0x02 if clean_session else 0
        payload = _str(self.client_id)
        if self.lw:
            topic, msg, retain, qos = self.lw
            flags |= 0x04 | (qos & 3) << 3 | (0x20 if retain else 0)
            payload += _str(topic) + _str(msg)
        if self.user is not None:
            flags |= 0x80
            payload += _str(self.user)
            if self.password is not None:
                flags |= 0x40
                payload += _str(self.password)
        body = _str("MQTT") + bytes([4, flags]) + struct.pack("!H", self.keepalive) + payload
        try:
            self._packet(0x10, body)
            resp = self._recv_exact(4)
        except Exception:
            self.close()
            raise
        if resp[0] != 0x20 or resp[3] != 0:
            self.close()
            raise MQTTException("CONNACK rc=%d" % resp[3])
        self.last_rx = ticks_ms()
        return resp[2] & 1

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None

    def disconnect(self):
        if self.sock:
            try:
                self._send(b"\xe0\x00")
            except Exception:
                pass
        self.close()

    def is_connected(self):
        return self.sock is not None

    def publish(self, topic, msg, retain=False):
        if isinstance(msg, str):
            msg = msg.encode()
        self._packet(0x30 | (1 if retain else 0), _str(topic) + msg)

    def subscribe(self, topic, qos=1):
        self.pid = self.pid % 65535 + 1
        pid = self.pid
        self._packet(0x82, struct.pack("!H", pid) + _str(topic) + bytes([qos]))
        while True:
            op = self.wait_msg()
            if op == 0x90:
                return
            if op is None:
                raise MQTTException("no SUBACK")

    def ping(self):
        self._send(b"\xc0\x00")

    def wait_msg(self):
        try:
            first = self._recv_exact(1)[0]
        except OSError as e:
            if _would_block(e):
                return None
            raise
        self.sock.settimeout(self.timeout_s)
        n = self._read_varlen()
        body = self._recv_exact(n) if n else b""
        self.last_rx = ticks_ms()
        op = first & 0xF0
        if op == 0x30:
            tl = struct.unpack("!H", body[:2])[0]
            topic = body[2:2 + tl].decode()
            pos = 2 + tl
            qos = (first >> 1) & 3
            if qos:
                pid = body[pos:pos + 2]
                pos += 2
                if qos == 1:
                    self._send(b"\x40\x02" + pid)
            if self.cb:
                self.cb(topic, body[pos:])
        return op

    def check_msg(self):
        if self.sock is None:
            raise MQTTException("not connected")
        while True:
            self.sock.settimeout(0)
            try:
                op = self.wait_msg()
            finally:
                if self.sock:
                    self.sock.settimeout(self.timeout_s)
            if op is None:
                break
        now = ticks_ms()
        if self.keepalive:
            if ticks_diff(now, self.last_tx) > self.keepalive * 500:
                self.ping()
            if ticks_diff(now, self.last_rx) > self.keepalive * 1500:
                self.close()
                raise MQTTException("keepalive timeout")
