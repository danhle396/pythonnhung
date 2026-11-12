# Driver màn TFT 1.8" ST7735S 128x160 (SPI) tự viết cho MicroPython — thay thư viện Adafruit ST7735.
# Vẽ theo từng dải chữ: mỗi dòng chữ được dựng trong một FrameBuffer nhỏ (RGB565) rồi đẩy một cửa sổ qua SPI,
# không cần bộ đệm cả màn hình (40 kB). Font 8x8 có sẵn của framebuf; cỡ 2 = phóng to 2 lần.
import framebuf
from machine import SPI, Pin

from compat import sleep_ms

# Lệnh ST7735
SWRESET, SLPOUT, NORON, INVOFF, DISPON = 0x01, 0x11, 0x13, 0x20, 0x29
CASET, RASET, RAMWR, MADCTL, COLMOD = 0x2A, 0x2B, 0x2C, 0x36, 0x3A
MY, MX, MV, BGR = 0x80, 0x40, 0x20, 0x08

# Trình tự khởi tạo của datasheet/Adafruit cho module "tab" đỏ/đen/xanh (ST7735R/S)
_INIT = (
    (0xB1, b"\x01\x2c\x2d", 0), (0xB2, b"\x01\x2c\x2d", 0), (0xB3, b"\x01\x2c\x2d\x01\x2c\x2d", 0),
    (0xB4, b"\x07", 0), (0xC0, b"\xa2\x02\x84", 0), (0xC1, b"\xc5", 0), (0xC2, b"\x0a\x00", 0),
    (0xC3, b"\x8a\x2a", 0), (0xC4, b"\x8a\xee", 0), (0xC5, b"\x0e", 0), (INVOFF, b"", 0), (COLMOD, b"\x05", 0),
    (0xE0, b"\x02\x1c\x07\x12\x37\x32\x29\x2d\x29\x25\x2b\x39\x00\x01\x03\x10", 0),
    (0xE1, b"\x03\x1d\x07\x06\x2e\x2c\x29\x2d\x2e\x2e\x37\x3f\x00\x00\x02\x10", 0),
    (NORON, b"", 10), (DISPON, b"", 100),
)


def rgb(r, g, b):
    """Màu RGB565, đảo byte sẵn: framebuf ghi little-endian còn ST7735 đọc big-endian."""
    c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return ((c & 0xFF) << 8) | (c >> 8)


BLACK = rgb(0, 0, 0)
WHITE = rgb(255, 255, 255)
RED = rgb(255, 0, 0)
GREEN = rgb(0, 255, 0)
DARKGREEN = rgb(0, 124, 0)
YELLOW = rgb(255, 255, 0)
ORANGE = rgb(255, 165, 0)
CYAN = rgb(0, 255, 255)
GREY = rgb(124, 124, 124)


class ST7735:
    def __init__(self, spi_id, sck, mosi, cs, dc, baudrate=20000000, tab="black", rotation=1):
        # SPI chỉ ghi; MISO để mặc định của bus (không nối dây, chỉ là chân vào)
        self.spi = SPI(spi_id, baudrate=baudrate, polarity=0, phase=0, sck=Pin(sck), mosi=Pin(mosi))
        self.cs = Pin(cs, Pin.OUT, value=1)
        self.dc = Pin(dc, Pin.OUT, value=0)
        self.tab = tab
        self.width, self.height = (160, 128) if rotation in (1, 3) else (128, 160)
        col0, row0 = (2, 1) if tab == "green" else (0, 0)
        # khi xoay ngang, vị trí lệch của cột/hàng đổi chỗ
        self.x0, self.y0 = (row0, col0) if rotation in (1, 3) else (col0, row0)
        order = 0 if tab == "black" else BGR
        self.madctl = (MX | MY, MY | MV, 0, MX | MV)[rotation & 3] | order
        self._strips = {}
        self.init()

    def cmd(self, c, data=b""):
        self.cs(0)
        self.dc(0)
        self.spi.write(bytes([c]))
        if data:
            self.dc(1)
            self.spi.write(data)
        self.cs(1)

    def init(self):
        self.cmd(SWRESET)  # RESET nối EN: lệnh reset mềm để khởi tạo lại sau reset của ESP32
        sleep_ms(150)
        self.cmd(SLPOUT)
        sleep_ms(255)
        for c, data, delay in _INIT:
            self.cmd(c, data)
            if delay:
                sleep_ms(delay)
        self.cmd(MADCTL, bytes([self.madctl]))

    def window(self, x, y, w, h):
        x += self.x0
        y += self.y0
        self.cmd(CASET, bytes([0, x, 0, x + w - 1]))
        self.cmd(RASET, bytes([0, y, 0, y + h - 1]))

    def blit(self, buf, x, y, w, h):
        self.window(x, y, w, h)
        self.cs(0)
        self.dc(0)
        self.spi.write(bytes([RAMWR]))
        self.dc(1)
        self.spi.write(buf)
        self.cs(1)

    def fill_rect(self, x, y, w, h, color):
        line = bytearray(w * 2)
        hi, lo = color & 0xFF, color >> 8  # thứ tự byte giống framebuf
        for i in range(0, w * 2, 2):
            line[i], line[i + 1] = hi, lo
        self.window(x, y, w, h)
        self.cs(0)
        self.dc(0)
        self.spi.write(bytes([RAMWR]))
        self.dc(1)
        for _ in range(h):
            self.spi.write(line)
        self.cs(1)

    def fill(self, color):
        self.fill_rect(0, 0, self.width, self.height, color)

    def _strip(self, h):
        s = self._strips.get(h)
        if s is None:
            buf = bytearray(self.width * h * 2)
            s = (buf, framebuf.FrameBuffer(buf, self.width, h, framebuf.RGB565))
            self._strips[h] = s
        return s

    def text_row(self, text, y, size, fg, bg):
        """Vẽ một dòng chữ rộng hết màn hình (nền bg) tại y; cỡ 1 = 20 ký tự, cỡ 2 = 10 ký tự."""
        h = 8 * size
        buf, fb = self._strip(h)
        fb.fill(bg)
        if size == 1:
            fb.text(text, 0, 0, fg)
        else:
            small_buf, small = self._strip(8)
            small.fill(bg)
            text = text[:self.width // 16]
            small.text(text, 0, 0, fg)
            for yy in range(8):
                for xx in range(len(text) * 8):
                    if small.pixel(xx, yy) == fg:
                        fb.fill_rect(xx * size, yy * size, size, size, fg)
        self.blit(buf, 0, y, self.width, h)
