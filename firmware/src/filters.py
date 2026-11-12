# Bộ lọc tín hiệu thuần Python (không phụ thuộc phần cứng) — dùng chung cho firmware và test trên PC.
import math

from compat import isnan


class RingBuffer:
    """Vòng đệm kích thước cố định (cấp phát một lần)."""

    def __init__(self, n):
        self.n = n
        self.buf = [0.0] * n
        self.head = 0
        self.count = 0

    def push(self, v):
        self.buf[self.head] = v
        self.head = (self.head + 1) % self.n
        if self.count < self.n:
            self.count += 1

    def size(self):
        return self.count

    def full(self):
        return self.count == self.n

    def clear(self):
        self.head = self.count = 0

    def at(self, i):
        """Phần tử thứ i tính từ cũ nhất (0) đến mới nhất (size()-1)."""
        return self.buf[(self.head + self.n - self.count + i) % self.n]

    def last(self):
        return self.at(self.count - 1)

    def mean(self):
        if not self.count:
            return 0.0
        s = 0.0
        for i in range(self.count):
            s += self.at(i)
        return s / self.count

    def stdev(self):
        """Độ lệch chuẩn tổng thể (chia n) — giống np.std."""
        if self.count < 2:
            return 0.0
        m = self.mean()
        s = 0.0
        for i in range(self.count):
            d = self.at(i) - m
            s += d * d
        return math.sqrt(s / self.count)

    def slope(self, n=None):
        """Độ dốc bình phương tối thiểu của n phần tử mới nhất (đơn vị: giá trị / mẫu)."""
        if n is None or n > self.count:
            n = self.count
        if n < 2:
            return 0.0
        start = self.count - n
        tm = (n - 1) / 2.0
        ym = 0.0
        for i in range(n):
            ym += self.at(start + i)
        ym /= n
        num = den = 0.0
        for i in range(n):
            tc = i - tm
            num += tc * (self.at(start + i) - ym)
            den += tc * tc
        return num / den


class Median5:
    """Median cửa sổ 5 — loại bỏ spike đơn lẻ."""

    def __init__(self):
        self.w = [0.0] * 5
        self.n = 0
        self.i = 0

    def update(self, v):
        self.w[self.i] = v
        self.i = (self.i + 1) % 5
        if self.n < 5:
            self.n += 1
        s = sorted(self.w[:self.n])
        return s[self.n // 2]

    def reset(self):
        self.n = 0


class Ewma:
    """EWMA: s_t = α·x_t + (1 − α)·s_{t−1}"""

    def __init__(self, alpha=0.25):
        self.a = alpha
        self.s = 0.0
        self.init = False

    def update(self, v):
        if not self.init:
            self.s = v
            self.init = True
        else:
            self.s = self.a * v + (1 - self.a) * self.s
        return self.s

    def value(self):
        return self.s


class SensorFilter:
    """Median-5 rồi EWMA (task.md 6.2). Giá trị NaN/None bị bỏ qua."""

    def __init__(self, alpha=0.25):
        self.med = Median5()
        self.ewma = Ewma(alpha)

    def update(self, v):
        if isnan(v):
            return self.ewma.value()
        return self.ewma.update(self.med.update(v))

    def value(self):
        return self.ewma.value()


def dew_point(t, rh):
    """Magnus: γ = ln(RH/100) + a·T/(b+T),  Td = b·γ/(a−γ)"""
    a, b = 17.62, 243.12
    if rh < 0.001:
        rh = 0.001
    g = math.log(rh / 100.0) + a * t / (b + t)
    return b * g / (a - g)


def heat_index(t, rh):
    """NOAA Rothfusz, trả về °C."""
    if t < 27.0:
        return t
    T = t * 9.0 / 5.0 + 32.0
    R = rh
    hi = (-42.379 + 2.04901523 * T + 10.14333127 * R - 0.22475541 * T * R - 6.83783e-3 * T * T
          - 5.481717e-2 * R * R + 1.22874e-3 * T * T * R + 8.5282e-4 * T * R * R - 1.99e-6 * T * T * R * R)
    return (hi - 32.0) * 5.0 / 9.0


def sea_level_pressure(p, t, h):
    """P0 = P·(1 − 0.0065·h/(T + 0.0065·h + 273.15))^(−5.257)"""
    return p * math.pow(1.0 - 0.0065 * h / (t + 0.0065 * h + 273.15), -5.257)
