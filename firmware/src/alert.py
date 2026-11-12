# Rule engine cảnh báo khí 4 cấp + quản lý hành động (còi/LED/mute; relay tuỳ chọn). Thuần Python, test được trên PC.
# Logic GIỐNG HỆT ml/src/gas_edge.py (RuleEngine) để bản dùng khi huấn luyện/đánh giá phản ánh đúng thiết bị
# (ml/tests/test_edge_parity.py kiểm tra hai bản cho cùng kết quả).
from compat import ticks_add, ticks_diff

CAUSE_PPM_TH1 = 1 << 0
CAUSE_SLOPE = 1 << 1
CAUSE_PPM_TH2 = 1 << 2
CAUSE_PPM_TH3 = 1 << 3
CAUSE_TEMP_RISING = 1 << 4
CAUSE_MODEL = 1 << 5
CAUSE_SENSOR_FAULT = 1 << 6
CAUSE_CLOUD = 1 << 7
CAUSE_TEST = 1 << 8

# Chế độ LED / còi
LED_GREEN, LED_YELLOW, LED_RED_BLINK, LED_RED_SOLID, LED_OFF = 0, 1, 2, 3, 4
BUZZER_OFF, BUZZER_INTERMITTENT, BUZZER_CONTINUOUS = 0, 1, 2


class RuleConfig:
    def __init__(self, th1=300.0, th2=1000.0, th3=2000.0, slope1=15.0, dtemp3=1.0, hyst=0.15,
                 debounce_up=3, debounce_down=5):
        self.th1, self.th2, self.th3 = th1, th2, th3
        self.slope1 = slope1        # ppm/s
        self.dtemp3 = dtemp3        # °C/phút
        self.hyst = hyst
        self.debounce_up = debounce_up
        self.debounce_down = debounce_down

    def copy(self):
        return RuleConfig(self.th1, self.th2, self.th3, self.slope1, self.dtemp3, self.hyst,
                          self.debounce_up, self.debounce_down)


def cause_list(c, cfg):
    """Bit nguyên nhân -> danh sách chuỗi gửi lên cloud."""
    out = []
    if c & CAUSE_PPM_TH1:
        out.append("gas_ppm>%.0f" % cfg.th1)
    if c & CAUSE_SLOPE:
        out.append("slope_high")
    if c & CAUSE_PPM_TH2:
        out.append("gas_ppm>%.0f" % cfg.th2)
    if c & CAUSE_PPM_TH3:
        out.append("gas_ppm>%.0f" % cfg.th3)
    if c & CAUSE_TEMP_RISING:
        out.append("temp_rising")
    if c & CAUSE_MODEL:
        out.append("model")
    if c & CAUSE_CLOUD:
        out.append("cloud_escalation")
    if c & CAUSE_TEST:
        out.append("test_alarm")
    return out


class RuleEngine:
    def __init__(self, cfg=None):
        self.cfg = cfg or RuleConfig()
        self.level = 0
        self.up_cnt = 0
        self.down_cnt = 0
        self.cause = 0

    def raw_level(self, ppm, slope, dtemp, scale=1.0):
        """Trả về (cấp, bit nguyên nhân) khi so với ngưỡng × scale."""
        c = self.cfg
        cause = 0
        lvl = 0
        if ppm >= c.th1 * scale:
            lvl = 1
            cause |= CAUSE_PPM_TH1
        if slope >= c.slope1 * scale:
            if lvl < 1:
                lvl = 1
            cause |= CAUSE_SLOPE
        if ppm >= c.th2 * scale:
            lvl = 2
            cause |= CAUSE_PPM_TH2
        if ppm >= c.th3 * scale:
            lvl = 3
            cause |= CAUSE_PPM_TH3
        elif lvl >= 2 and dtemp >= c.dtemp3:
            lvl = 3
            cause |= CAUSE_TEMP_RISING
        return lvl, cause

    def update(self, ppm, slope, dtemp):
        up, c = self.raw_level(ppm, slope, dtemp, 1.0)
        if up > self.level:
            self.down_cnt = 0
            if up == 3:  # cấp Nguy hiểm: tăng ngay, không debounce
                self.level, self.up_cnt, self.cause = 3, 0, c
            else:
                self.up_cnt += 1
                if self.up_cnt >= self.cfg.debounce_up:
                    self.level, self.up_cnt, self.cause = up, 0, c
            return self.level
        self.up_cnt = 0
        down, _ = self.raw_level(ppm, slope, dtemp, 1.0 - self.cfg.hyst)
        if down < self.level:
            self.down_cnt += 1
            if self.down_cnt >= self.cfg.debounce_down:
                self.level, self.down_cnt = down, 0
                if down == 0:
                    self.cause = 0
        else:
            self.down_cnt = 0
        return self.level

    def reset(self):
        self.level = self.up_cnt = self.down_cnt = 0
        self.cause = 0


class Actions:
    def __init__(self):
        self.led = LED_GREEN
        self.buzzer = BUZZER_OFF
        self.relay = False
        self.level_changed = False
        self.level = 0
        self.prev_level = 0
        self.muted = False
        self.testing = False  # đang thử còi (cmd test_alarm), không phải sự cố khí


def _active(now, until):
    return until is not None and ticks_diff(until, now) > 0


class AlertManager:
    """Cấp cảnh báo đầu ra + tắt còi (lệnh mute từ dashboard, task.md 6.3): mute tắt còi 5 phút nhưng giữ cấp và LED;
    nếu cấp tăng thêm thì còi kêu lại. Cloud có thể nâng cấp (cmd escalate) — không bao giờ hạ cấp edge.
    Mốc thời gian hết hạn được xoá (None) ngay khi qua để không bị sai khi bộ đếm ticks quay vòng."""

    def __init__(self, mute_ms=300000):
        self.mute_ms = mute_ms
        self.level = 0
        self.muted_level = -1
        self.muted_until = None
        self.cloud_level = 0
        self.cloud_until = None
        self.test_until = None

    def press_mute(self, now):
        if self.level >= 1:
            self.muted_level = self.level
            self.muted_until = ticks_add(now, self.mute_ms)

    def cloud_escalate(self, level, now, hold_ms=60000):
        self.cloud_level = level
        self.cloud_until = ticks_add(now, hold_ms)

    def test_alarm(self, now, dur_ms=3000):
        self.test_until = ticks_add(now, dur_ms)

    def update(self, edge_level, now):
        a = Actions()
        lvl = edge_level
        if _active(now, self.cloud_until):
            if self.cloud_level > lvl:
                lvl = self.cloud_level  # cloud chỉ được nâng cấp
        else:
            self.cloud_until = None
        testing = _active(now, self.test_until)
        if not testing:
            self.test_until = None
        if testing:
            lvl = 3
        a.testing = testing
        a.prev_level = self.level
        a.level_changed = lvl != self.level
        self.level = lvl
        a.level = lvl
        # mute hết hạn hoặc cấp tăng vượt cấp đã mute -> còi kêu lại
        muted = self.muted_level >= 0 and _active(now, self.muted_until) and lvl <= self.muted_level and not testing
        if not muted:
            self.muted_level = -1
            self.muted_until = None
        a.muted = muted
        if lvl == 0:
            a.led = LED_GREEN
        elif lvl == 1:
            a.led = LED_YELLOW
        elif lvl == 2:
            a.led, a.buzzer, a.relay = LED_RED_BLINK, BUZZER_INTERMITTENT, True
        else:
            a.led, a.buzzer, a.relay = LED_RED_SOLID, BUZZER_CONTINUOUS, True
        if muted:
            a.buzzer = BUZZER_OFF
        return a
