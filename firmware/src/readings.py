# Xử lý số đo thô từ driver (sensors.py) -> SensorData đã lọc. Thuần Python (test được trên PC).
import config
from compat import isnan, nan
from edge_ai import FAULT_NONE, Mq2FaultDetector, Mq2Params, Mq2Reading, mq2_convert
from filters import SensorFilter, dew_point, heat_index, sea_level_pressure


class RawSample:
    """Số đo thô một chu kỳ 1 giây. None = không đọc ở chu kỳ này; dht = (t, h), 'fail' hoặc None."""

    def __init__(self, dht=None, bmp=None, lux=None, rain_mv=None, gas_mv=0.0, bmp_present=False, bh_present=False):
        self.dht = dht
        self.bmp = bmp            # (t, p_hPa) hoặc None khi lỗi
        self.lux = lux
        self.rain_mv = rain_mv
        self.gas_mv = gas_mv
        self.bmp_present = bmp_present
        self.bh_present = bh_present


class SensorData:
    def __init__(self):
        self.ts = 0  # epoch (s), 0 nếu chưa có NTP
        self.temp_dht = self.hum = self.temp_bmp = self.pressure = self.pressure_msl = self.lux = nan()
        self.temp = nan()  # nhiệt độ dùng chung: DHT22, dự phòng BMP280
        self.dew = self.heat_index = nan()
        self.rain_mv = -1
        self.rain_level = 0
        self.gas_mv = nan()
        self.mq2 = Mq2Reading()
        self.dht_ok = self.bmp_ok = self.bh_ok = self.rain_ok = self.gas_ok = False
        self.gas_fault = FAULT_NONE


def rain_level_from_mv(mv):
    if mv >= config.RAIN_MV_DRY:
        return 0       # khô
    if mv >= config.RAIN_MV_DRIZZLE:
        return 1       # mưa phùn
    if mv >= config.RAIN_MV_MODERATE:
        return 2       # mưa vừa
    return 3           # mưa to


class SensorProcessor:
    def __init__(self, mq2=None):
        self.mq2 = mq2 or Mq2Params(config.MQ2_RL_KOHM, config.MQ2_VC, config.MQ2_DIVIDER,
                                    config.MQ2_R0_DEFAULT_KOHM, config.MQ2_CURVE_A, config.MQ2_CURVE_B)
        self.f_temp = SensorFilter(0.3)
        self.f_hum = SensorFilter(0.3)
        self.f_temp_bmp = SensorFilter(0.25)
        self.f_pres = SensorFilter(0.25)
        self.f_lux = SensorFilter(0.3)
        self.f_gas = SensorFilter(0.3)
        self.gas_fault = Mq2FaultDetector()
        self.last_temp_dht = self.last_hum = nan()
        self.last_rain_mv = -1
        self.rain_hist = [0] * config.RAIN_HOLD_READS  # mức mưa các lần đọc gần nhất (giữ trạng thái ướt)
        self.rain_idx = 0
        self.dht_fails = 0
        self.last_temp_bmp = self.last_pres = nan()
        self.last_lux = nan()

    def process(self, raw, ts=0):
        d = SensorData()
        d.ts = ts
        # ---- DHT22 (driver chỉ đọc 1 lần / 2 s)
        if raw.dht is not None:
            ok = raw.dht != "fail"
            if ok:
                t, h = raw.dht
                ok = (not isnan(t) and not isnan(h) and -20 < t < 70 and 0 <= h <= 100)
            if ok:
                self.last_temp_dht = self.f_temp.update(t)
                self.last_hum = self.f_hum.update(h)
                self.dht_fails = 0
            else:
                self.dht_fails += 1
                if self.dht_fails > 3:  # lỗi liên tiếp -> báo hỏng
                    self.last_temp_dht = self.last_hum = nan()
        d.temp_dht, d.hum = self.last_temp_dht, self.last_hum
        d.dht_ok = not isnan(d.temp_dht)

        # ---- BMP280
        if raw.bmp_present and raw.bmp is not None:
            t, p = raw.bmp
            d.bmp_ok = not isnan(p) and 800 < p < 1100
            if d.bmp_ok:
                self.last_temp_bmp = self.f_temp_bmp.update(t)
                self.last_pres = self.f_pres.update(p)
        if d.bmp_ok:
            d.temp_bmp, d.pressure = self.last_temp_bmp, self.last_pres
        # nhiệt độ dùng chung: ưu tiên DHT22, dự phòng BMP280 (task.md mục 16)
        d.temp = d.temp_dht if d.dht_ok else d.temp_bmp
        if d.bmp_ok and not isnan(d.temp):
            d.pressure_msl = sea_level_pressure(d.pressure, d.temp, config.STATION_ALT_M)
        if d.dht_ok:
            d.dew = dew_point(d.temp_dht, d.hum)
            d.heat_index = heat_index(d.temp_dht, d.hum)

        # ---- BH1750
        if raw.bh_present and raw.lux is not None:
            d.bh_ok = raw.lux >= 0
            if d.bh_ok:
                self.last_lux = self.f_lux.update(raw.lux)
                d.lux = self.last_lux

        # ---- YL-83 (driver chỉ cấp nguồn và đọc mỗi 10 s)
        if raw.rain_mv is not None:
            self.last_rain_mv = int(raw.rain_mv)
            self.rain_hist[self.rain_idx] = rain_level_from_mv(self.last_rain_mv)
            self.rain_idx = (self.rain_idx + 1) % len(self.rain_hist)
        d.rain_mv = self.last_rain_mv
        d.rain_level = max(self.rain_hist)
        d.rain_ok = self.last_rain_mv > 50  # 0 mV -> dây đứt

        # ---- MQ-2
        d.gas_fault = self.gas_fault.update(raw.gas_mv)
        d.gas_mv = self.f_gas.update(raw.gas_mv)
        d.mq2 = mq2_convert(d.gas_mv, self.mq2)
        d.gas_ok = d.gas_fault == FAULT_NONE
        return d
