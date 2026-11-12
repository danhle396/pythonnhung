"""Sinh sơ đồ đấu dây docs/hardware/wiring.drawio (2 trang) — mở bằng draw.io / diagrams.net.

    python docs/hardware/gen_wiring_drawio.py
    python tools/render_drawio.py docs/hardware/wiring.drawio   # → wiring-1.png, wiring-2.png

Kiểu vẽ: hàng chân ESP32 ở trên, mỗi chân là một "thanh dọc" màu; linh kiện xếp bên phải, dây ngang từ thanh tới chân
linh kiện. Chấm tròn = nối; vòng cung = dây cắt qua, KHÔNG nối. Chân lấy theo firmware/src/config.py —
đổi chân thì sửa cả hai nơi.
"""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).with_name("wiring.drawio")

S_PIN = "rounded=0;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#d6b656;fontSize=13;"
S_PIN_NC = "rounded=0;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#d6b656;fontSize=13;fontColor=#999999;"
S_BODY = "rounded=0;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;strokeWidth=2;fontSize=14;"
S_HEAD = "rounded=0;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;strokeWidth=2;fontSize=16;"
S_COL = "rounded=0;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#6c8ebf;fontSize=13;"
S_RES = "rounded=0;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#333333;strokeWidth=2;fontSize=12;"
GREY = "#666666"


class Page:
    def __init__(self, name, title, cols, pin_x):
        """cols: [(key, nhãn dòng 1, nhãn dòng 2, màu dây)]"""
        self.name, self.rails, self.wires, self.dots, self.top = name, [], [], [], []
        self.n = 0
        self.col = {}
        self.max_y = {}
        self.pin_x = pin_x
        self.box(40, 40, 100 * len(cols), 60, title, S_HEAD)
        for i, (key, l1, l2, color) in enumerate(cols):
            self.col[key] = (90 + 100 * i, color)
            self.max_y[key] = 150
            self.box(40 + 100 * i, 100, 100, 50, f"<b>{l1}</b>" + (f"<br>{l2}" if l2 else ""), S_COL)
        self.y = 210

    # ---------------------------------------------------------------- phần tử cơ bản
    def _id(self):
        self.n += 1
        return f"{self.name}{self.n}"

    def box(self, x, y, w, h, text, style, layer="top"):
        c = (f'<mxCell id="{self._id()}" parent="1" style="{style}" value="{escape(text, {chr(34): "&quot;"})}" vertex="1">'
             f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        (self.dots if layer == "dot" else self.top).append(c)

    def line(self, pts, color, dashed=False, jump=True, rail=False):
        st = f"endArrow=none;html=1;strokeWidth=3;strokeColor={color};" + ("dashed=1;" if dashed else "") + \
             ("jumpStyle=arc;jumpSize=14;" if jump else "")
        mid = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in pts[1:-1])
        c = (f'<mxCell id="{self._id()}" parent="1" style="{st}" edge="1"><mxGeometry relative="1" as="geometry">'
             f'<mxPoint x="{pts[0][0]}" y="{pts[0][1]}" as="sourcePoint"/><mxPoint x="{pts[-1][0]}" y="{pts[-1][1]}" as="targetPoint"/>'
             + (f'<Array as="points">{mid}</Array>' if mid else "") + "</mxGeometry></mxCell>")
        (self.rails if rail else self.wires).append(c)

    def dot(self, x, y, color):
        self.box(x - 6, y - 6, 12, 12, "", f"ellipse;fillColor={color};strokeColor=none;", layer="dot")

    def tap(self, key, y, x_end, color=None, dashed=False):
        """dây ngang từ thanh `key` tới x_end tại độ cao y (có chấm nối ở thanh)."""
        rx, rc = self.col[key]
        color = color or rc
        self.line([(rx, y), (x_end, y)], color, dashed)
        self.dot(rx, y, color)
        self.max_y[key] = max(self.max_y[key], y)

    # ---------------------------------------------------------------- linh kiện
    def comp(self, text, pins, min_h=80, gap=50):
        """pins: [(nhãn, kết nối)] — kết nối: None (để trống) | "KEY" | ("KEY", "dashed") | ("via", "R…", "KEY")
        | ("custom",).  Trả về dict nhãn → tâm y của chân."""
        px, y0 = self.pin_x, self.y
        ys = {}
        for k, (label, conn) in enumerate(pins):
            y = y0 + 40 * k
            cy = y + 20
            ys[label] = cy
            self.box(px, y, 90, 40, label, S_PIN_NC if conn is None else S_PIN)
            if conn is None or conn == ("custom",):
                continue
            if isinstance(conn, str):
                self.tap(conn, cy, px)
            elif conn[0] == "via":
                _, rlabel, key = conn
                rx = px - 190
                self.tap(key, cy, rx)
                self.box(rx, cy - 15, 90, 30, rlabel, S_RES)
                self.line([(rx + 90, cy), (px, cy)], self.col[key][1])
            else:
                self.tap(conn[0], cy, px, dashed=True)
        h = max(40 * len(pins), min_h)
        self.box(px + 90, y0, 280, h, text, S_BODY)
        self.y = y0 + h + gap
        return ys

    def legend(self, items):
        y = self.y + 10
        x = 40
        for color, label, dashed in items:
            self.line([(x, y), (x + 60, y)], color, dashed, jump=False)
            self.box(x + 70, y - 14, 190, 28, label, "text;html=1;align=left;verticalAlign=middle;fontSize=13;")
            x += 270
        self.box(40, y + 22, 900, 26, "● = nối · vòng cung = dây cắt qua, KHÔNG nối · nét đứt = nối cố định để chọn địa chỉ/chế độ",
                 f"text;html=1;align=left;verticalAlign=middle;fontSize=13;fontColor={GREY};")
        self.height = y + 70

    def xml(self):
        for key, (rx, color) in self.col.items():  # thanh dọc vẽ trước để dây ngang "nhảy" qua
            if self.max_y[key] > 150:
                self.line([(rx, 150), (rx, self.max_y[key])], color, jump=False, rail=True)
        w = max(1300, self.pin_x + 420)
        body = "\n          ".join(self.rails + self.wires + self.top + self.dots)
        return (f'  <diagram id="{self.name}" name="{self.title_short}">\n'
                f'    <mxGraphModel dx="1200" dy="900" grid="0" gridSize="10" guides="1" tooltips="1" connect="0" arrows="1" '
                f'fold="1" page="1" pageScale="1" pageWidth="{w}" pageHeight="{self.height}" background="#FFFFFF" math="0" shadow="0">\n'
                f'      <root>\n        <mxCell id="0"/>\n        <mxCell id="1" parent="0"/>\n          {body}\n'
                f'      </root>\n    </mxGraphModel>\n  </diagram>\n')


SCL, SDA, DHT, P3V3, GND, P5V = "#F08C00", "#1E6FD9", "#2E9D47", "#D93636", "#222222", "#AD1457"

# =================================================================== Trang 1: cảm biến
p1 = Page("s", "<b>ESP32 DevKit V1</b> (ESP32-WROOM-32) · Trang 1/2 — <b>Cảm biến</b>", [
    ("G22", "GPIO22", "SCL", SCL), ("G21", "GPIO21", "SDA", SDA), ("G4", "GPIO4", "DHT22", DHT),
    ("G34", "GPIO34", "Mưa AO", "#00897B"), ("G35", "GPIO35", "Mưa DO", "#6D4C41"), ("G18", "GPIO18", "Mưa VCC", "#8E24AA"),
    ("G32", "GPIO32", "MQ-2 AO", "#3949AB"), ("5V", "VIN", "5V", P5V), ("3V3", "3V3", "", P3V3), ("GND", "GND", "", GND),
], pin_x=1340)
p1.title_short = "1 - Cam bien"
g = f"<font color='{GREY}'>"
p1.comp(f"<b>DHT22</b> (AM2302)<br>Nhiệt độ, độ ẩm<br>{g}1 dây · trở kéo lên 10 kΩ DATA–3V3<br>(module 3 chân đã có sẵn)</font>",
        [("VCC", "3V3"), ("DATA", "G4"), ("GND", "GND")], min_h=120)
p1.comp(f"<b>BH1750</b> (GY-302)<br>Cường độ ánh sáng<br>{g}I2C địa chỉ 0x23<br>(ADDR nối GND)</font>",
        [("VCC", "3V3"), ("GND", "GND"), ("SDA", "G21"), ("SCL", "G22"), ("ADDR", ("GND", "dashed"))])
p1.comp(f"<b>BMP280</b> (GY-BMP280)<br>Áp suất<br>{g}I2C địa chỉ 0x76 (SDO nối GND)<br>CSB nối 3V3 → chế độ I2C<br>chỉ dùng 3,3 V</font>",
        [("VCC", "3V3"), ("GND", "GND"), ("SDA", "G21"), ("SCL", "G22"), ("CSB", ("3V3", "dashed")), ("SDO", ("GND", "dashed"))])
p1.comp(f"<b>YL-83 + LM393</b><br>Mưa (4 mức)<br>{g}VCC lấy từ GPIO18: chỉ cấp khi đọc<br>(giảm ăn mòn tấm cảm biến)</font>",
        [("VCC", "G18"), ("GND", "GND"), ("DO", "G35"), ("AO", "G34")])
ys = p1.comp(f"<b>MQ-2</b><br>Khí gas, khói · đốt nóng 5 V ≈ 150 mA<br>{g}AO → R1 → GPIO32; GPIO32 → R2 → GND<br>"
             f"(AO tới 5 V → ≤ 3,33 V vào ADC)<br>"
             f"DO: để trống (mức 5 V)</font>",
             [("VCC", "5V"), ("GND", "GND"), ("AO", ("via", "R1 10 kΩ", "G32")), ("DO", None)], min_h=160, gap=90)
# cầu phân áp: AO → R1 10 kΩ → [nút giữa = GPIO32] → R2 20 kΩ → GND. Nút giữa nằm ở PHÍA GPIO32 của R1
# (bên trái R1), không phải phía chân AO — đặt sai thì GPIO32 nhận thẳng điện áp AO tới 5 V.
cy = ys["AO"]
nx = p1.pin_x - 240  # giữa thanh GND và R1 (R1 nằm ở pin_x−190 … pin_x−100)
p1.dot(nx, cy, "#3949AB")
p1.box(nx - 60, cy - 34, 120, 22, "→ GPIO32", "text;html=1;align=center;fontSize=12;fontColor=#3949AB;")
p1.box(nx - 32, cy + 30, 64, 44, "R2<br>20 kΩ", S_RES)
p1.line([(nx, cy), (nx, cy + 30)], "#3949AB", jump=False)
p1.line([(nx, cy + 74), (nx, cy + 100), (p1.col["GND"][0], cy + 100)], GND, jump=False)
p1.dot(p1.col["GND"][0], cy + 100, GND)
p1.max_y["GND"] = cy + 100
p1.legend([(P5V, "5 V (VIN)", False), (P3V3, "3,3 V", False), (GND, "GND", False), (SDA, "I2C SDA", False),
           (SCL, "I2C SCL", False), (DHT, "DHT22 data", False)])

# =================================================================== Trang 2: cảnh báo & điều khiển
TFT_CS, TFT_DC, TFT_SDA, TFT_SCK, TFT_RST = "#1E6FD9", "#8E24AA", "#00897B", "#F08C00", "#C2185B"
p2 = Page("a", "<b>ESP32 DevKit V1</b> · Trang 2/2 — <b>Cảnh báo &amp; hiển thị</b> (còi · LED · màn hình TFT)", [
    ("G25", "GPIO25", "Còi", "#6D4C41"), ("G26", "GPIO26", "LED xanh", "#2E9D47"),
    ("G14", "GPIO14", "LED đỏ", "#E53935"),
    ("G5", "GPIO5", "TFT CS", TFT_CS), ("G16", "GPIO16", "RX2 · TFT A0", TFT_DC), ("G17", "GPIO17", "TX2 · TFT SDA", TFT_SDA),
    ("G19", "GPIO19", "TFT SCK", TFT_SCK), ("EN", "EN", "TFT RESET", TFT_RST), ("3V3", "3V3", "", P3V3),
    ("GND", "GND", "", GND),
], pin_x=1350)
p2.title_short = "2 - Canh bao + TFT"
# Còi active 2 chân nối thẳng GPIO25 (không transistor): GPIO = HIGH → kêu.
p2.comp(f"<b>Còi active 2 chân</b><br>{g}nối thẳng GPIO, không cần transistor<br>"
        f"chân (+) dài hơn / có dấu + trên vỏ<br>GPIO25 = HIGH → kêu</font>",
        [("+", "G25"), ("−", "GND")], min_h=110, gap=40)
for key, name, state in [("G26", "LED xanh", "Bình thường · nháy 1 Hz = Chú ý"), ("G14", "LED đỏ", "nháy = Cảnh báo · sáng = Nguy hiểm")]:
    p2.comp(f"<b>{name}</b><br>{g}{state}</font>", [("A (+)", ("via", "220 Ω", key)), ("K (−)", "GND")], gap=30)
p2.y += 20
# Màn hình TFT 1.8" (module đỏ, 8 chân theo thứ tự trên mạch): SPI chỉ ghi qua HSPI + GPIO matrix
p2.comp(f"<b>TFT 1.8\" ST7735S</b> 128×160 · SPI<br>Màn hình màu tại chỗ (3 trang)<br>{g}"
        f"SPI chỉ ghi: không nối MISO<br>RESET → EN: reset cùng ESP32<br>LED = đèn nền → 3V3<br>"
        f"Khe thẻ SD (SD_CS/MOSI/MISO/SCK): không dùng</font>",
        [("VCC", "3V3"), ("GND", "GND"), ("CS", "G5"), ("RESET", "EN"), ("A0", "G16"), ("SDA", "G17"), ("SCK", "G19"),
         ("LED", "3V3")], gap=70)
p2.legend([(P3V3, "3,3 V", False), (GND, "GND", False), ("#6D4C41", "Còi", False), ("#2E9D47", "LED xanh", False),
           ("#E53935", "LED đỏ", False)])
p2.box(40, p2.height - 20, 1300, 26, "Không dùng LED vàng, transistor S8050, relay, nút tắt còi "
       "(GPIO27, GPIO23, GPIO13 để trống; firmware: HAS_LED_YELLOW = False, HAS_RELAY = False). Tắt còi: lệnh mute trên dashboard.",
       f"text;html=1;align=left;verticalAlign=middle;fontSize=13;fontColor={GREY};")
p2.box(40, p2.height + 6, 1300, 26, "TFT: SPI(1) = HSPI, chỉ ghi (firmware: PIN_TFT_* trong config.py); MicroPython gán GPIO12 làm MISO mặc định "
       "(chỉ là chân vào) — không nối gì vào GPIO12 (D12). Trên DevKit V1: GPIO16 in là RX2, GPIO17 in là TX2.",
       f"text;html=1;align=left;verticalAlign=middle;fontSize=13;fontColor={GREY};")
p2.height += 56

OUT.write_text('<mxfile host="Electron" agent="gen_wiring_drawio.py">\n' + p1.xml() + p2.xml() + "</mxfile>\n", encoding="utf-8")
print("Đã ghi", OUT)
