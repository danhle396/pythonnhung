"""Driver BMP280/BH1750 (I2C giả lập bằng bảng thanh ghi), đệm offline, cấu hình, seq, mẫu nowcast."""
import struct

import pytest

from drivers import BH1750, BMP280, bmp280_compensate
from storage import DeviceConfig, Storage

# Ví dụ bù trừ trong datasheet Bosch BMP280 (BST-BMP280-DS001, bảng 16)
CAL = (27504, 26435, -1000, 36477, -10685, 3024, 2855, 140, -7, 15500, -14600, 6000)


def test_bmp280_compensation_datasheet_example():
    t, p = bmp280_compensate(519888, 415148, CAL)
    assert t == pytest.approx(25.08, abs=0.01)
    assert p * 100 == pytest.approx(100653.27, abs=0.05)  # Pa (công thức số nguyên: 100653,25)


class FakeI2C:
    def __init__(self, regs):
        self.regs = regs
        self.writes = []

    def readfrom_mem(self, addr, reg, n):
        return bytes(self.regs[reg + i] for i in range(n))

    def writeto_mem(self, addr, reg, data):
        self.writes.append((reg, bytes(data)))

    def writeto(self, addr, data):
        self.writes.append((None, bytes(data)))

    def readfrom(self, addr, n):
        return bytes([0x01, 0x2C])  # 300 -> 250 lx


def test_bmp280_driver_reads_and_configures():
    regs = {0xD0: 0x58}
    for i, b in enumerate(struct.pack("<HhhHhhhhhhhh", *CAL)):
        regs[0x88 + i] = b
    adc_p, adc_t = 415148, 519888
    raw = [adc_p >> 12, (adc_p >> 4) & 0xFF, (adc_p & 0xF) << 4, adc_t >> 12, (adc_t >> 4) & 0xFF, (adc_t & 0xF) << 4]
    for i, b in enumerate(raw):
        regs[0xF7 + i] = b
    i2c = FakeI2C(regs)
    s = BMP280(i2c, 0x76)
    assert (0xF4, bytes([0x57])) in i2c.writes  # normal mode, áp suất ×16, nhiệt ×2
    t, p = s.read()
    assert t == pytest.approx(25.08, abs=0.01) and p == pytest.approx(1006.53, abs=0.01)


def test_bh1750_lux():
    assert BH1750(FakeI2C({}), 0x23).read() == pytest.approx(250.0)


def test_offline_buffer_rotation_and_replay(tmp_path):
    st = Storage(str(tmp_path), max_records=10)  # 2 file × 5 bản ghi
    for i in range(12):
        assert st.append("telemetry", '{"seq":%d}' % i)
    assert st.pending() == 7  # bản ghi 0..4 bị bỏ khi xoay vòng lần 2
    got = []
    assert st.replay(lambda t, p: got.append(p) or True, max_records=3) == 3
    assert got == ['{"seq":5}', '{"seq":6}', '{"seq":7}']
    assert st.pending() == 4
    # gửi lỗi giữa chừng -> giữ lại phần chưa gửi, đúng thứ tự
    calls = []

    def flaky(t, p):
        calls.append(p)
        return len(calls) < 2

    assert st.replay(flaky) == 1
    assert st.pending() == 3
    st2 = Storage(str(tmp_path), max_records=10)  # khởi động lại: đếm lại từ file
    assert st2.pending() == 3
    rest = []
    st2.replay(lambda t, p: rest.append((t, p)) or True)
    assert rest == [("telemetry", '{"seq":9}'), ("telemetry", '{"seq":10}'), ("telemetry", '{"seq":11}')]
    assert st2.pending() == 0


def test_seq_survives_reboot_and_config_roundtrip(tmp_path):
    a = Storage(str(tmp_path))
    seqs = [a.next_seq() for _ in range(3)]
    assert seqs == [1, 2, 3]
    b = Storage(str(tmp_path))
    assert b.next_seq() > 3  # nhảy cóc tối đa 100, không bao giờ lặp lại
    c = DeviceConfig()
    c.rule.th1, c.r0_kohm, c.version = 250.0, 7.5, 4
    a.save_config(c)
    d = Storage(str(tmp_path)).load_config()
    assert (d.rule.th1, d.r0_kohm, d.version) == (250.0, 7.5, 4)
    a.save_nowcast([1010.0, 1009.5], [1794470000, 1794470600])
    assert b.load_nowcast() == ([1010.0, 1009.5], [1794470000, 1794470600])


def test_config_validation():
    c = DeviceConfig()
    assert c.valid()
    c.rule.th2 = 100.0  # th1 < th2 bị vi phạm
    assert not c.valid()
