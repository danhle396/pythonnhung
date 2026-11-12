# Trạm AIoT VKU — ESP32 + MicroPython: thu thập cảm biến, Edge AI cảnh báo khí/khói 4 cấp, nowcast, MQTT, đệm offline.
#   Luồng chính : cảm biến 1 Hz -> Edge AI -> còi/LED (~20 lần/s) -> màn TFT (2 lần/s). Không phụ thuộc mạng.
#   Luồng mạng  : Wi-Fi, NTP, MQTT, gửi bù đệm offline, status, hiệu chuẩn R0, OTA.
#   Watchdog 30 s: luồng chính chỉ cho "chó canh" ăn khi luồng mạng còn sống (< 60 s) -> treo ở đâu cũng tự khởi động lại.
import gc
import sys

import _thread
import machine
from machine import Pin

import config
import gas_model
from compat import has_time, local_tm, sleep_ms, ticks_diff, ticks_ms
from station import Station
from storage import Storage

print("\n[BOOT] VKU AIoT Station fw", config.FW_VERSION, "model", gas_model.VERSION, "-", sys.implementation.name)


class Hardware:
    """Các thao tác phần cứng mà Station gọi từ luồng mạng."""

    def __init__(self, sensors, wdt):
        self.sensors = sensors
        self.wdt = wdt
        self.min_free = gc.mem_free()

    def sysinfo(self):
        gc.collect()
        free = gc.mem_free()
        self.min_free = min(self.min_free, free)
        return {"uptime_s": ticks_ms() // 1000, "free_heap": free, "min_free_heap": self.min_free,
                "reset_reason": machine.reset_cause()}

    def mean_rs_kohm(self, mq2_params):
        return self.sensors.mean_rs_kohm(mq2_params, 50, feed=self.feed)

    def feed(self):
        if self.wdt:
            self.wdt.feed()

    def ota(self, url, station):
        import ota
        try:
            ok, ver = ota.update(url, feed=self.feed)
        except Exception as e:
            return False, "ota failed: %s" % e
        print("[OTA] da cai ban", ver, "-> khoi dong lai")
        sleep_ms(300)
        machine.reset()
        return ok, ver

    def reset(self):
        sleep_ms(200)
        machine.reset()


def build_actuators():
    pins = {"green": Pin(config.PIN_LED_GREEN, Pin.OUT, value=0), "red": Pin(config.PIN_LED_RED, Pin.OUT, value=0),
            "buzz": Pin(config.PIN_BUZZER, Pin.OUT, value=1 if config.BUZZER_ACTIVE_LOW else 0)}  # còi tắt
    if config.HAS_LED_YELLOW:
        pins["yellow"] = Pin(config.PIN_LED_YELLOW, Pin.OUT, value=0)
    if config.HAS_RELAY:
        pins["relay"] = Pin(config.PIN_RELAY, Pin.OUT, value=0)
    return pins


def drive(pins, states):
    green, yellow, red, buzz, relay = states
    pins["green"].value(green)
    pins["red"].value(red)
    pins["buzz"].value(buzz != config.BUZZER_ACTIVE_LOW)
    if "yellow" in pins:
        pins["yellow"].value(yellow)
    if "relay" in pins:
        pins["relay"].value(relay)


def network_thread(station, link):
    while True:
        try:
            station.net_step(link, ticks_ms())
        except Exception as e:  # không để lỗi bất ngờ giết luồng mạng
            print("[NET] loi:", e)
            sys.print_exception(e)
        sleep_ms(20)


def main():
    pins = build_actuators()
    storage = Storage("")
    try:
        from sensors import Sensors
        sensors = Sensors()
    except Exception as e:
        print("[SENS] khong khoi tao duoc:", e)
        raise
    display = None
    try:
        from display import Display
        from st7735 import ST7735
        tft = ST7735(config.TFT_SPI_ID, config.PIN_TFT_SCK, config.PIN_TFT_MOSI, config.PIN_TFT_CS, config.PIN_TFT_DC,
                     config.TFT_SPI_HZ, config.TFT_TAB, config.TFT_ROTATION)
        display = Display(tft)
    except Exception as e:  # màn hình hỏng không được làm dừng cảnh báo
        print("[TFT] loi:", e)

    wdt = machine.WDT(timeout=config.WDT_TIMEOUT_MS)
    hw = Hardware(sensors, wdt)
    station = Station(storage, hw)

    try:
        import credentials as cred
    except ImportError:
        cred = None
        print("[NET] thieu credentials.py -> chay offline (chep credentials_example.py thanh credentials.py)")
    if cred:
        from net import NetLink
        ssl_ctx = None
        if getattr(cred, "MQTT_CA_FILE", None):
            import ssl
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_ctx.load_verify_locations(cafile=cred.MQTT_CA_FILE)
        link = NetLink(cred.WIFI_SSID, cred.WIFI_PASS, cred.MQTT_HOST, cred.MQTT_PORT, cred.MQTT_USER,
                       cred.MQTT_PASS, on_message=station.on_message, ssl_context=ssl_ctx,
                       client_suffix="-" + "".join("%02x" % b for b in machine.unique_id()[-3:]))
        _thread.stack_size(16 * 1024)
        _thread.start_new_thread(network_thread, (station, link))

    last_sample = last_disp = None
    while True:
        now = ticks_ms()
        if last_sample is None or ticks_diff(now, last_sample) >= config.SENSOR_PERIOD_MS:
            last_sample = now
            station.sample_step(sensors.read_raw(now), now)
        drive(pins, station.actuator_states(ticks_ms()))
        if display and (last_disp is None or ticks_diff(now, last_disp) >= config.DISPLAY_PERIOD_MS):
            last_disp = now
            clock = "%02d:%02d" % local_tm(tz_h=config.TZ_HOURS)[3:5] if has_time() else "--:--"
            try:
                display.render(station.dstate, now, clock)
            except Exception as e:
                print("[TFT] loi ve:", e)
        # luồng mạng còn sống (hoặc chạy offline) mới cho chó canh ăn
        if not cred or ticks_diff(now, station.heartbeat) < config.NET_STALL_MS:
            wdt.feed()
        sleep_ms(50)


main()
