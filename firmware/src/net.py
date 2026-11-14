import config
from compat import has_time, ticks_diff, ticks_ms
from mqtt import MQTTClient

try:
    import network
except ImportError:
    network = None


class NetLink:
    def __init__(self, ssid, password, host, port, user, mqtt_pass, device_id=config.DEVICE_ID,
                 on_message=None, ssl_context=None, client_suffix=""):
        self.ssid, self.password = ssid, password
        self.prefix = config.TOPIC_PREFIX + device_id + "/"
        self.on_message = on_message
        self.wlan = None
        if network is not None:
            self.wlan = network.WLAN(network.STA_IF)
            self.wlan.active(True)
            try:
                self.wlan.config(pm=0)
            except (ValueError, OSError, AttributeError):
                pass
        self.client = MQTTClient(device_id + client_suffix, host, port, user, mqtt_pass, keepalive=15,
                                 ssl_context=ssl_context, timeout_s=5)
        self.client.set_last_will(self.prefix + "status", '{"state":"offline"}', retain=True, qos=1)
        self.client.set_callback(self._on_mqtt)
        self.mqtt_up = False
        self.backoff = 2000
        self.last_try = None
        self.last_wifi_try = None
        self.last_ntp_try = None
        self.reconnects = 0

    def wifi_connected(self):
        return True if self.wlan is None else self.wlan.isconnected()

    def rssi(self):
        if self.wlan is None or not self.wlan.isconnected():
            return 0
        try:
            return self.wlan.status("rssi")
        except (ValueError, OSError):
            return 0

    def _ensure_wifi(self, now):
        if self.wifi_connected():
            return True
        if self.last_wifi_try is None or ticks_diff(now, self.last_wifi_try) > 15000:
            self.last_wifi_try = now
            try:
                self.wlan.disconnect()
            except OSError:
                pass
            try:
                self.wlan.connect(self.ssid, self.password)
                print("[WIFI] dang ket noi", self.ssid)
            except OSError as e:
                print("[WIFI] loi", e)
        return False

    def _ensure_time(self, now):
        if has_time() or (self.last_ntp_try is not None and ticks_diff(now, self.last_ntp_try) < 60000):
            return
        self.last_ntp_try = now
        try:
            import ntptime
        except ImportError:
            return
        for host in config.NTP_SERVERS:
            try:
                ntptime.host = host
                ntptime.timeout = 2
                ntptime.settime()
                print("[NTP] da dong bo gio tu", host)
                return
            except Exception as e:
                print("[NTP]", host, "loi", e)

    def _on_mqtt(self, topic, payload):
        if self.on_message and topic.startswith(self.prefix):
            try:
                self.on_message(topic[len(self.prefix):], payload)
            except Exception as e:
                print("[MQTT] loi xu ly", topic, e)

    def _connect_mqtt(self):
        self.client.connect()
        for t in ("cmd", "config", "forecast"):
            self.client.subscribe(self.prefix + t, 1)
        self.reconnects += 1
        self.backoff = 2000
        print("[MQTT] da ket noi")

    def connected(self):
        return self.mqtt_up and self.wifi_connected()

    def step(self, now):
        if not self._ensure_wifi(now):
            self._drop()
            return False
        self._ensure_time(now)
        if not self.mqtt_up:
            if self.last_try is not None and ticks_diff(now, self.last_try) < self.backoff:
                return False
            self.last_try = now
            try:
                self._connect_mqtt()
                self.mqtt_up = True
            except Exception as e:
                self.client.close()
                self.backoff = min(self.backoff * 2, 30000)
                print("[MQTT] ket noi that bai (%s), thu lai sau %d ms" % (e, self.backoff))
                return False
        try:
            self.client.check_msg()
        except Exception as e:
            print("[MQTT] mat ket noi:", e)
            self._drop()
            return False
        return True

    def _drop(self):
        if self.mqtt_up:
            self.client.close()
        self.mqtt_up = False

    def publish(self, suffix, payload, retain=False):
        if not self.connected():
            return False
        try:
            self.client.publish(self.prefix + suffix, payload, retain)
            return True
        except Exception as e:
            print("[MQTT] publish loi:", e)
            self._drop()
            return False
