# Điều phối trạm: nối cảm biến -> Edge AI -> cảnh báo -> bản tin MQTT, xử lý lệnh/cấu hình từ cloud.
# Không import phần cứng (machine/network): phần cứng được truyền vào qua đối tượng `hw` và `link`,
# nhờ đó toàn bộ luồng xử lý chạy được trong pytest trên PC.
#
#   Luồng chính  : sample_step() mỗi 1 s (cảm biến -> edge -> còi/LED), actuator_states() mỗi ~50 ms.
#   Luồng mạng   : net_step() — gửi hàng đợi, gửi bù đệm offline, status, hiệu chuẩn, OTA, khởi động lại.
#   Cảnh báo tại edge KHÔNG phụ thuộc mạng: luồng chính tự điều khiển còi/LED.
import json

import config
import gas_model
import payloads
from alert import (BUZZER_CONTINUOUS, BUZZER_INTERMITTENT, CAUSE_CLOUD, CAUSE_TEST, LED_GREEN, LED_RED_BLINK,
                   LED_RED_SOLID, LED_YELLOW, Actions, AlertManager, cause_list)
from compat import allocate_lock, epoch, has_time, isnan, local_tm, ticks_diff, ticks_ms
from edge_ai import MODE_NAMES, EdgeAI, EdgeOutput, mq2_calibrate_r0
from nowcast import Nowcast, NowcastEngine
from readings import SensorData, SensorProcessor


class Outbox:
    """Hàng đợi bản tin từ luồng chính sang luồng mạng (có khoá). Đầy -> bản tin cần lưu được ghi vào đệm offline."""

    def __init__(self, storage, maxlen=config.OUTBOX_MAX):
        self.q = []
        self.maxlen = maxlen
        self.lock = allocate_lock()
        self.storage = storage

    def put(self, suffix, payload, retain=False, buffer=False):
        with self.lock:
            if len(self.q) < self.maxlen:
                self.q.append((suffix, payload, retain, buffer))
                return True
        if buffer:
            self.storage.append(suffix, payload)
        return False

    def pop(self):
        with self.lock:
            return self.q.pop(0) if self.q else None

    def __len__(self):
        return len(self.q)


class DisplayState:
    def __init__(self):
        self.s = SensorData()
        self.level = 0
        self.muted = False
        self.wifi = False
        self.mqtt = False
        self.warming_up = True
        self.score = 0.0
        self.nc = Nowcast()
        self.cloud_forecast = ""


class Station:
    def __init__(self, storage, hw=None):
        self.storage = storage
        self.hw = hw
        self.cfg = storage.load_config()
        self.proc = SensorProcessor()
        self.proc.mq2.r0_kohm = self.cfg.r0_kohm
        self.edge = EdgeAI(warmup_samples=config.MQ2_WARMUP_S)
        self.alerts = AlertManager(config.MUTE_DURATION_MS)
        self.nowcaster = NowcastEngine()
        self.outbox = Outbox(storage)
        self.dstate = DisplayState()
        self.act = Actions()
        self.out = EdgeOutput()
        self.last_nowcast = Nowcast()
        self.cfg_lock = allocate_lock()
        # cờ do luồng mạng đặt, luồng chính xử lý
        self.flag_mute = self.flag_test = False
        self.flag_calibrate = self.flag_reboot = False
        self.flag_config_changed = True
        self.cloud_level = 0
        self.ota_url = None
        self.last_tel = self.last_now = None
        self.nc_restored = False
        self.was_testing = False
        self.prev_fault = 0
        self.last_status = None
        self.was_connected = False
        self.heartbeat = ticks_ms()  # luồng mạng cập nhật; luồng chính kiểm tra trước khi cho chó canh ăn

    # ================================================================ lệnh từ cloud (luồng mạng)
    def send_ack(self, ref, cmd_id, ok, msg):
        self.outbox.put("ack", payloads.ack(ref, cmd_id, ok, msg, epoch() if has_time() else 0))

    def apply_config(self, j):
        c = self.cfg.copy()
        try:
            c.update_from(j)
            mode = j.get("mode", "")
            if mode in MODE_NAMES:
                c.edge_mode = MODE_NAMES.index(mode)
            c.version = int(j.get("version", self.cfg.version + 1))
        except (TypeError, ValueError):
            self.send_ack("config", None, False, "invalid values")
            return False
        if not c.valid():
            self.send_ack("config", None, False, "invalid ranges")
            return False
        with self.cfg_lock:
            self.cfg = c
            self.flag_config_changed = True
        self.storage.save_config(c)
        self.send_ack("config", None, True, "config v%d applied" % c.version)
        return True

    def on_message(self, suffix, payload):
        try:
            j = json.loads(payload)
            if not isinstance(j, dict):
                raise ValueError
        except ValueError:
            self.send_ack(suffix, None, False, "bad json")
            return
        if suffix == "cmd":
            cmd = j.get("cmd", "")
            cmd_id = j.get("id", "")
            if cmd == "mute":
                self.flag_mute = True
            elif cmd == "test_alarm":
                self.flag_test = True
            elif cmd == "calibrate":
                self.flag_calibrate = True
            elif cmd == "reboot":
                self.flag_reboot = True
            elif cmd == "escalate":
                try:
                    self.cloud_level = min(max(int(j.get("level", 0)), 0), 3)
                except (TypeError, ValueError):
                    self.cloud_level = 0
            elif cmd == "ota":  # {"cmd":"ota","url":"http://host/ota/manifest.json"} (xem firmware/deploy.py --ota)
                url = j.get("url", "")
                if not (isinstance(url, str) and (url.startswith("http://") or url.startswith("https://"))):
                    self.send_ack("cmd", cmd_id, False, "bad url")
                    return
                self.ota_url = url
            else:
                self.send_ack("cmd", cmd_id, False, "unknown cmd")
                return
            self.send_ack("cmd", cmd_id, True, cmd)
        elif suffix == "config":
            self.apply_config(j)
        elif suffix == "forecast":
            s = j.get("summary", "")
            self.dstate.cloud_forecast = s[:60] if isinstance(s, str) else ""

    # ================================================================ xử lý 1 mẫu (luồng chính)
    def _publish_nowcast(self, ts):
        self.outbox.put("nowcast", payloads.nowcast(self.last_nowcast, ts, self.nowcaster.samples()), retain=True)

    def _compute_nowcast(self, d):
        month = local_tm(tz_h=config.TZ_HOURS)[1] if has_time() else 11
        self.last_nowcast = self.nowcaster.compute(d.rain_level, 70.0 if isnan(d.hum) else d.hum, month)

    def sample_step(self, raw, now):
        """raw: readings.RawSample đọc trong chu kỳ này; now: ticks_ms()."""
        if self.flag_config_changed:
            with self.cfg_lock:
                self.edge.rules.cfg = self.cfg.rule.copy()
                self.edge.mode = self.cfg.edge_mode
                self.proc.mq2.r0_kohm = self.cfg.r0_kohm
                self.flag_config_changed = False
        if self.flag_mute:
            self.alerts.press_mute(now)
            self.flag_mute = False
        if self.flag_test:
            self.alerts.test_alarm(now)
            self.flag_test = False
        if self.cloud_level > 0:
            self.alerts.cloud_escalate(self.cloud_level, now)
            self.cloud_level = 0

        ts = epoch() if has_time() else 0  # 0 = chưa có NTP -> backend gán giờ nhận
        d = self.proc.process(raw, ts)
        o = self.edge.step(d.mq2.ppm, d.mq2.ratio, 25.0 if isnan(d.temp) else d.temp,
                           70.0 if isnan(d.hum) else d.hum, 0.0 if isnan(d.lux) else d.lux, d.gas_ok)
        act = self.alerts.update(o.level, now)
        self.out, self.act = o, act

        if act.level_changed:
            is_test = act.testing or self.was_testing
            if is_test:
                cause = CAUSE_TEST
            else:
                cause = o.cause | (CAUSE_CLOUD if act.level > o.level else 0)
            self.outbox.put("alert", payloads.alert_gas(
                d, act, o, self.storage.next_seq(), is_test, cause_list(cause, self.edge.rules.cfg),
                ticks_diff(ticks_ms(), now)), buffer=True)
        self.was_testing = act.testing
        if d.gas_fault != self.prev_fault:
            self.outbox.put("alert", payloads.sensor_fault(d, act.level, self.storage.next_seq()), buffer=True)
            self.prev_fault = d.gas_fault

        period = config.TELEMETRY_ALERT_PERIOD_MS if act.level >= 1 else self.cfg.telemetry_ms
        if self.last_tel is None or ticks_diff(now, self.last_tel) >= period:
            self.last_tel = now
            self.outbox.put("telemetry", payloads.telemetry(d, act, o, self.storage.next_seq()), buffer=True)

        # Lần đầu có giờ NTP sau khởi động: gán giờ cho mẫu đã lấy, nạp lại mẫu đã lưu (≤ 3 giờ trước)
        # -> nowcast không phải chờ lại 1 giờ mỗi khi board khởi động lại.
        if not self.nc_restored and ts:
            self.nc_restored = True
            if self.nowcaster.samples() and self.last_now is not None:
                self.nowcaster.assign_times(ts - ticks_diff(now, self.last_now) // 1000)
            ps, tss = self.storage.load_nowcast()
            self.nowcaster.restore(ps, tss, ts)
            self._compute_nowcast(d)
            self._publish_nowcast(ts)  # mẫu đầu sau khởi động thường lấy lúc chưa có mạng -> gửi lại
            print("[NOWCAST] nap lai %d mau -> %d mau, %.1f gio" % (len(ps), self.nowcaster.samples(),
                                                                     self.nowcaster.span_hours()))
        # nowcast: 1 mẫu áp suất / 10 phút (mẫu đầu tiên ngay khi có dữ liệu)
        if not isnan(d.pressure_msl) and (self.last_now is None
                                          or ticks_diff(now, self.last_now) >= config.NOWCAST_SAMPLE_MS):
            self.last_now = now
            self.nowcaster.add_pressure(d.pressure_msl, ts)
            if ts:
                ps, tss = self.nowcaster.export_samples()
                self.storage.save_nowcast(ps, tss)
            self._compute_nowcast(d)
            self._publish_nowcast(ts)

        ds = self.dstate
        ds.s, ds.level, ds.muted, ds.score = d, act.level, act.muted, o.score
        ds.warming_up, ds.nc = o.warming_up, self.last_nowcast
        return d

    def actuator_states(self, now):
        """(xanh, vàng, đỏ, còi, relay) theo chế độ hiện tại. Logic cảnh báo giữ 4 trạng thái LED;
        chỉ ánh xạ ra phần cứng đang có ở đây."""
        a = self.act
        blink = (now // 250) % 2 == 1        # đỏ nháy 2 Hz (cấp 2)
        slow_blink = (now // 500) % 2 == 1   # xanh nháy 1 Hz (cấp 1 khi không có LED vàng)
        if config.HAS_LED_YELLOW:
            green, yellow = a.led == LED_GREEN, a.led == LED_YELLOW
        else:
            green, yellow = a.led == LED_GREEN or (a.led == LED_YELLOW and slow_blink), False
        red = a.led == LED_RED_SOLID or (a.led == LED_RED_BLINK and blink)
        buzz = a.buzzer == BUZZER_CONTINUOUS or (a.buzzer == BUZZER_INTERMITTENT and now % 1000 < 200)
        return green, yellow, red, buzz, a.relay

    # ================================================================ luồng mạng
    def status_info(self, link):
        info = {"ts": epoch() if has_time() else 0, "offline_pending": self.storage.pending(),
                "edge_mode": self.cfg.edge_mode, "config_ver": self.cfg.version,
                "inference_us": self.edge.last_inference_us, "reconnects": link.reconnects, "rssi": link.rssi()}
        if self.hw:
            info.update(self.hw.sysinfo())
        return info

    def net_step(self, link, now):
        """Một vòng của luồng mạng. link: net.NetLink (hoặc giả lập trong test)."""
        self.heartbeat = now
        up = link.step(now)
        if up and not self.was_connected:
            self.last_status = None  # vừa kết nối lại -> gửi status ngay
        self.was_connected = up
        if self.flag_calibrate and self.hw:  # đo R0 trong không khí sạch (~5 s)
            self.flag_calibrate = False
            r0 = mq2_calibrate_r0(self.hw.mean_rs_kohm(self.proc.mq2), config.MQ2_CLEAN_AIR_RATIO)
            with self.cfg_lock:
                self.cfg.r0_kohm = r0
                self.flag_config_changed = True
            self.storage.save_config(self.cfg)
            self.send_ack("calibrate", None, True, "R0=%.2f kOhm" % r0)
        if self.ota_url and self.hw:  # tải bản cập nhật; thành công -> tự khởi động lại
            url, self.ota_url = self.ota_url, None
            link.publish("status", '{"state":"updating"}', True)
            ok, msg = self.hw.ota(url, self)
            self.send_ack("ota", None, ok, msg)
        if up and self.storage.pending():  # gửi bù dữ liệu đệm offline
            self.storage.replay(lambda t, p: link.publish(t, p), 20)
        while True:
            m = self.outbox.pop()
            if m is None:
                break
            suffix, payload, retain, buffer = m
            if not link.publish(suffix, payload, retain) and buffer:
                self.storage.append(suffix, payload)
        if up and (self.last_status is None or ticks_diff(now, self.last_status) >= config.STATUS_PERIOD_MS):
            self.last_status = now
            link.publish("status", payloads.status(self.status_info(link)), True)
        if self.flag_reboot and self.hw:
            link.publish("status", '{"state":"rebooting"}', True)
            self.hw.reset()
        self.dstate.wifi = link.wifi_connected()
        self.dstate.mqtt = link.connected()
        return up
