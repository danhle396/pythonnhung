# Nowcast thời tiết tại edge kiểu Zambretti: xu hướng áp suất 3 giờ + mưa + độ ẩm. Thuần Python.

TREND_FALLING, TREND_STEADY, TREND_RISING, TREND_UNKNOWN = -1, 0, 1, 2
CODE_FINE, CODE_POSSIBLE_RAIN, CODE_RAIN_SOON, CODE_RAINING, CODE_UNKNOWN = 0, 1, 2, 3, 4

# (chữ ASCII cho màn TFT, chữ UTF-8 cho MQTT)
TEXTS = {
    CODE_FINE: ("Troi dep", "Trời đẹp"),
    CODE_POSSIBLE_RAIN: ("Co the mua", "Có thể mưa"),
    CODE_RAIN_SOON: ("Mua sap toi", "Mưa sắp tới"),
    CODE_RAINING: ("Dang mua", "Đang mưa"),
    CODE_UNKNOWN: ("Chua du du lieu", "Chưa đủ dữ liệu"),
}

# Bảng Zambretti (Negretti & Zambra, 1915) theo số Z:
#   giảm   : Z = 127 − 0.12·P  (1..9)
#   ổn định: Z = 144 − 0.13·P  (10..19)
#   tăng   : Z = 185 − 0.16·P  (20..32)
FALLING_MAP = "ABDHORUVX"      # Z 1..9
STEADY_MAP = "ABEKNPSWXZ"      # Z 10..19
RISING_MAP = "ABCFGIJLMQTYZ"   # Z 20..32


class Nowcast:
    def __init__(self):
        self.trend = TREND_UNKNOWN
        self.trend3h = 0.0  # hPa / 3h
        self.zambretti = "?"
        self.z_number = 0
        self.code = CODE_UNKNOWN

    @property
    def text(self):
        return TEXTS[self.code][0]

    @property
    def text_vi(self):
        return TEXTS[self.code][1]


def zambretti_letter(p, trend, month):
    """Trả về (chữ cái A..Z, số Z)."""
    if trend == TREND_FALLING:
        z, m, lo = int(127.0 - 0.12 * p + 0.5), FALLING_MAP, 1
    elif trend == TREND_RISING:
        z, m, lo = int(185.0 - 0.16 * p + 0.5), RISING_MAP, 20
    else:
        z, m, lo = int(144.0 - 0.13 * p + 0.5), STEADY_MAP, 10
    # hiệu chỉnh mùa: Đà Nẵng mùa mưa tháng 9–12 -> nghiêng về kém ổn định
    if 9 <= month <= 12 and trend != TREND_RISING:
        z += 1
    idx = min(max(z - lo, 0), len(m) - 1)
    return m[idx], lo + idx


class NowcastEngine:
    """Lưu tối đa 19 mẫu (3 giờ × 1 mẫu / 10 phút) kèm giờ đo (epoch, 0 = chưa có NTP).
    Có giờ đo -> xu hướng tính theo khoảng thời gian thật, nạp lại được mẫu đã lưu sau khi khởi động lại."""
    N = 19
    STEP_S = 600                 # 1 mẫu / 10 phút
    WINDOW_S = 3 * 3600 + 300    # giữ mẫu trong 3 giờ (+5 phút dung sai)
    TREND_THRESHOLD = 1.6        # hPa / 3h

    def __init__(self):
        self.p = []  # cũ -> mới
        self.t = []

    def samples(self):
        return len(self.p)

    def _push(self, p, t):
        if len(self.p) == self.N:  # đầy: bỏ mẫu cũ nhất
            self.p.pop(0)
            self.t.pop(0)
        self.p.append(p)
        self.t.append(t)

    def _prune(self, newest_ts):
        k = 0  # số mẫu quá cũ ở đầu
        while k < len(self.t) and self.t[k] != 0 and newest_ts - self.t[k] > self.WINDOW_S:
            k += 1
        if k:
            self.p = self.p[k:]
            self.t = self.t[k:]

    def add_pressure(self, p_msl, ts=0):
        """Gọi mỗi 10 phút với áp suất quy về mực nước biển (hPa) và giờ đo (0 nếu chưa có NTP)."""
        self._push(p_msl, ts)
        if ts:
            self._prune(ts)

    def timed(self):
        """Mọi mẫu đều có giờ đo."""
        return len(self.t) > 0 and all(t != 0 for t in self.t)

    def span_hours(self):
        n = len(self.p)
        if n < 2:
            return 0.0
        if self.timed():
            return (self.t[-1] - self.t[0]) / 3600.0
        return (n - 1) * (self.STEP_S / 3600.0)  # chưa có giờ: các mẫu cách đều 10 phút

    def assign_times(self, newest_ts):
        """Vừa có NTP: gán giờ cho các mẫu chưa có giờ (lấy đều 10 phút), mẫu mới nhất đo lúc newest_ts."""
        n = len(self.t)
        for i in range(n):
            if self.t[i] == 0:
                self.t[i] = newest_ts - (n - 1 - i) * self.STEP_S

    def restore(self, ps, ts, now_ts):
        """Nạp lại mẫu đã lưu từ trước khi khởi động lại: bỏ mẫu ngoài 3 giờ tính tới now_ts, gộp theo thời gian."""
        first = self.t[0] if self.t else now_ts + 1  # mẫu đã lưu phải cũ hơn mẫu hiện có (tránh trùng)
        merged = []
        for p, t in zip(ps, ts):
            if len(merged) >= self.N:
                break
            if t == 0 or t > now_ts or now_ts - t > self.WINDOW_S:
                continue
            if self.t and t + self.STEP_S // 2 > first:
                continue
            merged.append((t, p))
        for p, t in zip(self.p, self.t):
            merged.append((t, p))
        merged.sort(key=lambda x: x[0])
        self.p, self.t = [], []
        for t, p in merged[-self.N:]:
            self._push(p, t)
        self._prune(now_ts)

    def export_samples(self):
        """Các mẫu có giờ đo (cũ -> mới) để lưu: (danh sách áp suất, danh sách giờ)."""
        ps, ts = [], []
        for p, t in zip(self.p, self.t):
            if t:
                ps.append(p)
                ts.append(t)
        return ps, ts

    def compute(self, rain_level, hum, month):
        nc = Nowcast()
        if rain_level >= 1:
            nc.code = CODE_RAINING
        span_h = self.span_hours()
        if span_h < 0.99:  # cần ít nhất 1 giờ dữ liệu
            return nc
        # quy đổi xu hướng về 3 giờ nếu chưa đủ 3 giờ
        nc.trend3h = (self.p[-1] - self.p[0]) * 3.0 / span_h
        if nc.trend3h <= -self.TREND_THRESHOLD:
            nc.trend = TREND_FALLING
        elif nc.trend3h >= self.TREND_THRESHOLD:
            nc.trend = TREND_RISING
        else:
            nc.trend = TREND_STEADY
        nc.zambretti, nc.z_number = zambretti_letter(self.p[-1], nc.trend, month)
        c = nc.zambretti
        if c <= "D" or c == "F":
            code = CODE_FINE
        elif c <= "Q":
            code = CODE_POSSIBLE_RAIN
        else:
            code = CODE_RAIN_SOON
        if hum >= 90.0 and code == CODE_POSSIBLE_RAIN:
            code = CODE_RAIN_SOON
        if hum >= 85.0 and nc.trend == TREND_FALLING and code == CODE_FINE:
            code = CODE_POSSIBLE_RAIN
        if rain_level >= 1:
            code = CODE_RAINING
        nc.code = code
        return nc
