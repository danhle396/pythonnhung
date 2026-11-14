import struct


def bmp280_compensate(adc_t, adc_p, cal):
    T1, T2, T3, P1, P2, P3, P4, P5, P6, P7, P8, P9 = cal
    var1 = (((adc_t >> 3) - (T1 << 1)) * T2) >> 11
    var2 = (((((adc_t >> 4) - T1) * ((adc_t >> 4) - T1)) >> 12) * T3) >> 14
    t_fine = var1 + var2
    t = ((t_fine * 5 + 128) >> 8) / 100.0
    var1 = t_fine - 128000
    var2 = var1 * var1 * P6
    var2 = var2 + ((var1 * P5) << 17)
    var2 = var2 + (P4 << 35)
    var1 = ((var1 * var1 * P3) >> 8) + ((var1 * P2) << 12)
    var1 = (((1 << 47) + var1) * P1) >> 33
    if var1 == 0:
        return t, None
    p = 1048576 - adc_p
    p = (((p << 31) - var2) * 3125) // var1
    var1 = (P9 * (p >> 13) * (p >> 13)) >> 25
    var2 = (P8 * p) >> 19
    p = ((p + var1 + var2) >> 8) + (P7 << 4)
    return t, p / 25600.0


class BMP280:
    CHIP_ID = 0x58

    def __init__(self, i2c, addr=0x76):
        self.i2c, self.addr = i2c, addr
        if self.i2c.readfrom_mem(addr, 0xD0, 1)[0] != self.CHIP_ID:
            raise OSError("khong phai BMP280")
        raw = self.i2c.readfrom_mem(addr, 0x88, 24)
        self.cal = struct.unpack("<HhhHhhhhhhhh", raw)
        self.i2c.writeto_mem(addr, 0xF5, bytes([0b100_100_00]))
        self.i2c.writeto_mem(addr, 0xF4, bytes([0b010_101_11]))

    def read(self):
        d = self.i2c.readfrom_mem(self.addr, 0xF7, 6)
        adc_p = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
        adc_t = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
        return bmp280_compensate(adc_t, adc_p, self.cal)


class BH1750:
    POWER_ON = 0x01
    CONT_HIGH_RES = 0x10

    def __init__(self, i2c, addr=0x23):
        self.i2c, self.addr = i2c, addr
        self.i2c.writeto(addr, bytes([self.POWER_ON]))
        self.i2c.writeto(addr, bytes([self.CONT_HIGH_RES]))

    def read(self):
        d = self.i2c.readfrom(self.addr, 2)
        return ((d[0] << 8) | d[1]) / 1.2
