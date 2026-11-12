# Đọc phần cứng cảm biến trên ESP32 (MicroPython): DHT22, BMP280, BH1750 (I2C), YL-83 và MQ-2 (ADC1).
# Chỉ lấy số đo thô; lọc/quy đổi nằm ở readings.py (thuần Python, test được trên PC).
import dht
from machine import ADC, I2C, Pin

import config
from compat import sleep_ms, ticks_diff
from drivers import BH1750, BMP280
from edge_ai import mq2_convert
from readings import RawSample


def _adc(pin):
    a = ADC(Pin(pin))
    a.atten(ADC.ATTN_11DB)  # đo tới ~3,1 V
    return a


class Sensors:
    def __init__(self):
        self.i2c = I2C(0, scl=Pin(config.PIN_I2C_SCL), sda=Pin(config.PIN_I2C_SDA), freq=100000, timeout=50000)
        found = self.i2c.scan()
        self.bmp = self.bh = None
        for addr in (config.BMP280_ADDR, 0x77):
            if addr in found:
                try:
                    self.bmp = BMP280(self.i2c, addr)
                    break
                except OSError:
                    pass
        if config.BH1750_ADDR in found:
            try:
                self.bh = BH1750(self.i2c, config.BH1750_ADDR)
            except OSError:
                pass
        self.dht = dht.DHT22(Pin(config.PIN_DHT))
        self.adc_gas = _adc(config.PIN_MQ2_AO)
        self.adc_rain = _adc(config.PIN_RAIN_AO)
        self.rain_pwr = Pin(config.PIN_RAIN_PWR, Pin.OUT, value=0)
        Pin(config.PIN_RAIN_DO, Pin.IN)
        Pin(config.PIN_MQ2_DO, Pin.IN)
        self.last_dht = None
        self.last_rain = None
        print("[SENS] I2C", [hex(a) for a in found], "BMP280:%d BH1750:%d" % (self.bmp is not None, self.bh is not None))

    def read_mv(self, adc, n=16):
        """Trung bình n mẫu; read_uv() dùng hệ số hiệu chỉnh eFuse của ESP32."""
        s = 0
        for _ in range(n):
            s += adc.read_uv()
        return s / n / 1000.0

    def read_raw(self, now):
        r = RawSample(bmp_present=self.bmp is not None, bh_present=self.bh is not None)
        # DHT22: tối đa 1 lần / 2 s
        if self.last_dht is None or ticks_diff(now, self.last_dht) >= config.DHT_PERIOD_MS:
            self.last_dht = now
            try:
                self.dht.measure()
                r.dht = (self.dht.temperature(), self.dht.humidity())
            except OSError:
                r.dht = "fail"
        if self.bmp:
            try:
                r.bmp = self.bmp.read()
                if r.bmp[1] is None:
                    r.bmp = None
            except OSError:
                r.bmp = None
        if self.bh:
            try:
                r.lux = self.bh.read()
            except OSError:
                r.lux = -1.0
        # YL-83: chỉ cấp nguồn khi đọc, mỗi 10 giây
        if self.last_rain is None or ticks_diff(now, self.last_rain) >= config.RAIN_PERIOD_MS:
            self.last_rain = now
            self.rain_pwr.value(1)
            sleep_ms(15)
            r.rain_mv = self.read_mv(self.adc_rain, 8)
            self.rain_pwr.value(0)
        r.gas_mv = self.read_mv(self.adc_gas, 16)
        return r

    def mean_rs_kohm(self, mq2_params, samples=50, feed=None):
        """Rs trung bình trong không khí sạch (lệnh calibrate, ~5 s)."""
        rs = 0.0
        for _ in range(samples):
            rs += mq2_convert(self.read_mv(self.adc_gas, 16), mq2_params).rs
            if feed:
                feed()
            sleep_ms(100)
        return rs / samples
