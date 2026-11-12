"""Sinh slide bảo vệ đồ án: docs/report/slides_bao_ve.pptx (python-pptx).

    python tools/slides/build_slides.py

Số liệu lấy từ docs/report/results_*.md và số test thực tế (chép vào hằng bên dưới — cập nhật khi huấn luyện lại).
"""
from __future__ import annotations

import re
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[2]
FIG = ROOT / "docs" / "report" / "figures"
OUT = ROOT / "docs" / "report" / "slides_bao_ve.pptx"

# ---- số test (cập nhật khi thêm test)
TESTS = {"ml": 44, "backend": 20, "firmware": 35, "dashboard": 8}

# ---- bảng màu: xanh biển sâu (thời tiết, Đà Nẵng) + hổ phách (cảnh báo gas)
C = dict(ink="0F1B2D", deep="0B4F6C", teal="1B7F8E", mist="E6F0F3", paper="FFFFFF", amber="F2A541", red="C0392B",
         green="2E7D32", yellow="F4C430", orange="E67E22", grey="5B6B7A", light="C9D6DE", cream="FFF4E0")
LV = [C["green"], C["yellow"], C["orange"], C["red"]]
HEAD, BODY = "Arial", "Calibri"
W, H, M = 13.333, 7.5, 0.6

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(W), Inches(H)
BLANK = prs.slide_layouts[6]
cp = prs.core_properties
cp.title = "Trạm quan trắc môi trường AIoT — VKU"
cp.author = "Nhóm đồ án VKU"
cp.subject = "Dự báo thời tiết ngắn hạn và cảnh báo khí gas/khói đa cấp, AI lai Edge–Cloud"


def rgb(h):
    return RGBColor.from_string(h)


def nb(t):
    """Giữ số kiểu '26 000' trên một dòng."""
    return re.sub(r"(\d) (\d{3})", "\\1\u00a0\\2", t) if isinstance(t, str) else t


_count = [0]


def slide(title=None, dark=False, notes=None):
    s = prs.slides.add_slide(BLANK)
    _count[0] += 1
    bg = s.background.fill
    bg.solid()
    bg.fore_color.rgb = rgb(C["ink"] if dark else C["paper"])
    if not dark:
        if title:
            text(s, title, M, 0.35, W - 2 * M, 0.85, font=HEAD, size=30, bold=True, valign="middle")
        text(s, "VKU · Trạm quan trắc AIoT", M, H - 0.42, 6, 0.3, size=10, color=C["grey"])
        text(s, str(_count[0]), W - M - 0.6, H - 0.42, 0.6, 0.3, size=10, color=C["grey"], align="right")
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def _style_run(r, font=BODY, size=16, color=C["ink"], bold=False, italic=False):
    r.font.name = font
    r.font.size = Pt(size)
    r.font.color.rgb = rgb(color)
    r.font.bold = bold
    r.font.italic = italic


def text(s, t, x, y, w, h, font=BODY, size=16, color=C["ink"], bold=False, italic=False, align="left",
         valign="top", runs=None):
    """Hộp chữ; t có thể nhiều dòng (\\n). runs = [(chữ, {tuỳ chọn}), ...] để trộn kiểu trong một dòng."""
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}[valign]
    al = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}[align]
    if runs:
        p = tf.paragraphs[0]
        p.alignment = al
        for chunk, o in runs:
            r = p.add_run()
            r.text = nb(chunk)
            _style_run(r, o.get("font", font), o.get("size", size), o.get("color", color), o.get("bold", bold),
                       o.get("italic", italic))
        return tb
    for i, line in enumerate(nb(t).split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = al
        r = p.add_run()
        r.text = line
        _style_run(r, font, size, color, bold, italic)
    return tb


def bullets(s, items, x, y, w, h, size=16, color=C["ink"]):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, t in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(6)
        pPr = p._p.get_or_add_pPr()
        pPr.set("marL", str(Inches(0.28)))
        pPr.set("indent", str(-Inches(0.28)))
        bu = etree.SubElement(pPr, qn("a:buChar"))
        bu.set("char", "•")
        r = p.add_run()
        r.text = nb(t)
        _style_run(r, BODY, size, color)
    return tb


def _no_line(shape, color=None):
    if color:
        shape.line.color.rgb = rgb(color)
    else:
        shape.line.fill.background()


def card(s, x, y, w, h, fill=C["mist"], radius=0.12, line=None):
    sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.adjustments[0] = min(0.5, radius / min(w, h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = rgb(fill)
    _no_line(sh, line or fill)
    sh.shadow.inherit = False
    return sh


def dot(s, x, y, d, color, label=None):
    sh = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    sh.fill.solid()
    sh.fill.fore_color.rgb = rgb(color)
    _no_line(sh, color)
    sh.shadow.inherit = False
    if label is not None:
        text(s, str(label), x, y, d, d, font=HEAD, size=d * 22, color=C["paper"], bold=True, align="center",
             valign="middle")


def stat(s, x, y, w, big, small, color=C["deep"]):
    text(s, big, x, y, w, 0.95, font=HEAD, size=44, bold=True, color=color, valign="bottom")
    text(s, small, x, y + 1.0, w, 0.7, size=14, color=C["grey"])


def arrow(s, x, y, w, both=False, color=C["deep"]):
    ln = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x), Inches(y), Inches(x + w), Inches(y))
    ln.line.color.rgb = rgb(color)
    ln.line.width = Pt(2)
    lnxml = ln.line._get_or_add_ln()
    if both:
        etree.SubElement(lnxml, qn("a:headEnd")).set("type", "triangle")
    etree.SubElement(lnxml, qn("a:tailEnd")).set("type", "triangle")


def img(s, name, x, y, w=None, h=None):
    return s.shapes.add_picture(str(FIG / name), Inches(x), Inches(y), Inches(w) if w else None,
                                Inches(h) if h else None)


def _cell_border(cell, color=C["light"], pt=0.5):
    tcPr = cell._tc.get_or_add_tcPr()
    # lược đồ OOXML: các đường viền phải đứng trước phần tô nền trong tcPr
    for i, tag in enumerate(("a:lnL", "a:lnR", "a:lnT", "a:lnB")):
        ln = etree.Element(qn(tag), w=str(int(pt * 12700)))
        sf = etree.SubElement(ln, qn("a:solidFill"))
        etree.SubElement(sf, qn("a:srgbClr"), val=color)
        tcPr.insert(i, ln)


def table(s, rows, x, y, w, col_w, row_h=0.5, size=14):
    shp = s.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(row_h * len(rows)))
    tbl = shp.table
    tblPr = tbl._tbl.tblPr
    for attr in ("firstRow", "bandRow"):
        tblPr.set(attr, "0")
    style = tblPr.find(qn("a:tableStyleId"))
    if style is not None:
        tblPr.remove(style)
    for j, cw in enumerate(col_w):
        tbl.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        tbl.rows[i].height = Inches(row_h)
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.margin_top = cell.margin_bottom = Inches(0.04)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb(C["deep"] if i == 0 else C["paper"])
            tf = cell.text_frame
            tf.paragraphs[0].text = ""
            r = tf.paragraphs[0].add_run()
            r.text = nb(val)
            _style_run(r, BODY, size, C["paper"] if i == 0 else C["ink"], bold=i == 0)
            _cell_border(cell)
    return tbl


def chart(s, title, data, x, y, w, h):
    cats = ["+1 h", "+3 h", "+6 h"]
    cd = CategoryChartData()
    cd.categories = cats
    for name, vals in data.items():
        cd.add_series(name, vals)
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), cd)
    ch = gf.chart
    ch.has_title = True
    ch.chart_title.text_frame.text = title
    _style_run(ch.chart_title.text_frame.paragraphs[0].runs[0], BODY, 14, C["ink"])
    ch.has_legend = True
    ch.legend.position = XL_LEGEND_POSITION.BOTTOM
    ch.legend.include_in_layout = False
    ch.legend.font.size = Pt(11)
    ch.legend.font.name = BODY
    colors = ["9AA5B1", "F0B429", "3E7CB1", "0B6E4F", "C75146"]
    for ser, col in zip(ch.series, colors):
        ser.format.fill.solid()
        ser.format.fill.fore_color.rgb = rgb(col)
    for ax in (ch.category_axis, ch.value_axis):
        ax.tick_labels.font.size = Pt(11)
        ax.tick_labels.font.name = BODY
        ax.tick_labels.font.color.rgb = rgb(C["grey"])
    ch.value_axis.major_gridlines.format.line.color.rgb = rgb("D9E2E8")
    ch.value_axis.major_gridlines.format.line.width = Pt(0.5)


# =============================================================== 1. Tiêu đề
s = slide(dark=True, notes="Giới thiệu đề tài: một trạm ESP32 vừa dự báo thời tiết ngắn hạn tại VKU vừa cảnh báo khí "
          "gas/khói 4 cấp. Điểm nhấn: AI lai edge–cloud, toàn bộ ML tự cài đặt và toàn bộ mã nguồn bằng Python.")
for i in range(4):
    dot(s, M + i * 0.55, 1.4, 0.38, LV[i])
text(s, "Trạm quan trắc môi trường AIoT", M, 2.3, W - 2 * M, 1.4, font=HEAD, size=40, bold=True, color=C["paper"],
     valign="bottom")
tb = text(s, "Dự báo thời tiết ngắn hạn và cảnh báo sớm khí gas/khói 4 cấp với AI lai Edge–Cloud", M, 3.85,
          W - 2 * M, 1.6, size=18, color=C["light"])
for t, col, sz in (("ESP32 + MicroPython · MQTT · FastAPI · TimescaleDB · ML tự viết bằng NumPy — 100 % Python",
                    C["amber"], 18), ("VKU — Đại học Đà Nẵng · 11/2026", C["light"], 14)):
    p = tb.text_frame.add_paragraph()
    r = p.add_run()
    r.text = t
    _style_run(r, BODY, sz, col)

# =============================================================== 2. Bối cảnh
s = slide("Bối cảnh: mưa nhiều và nguy cơ gas trong nhà",
          notes="Số liệu khí hậu tính từ 43 824 giờ Open-Meteo tại toạ độ VKU. Nêu ba vấn đề mà hệ thống giải quyết.")
stat(s, M, 1.5, 3.6, "62–66 %", "số giờ có mưa trong tháng 10 và 12 tại VKU (Open-Meteo 2021–2025)")
stat(s, M + 4.1, 1.5, 3.6, "668 mm", "lượng mưa trung bình tháng 10 — thời tiết đổi nhanh theo giờ")
stat(s, M + 8.2, 1.5, 3.6, "≈ 2 %", "giới hạn nổ dưới (LEL) của LPG ≈ 20 000 ppm", C["red"])
card(s, M, 4.1, W - 2 * M, 2.05)
text(s, "Vấn đề", M + 0.3, 4.3, 5, 0.4, font=HEAD, size=18, bold=True, color=C["deep"])
bullets(s, ["Dự báo công cộng có độ phân giải thô, không phản ánh vi khí hậu tại một điểm.",
            "Đầu báo gas giá rẻ chỉ có 1 ngưỡng cố định: dễ báo nhầm, không báo từ xa, không biết rò rỉ chậm.",
            "Thiết bị IoT phụ thuộc mạng: mất Wi-Fi là mất cảnh báo."], M + 0.3, 4.8, W - 2 * M - 0.6, 1.6)

# =============================================================== 3. Mục tiêu
s = slide("Mục tiêu và ràng buộc", notes="Bốn mục tiêu và hai ràng buộc của môn học: chỉ Python, tự viết toàn bộ ML.")
goals = [("Trạm 5 cảm biến", "DHT22, BMP280, BH1750, YL-83, MQ-2 gửi MQTT ổn định ≥ 72 h"),
         ("Cảnh báo 4 cấp", "Tại edge: hysteresis, debounce, chạy khi mất mạng, tắt còi từ dashboard"),
         ("Dự báo 1 / 3 / 6 giờ", "Nhiệt, ẩm, áp suất, mưa — vượt baseline persistence"),
         ("Cloud + dashboard", "Lưu trữ, leo thang, Telegram/Email, cấu hình từ xa")]
cw = (W - 2 * M - 3 * 0.3) / 4
for i, (t, d) in enumerate(goals):
    x = M + i * (cw + 0.3)
    card(s, x, 1.5, cw, 2.6)
    dot(s, x + 0.3, 1.75, 0.55, C["deep"], i + 1)
    text(s, t, x + 0.3, 2.45, cw - 0.6, 0.5, font=HEAD, size=17, bold=True)
    text(s, d, x + 0.3, 3.0, cw - 0.6, 1.0, size=14, color=C["grey"])
card(s, M, 4.5, W - 2 * M, 1.75, C["cream"])
text(s, "Ràng buộc", M + 0.3, 4.7, 4, 0.4, font=HEAD, size=18, bold=True, color=C["orange"])
bullets(s, ["Chỉ dùng Python: firmware ESP32 viết bằng MicroPython; backend, ML, dashboard, công cụ đều là Python.",
            "Không dùng thư viện học máy (scikit-learn, XGBoost, PyTorch…): CART, Random Forest, GBDT, Logistic, "
            "Holt-Winters, Isolation Forest, CUSUM, MLP, GRU tự cài đặt bằng NumPy trong mlcore."],
        M + 0.3, 5.15, W - 2 * M - 0.6, 1.1, size=15)

# =============================================================== 4. IPO
s = slide("Hệ thống theo mô hình Input – Xử lý – Output",
          notes="Đầu vào: 5 cảm biến, Open-Meteo, người dùng. Xử lý: edge (ESP32) và cloud nối qua MQTT. Đầu ra: còi/LED/TFT "
                "tại chỗ, dashboard, Telegram/Email, dữ liệu. Chi tiết 6 phân hệ ở docs/architecture/ipo.md.")
pic = img(s, "diagrams/so_do_he_thong_input_xu_ly_output.png", M, 1.3, h=5.6)
if pic.width > Inches(W - 2 * M):  # vừa khung
    ratio = Inches(W - 2 * M) / pic.width
    pic.width, pic.height = int(pic.width * ratio), int(pic.height * ratio)
pic.left = int((Inches(W) - pic.width) / 2)

# =============================================================== 5. Kiến trúc
s = slide("Kiến trúc AI lai Edge–Cloud", notes="Edge: quyết định an toàn trong dưới 1 giây và độc lập mạng. Cloud: ngữ "
          "cảnh dài, dự báo, thông báo, lưu trữ. MQTT nối hai phía.")
card(s, M, 1.4, 4.6, 5.1)
text(s, "EDGE — ESP32 · MicroPython", M + 0.25, 1.55, 4.2, 0.4, font=HEAD, size=16, bold=True, color=C["deep"])
eb = ["5 cảm biến · lọc median + EWMA", "10 feature cửa sổ 10–60 s", "Rule 4 cấp (+ RF khi có dữ liệu thật)",
      "level = max(rule, model)", "LED xanh/đỏ · còi · TFT", "Đệm offline trên flash · seq"]
for i, t in enumerate(eb):
    card(s, M + 0.25, 2.05 + i * 0.7, 4.1, 0.56, C["amber"] if i == 3 else C["paper"], 0.08, C["light"])
    text(s, t, M + 0.4, 2.05 + i * 0.7, 3.8, 0.56, size=14, valign="middle", bold=i == 3)
bx = M + 4.95
card(s, bx, 3.2, 2.3, 1.5, C["deep"], 0.2)
text(s, "Mosquitto\nMQTT", bx, 3.25, 2.3, 0.85, font=HEAD, size=17, bold=True, color=C["paper"], align="center",
     valign="middle")
text(s, "auth · ACL · LWT · retain", bx, 4.05, 2.3, 0.5, size=12, color=C["light"], align="center")
arrow(s, M + 4.6, 3.95, 0.35, both=True)
arrow(s, bx + 2.3, 3.95, 0.35, both=True)
text(s, "telemetry · alert · status\ncmd · config · forecast", bx - 0.2, 4.85, 2.7, 0.7, size=12, color=C["grey"],
     align="center")
cx = bx + 2.65
card(s, cx, 1.4, W - M - cx, 5.1)
text(s, "CLOUD — Docker Compose", cx + 0.25, 1.55, 4.5, 0.4, font=HEAD, size=16, bold=True, color=C["deep"])
cb = [("Ingest", "validate · chống trùng · ghi lô"), ("Alert service", "leo thang theo độ dốc 10 phút · nhắc lại"),
      ("Forecast service", "GBDT mlcore + bias correction"), ("TimescaleDB", "hypertable · continuous aggregate"),
      ("API + Dashboard", "JWT · WebSocket · Streamlit · Grafana"), ("Thông báo", "Telegram · Email · ack inline")]
cwid = W - M - cx - 0.5
for i, (t, d) in enumerate(cb):
    card(s, cx + 0.25, 2.05 + i * 0.7, cwid, 0.56, C["paper"], 0.08, C["light"])
    text(s, "", cx + 0.4, 2.05 + i * 0.7, cwid - 0.3, 0.56, size=14, valign="middle",
         runs=[(t + "  ", {"bold": True}), (d, {"color": C["grey"], "size": 13})])

# =============================================================== 6. Firmware MicroPython
s = slide("Firmware ESP32 viết bằng MicroPython", notes="Toàn bộ firmware là Python: driver BMP280/BH1750/ST7735 và MQTT "
          "client tự viết. Logic thuần (lọc, rule, nowcast, đệm offline) chạy được cả trên PC nên test bằng pytest. "
          "Nạp bằng firmware/deploy.py (mpy-cross + mpremote) hoặc Thonny.")
card(s, M, 1.45, 5.95, 4.0)
text(s, "Hai luồng", M + 0.3, 1.6, 5, 0.4, font=HEAD, size=18, bold=True, color=C["deep"])
bullets(s, ["Luồng chính: cảm biến 1 Hz → feature → rule/model → còi/LED, vẽ TFT — không phụ thuộc mạng",
            "Luồng mạng (_thread): Wi-Fi, NTP, MQTT, gửi bù đệm offline, hiệu chuẩn R0, OTA",
            "Watchdog 30 s: chỉ cho ăn khi luồng mạng còn sống",
            "Cấu hình, seq, mẫu nowcast lưu file JSON trên flash"], M + 0.3, 2.1, 5.4, 3.3, size=15)
x2 = M + 6.3
card(s, x2, 1.45, W - M - x2, 4.0, C["cream"])
text(s, "Tự viết bằng Python", x2 + 0.3, 1.6, 6, 0.4, font=HEAD, size=18, bold=True, color=C["orange"])
bullets(s, ["drivers.py: BMP280 (bù trừ số nguyên của datasheet), BH1750",
            "st7735.py: màn TFT qua SPI + framebuf, vẽ theo dải chữ",
            "mqtt.py: MQTT 3.1.1 (LWT, QoS 1 subscribe, keepalive, timeout)",
            "ota.py: cập nhật .mpy qua HTTP theo manifest",
            "gas_model.py: cây quyết định sinh tự động từ mlcore"], x2 + 0.3, 2.1, W - M - x2 - 0.6, 3.3, size=15)
stat(s, M, 5.45, 3.6, "21", "module MicroPython, biên dịch .mpy bằng mpy-cross")
stat(s, M + 4.1, 5.45, 3.6, str(TESTS["firmware"]), "test pytest chạy logic firmware trên PC")
stat(s, M + 8.2, 5.45, 3.6, "0", "dòng C/C++ trong dự án", C["green"])

# =============================================================== 7. Phần cứng & MQTT
s = slide("Phần cứng và giao thức MQTT", notes="Sơ đồ chân trong firmware/src/config.py. ACL: mỗi thiết bị chỉ ghi "
          "topic của chính nó.")
rows = [["Linh kiện", "Chân ESP32", "Ghi chú"], ["BMP280 · BH1750", "I²C 21/22", "0x76 · 0x23"],
        ['TFT 1.8" ST7735', "SPI 5 · 16 · 17 · 19", "CS·A0·SDA·SCK"], ["DHT22", "GPIO 4", "chu kỳ 2 s"],
        ["YL-83", "AO 34 · nguồn 18", "cấp nguồn khi đọc"], ["MQ-2", "AO 32 · DO 33", "phân áp 10k/20k"],
        ["Còi active 2 chân", "25", "nối thẳng GPIO"], ["LED xanh · đỏ", "26 · 14", "220 Ω"]]
table(s, rows, M, 1.45, 6.2, [2.4, 1.9, 1.9], 0.46, size=13)
r2 = [["Topic vku/aiot/{id}/…", "QoS", "Retain"], ["telemetry (10 s, 1 s khi cảnh báo)", "0", ""],
      ["alert · nowcast", "0", "nowcast"], ["status (LWT offline)", "0", "✔"], ["cmd (mute, calibrate, ota…)", "1", ""],
      ["config (có phiên bản + ack)", "1", "✔"], ["forecast → TFT", "1", "✔"]]
table(s, r2, M + 6.6, 1.45, W - 2 * M - 6.6, [3.6, 0.8, 1.13], 0.46, size=13)
card(s, M, 5.6, W - 2 * M, 1.0, C["cream"])
text(s, "MQTT client tự viết publish QoS 0 → tin cậy ở tầng ứng dụng: số thứ tự seq + đệm offline 2 000 bản ghi trên "
        "flash + backend chống trùng theo khoá (device_id, ts, seq).", M + 0.3, 5.65, W - 2 * M - 0.6, 0.9, size=15,
     valign="middle")

# =============================================================== 8. Cảnh báo 4 cấp
s = slide("Cảnh báo 4 cấp tại edge", notes="Ngưỡng mặc định có thể đổi từ xa qua topic config. Khi có model: fusion = "
          "max(rule, model), model không hạ cấp rule.")
lv = [("0", "Bình thường", "ppm < 300", "LED xanh"), ("1", "Chú ý", "ppm ≥ 300 hoặc dốc ≥ 15 ppm/s", "LED xanh nháy · log"),
      ("2", "Cảnh báo", "ppm ≥ 1 000", "đỏ nháy · còi · Telegram"),
      ("3", "Nguy hiểm", "ppm ≥ 2 000 hoặc ≥ 1 000 + nhiệt tăng ≥ 1 °C/phút", "còi liên tục · Telegram + Email · nhắc mỗi phút")]
for i, (n, name, cond, act) in enumerate(lv):
    y = 1.45 + i * 1.1
    card(s, M, y, 7.6, 0.95)
    dot(s, M + 0.15, y + 0.2, 0.56, LV[i], n)
    text(s, name, M + 0.9, y, 1.7, 0.95, font=HEAD, size=16, bold=True, valign="middle")
    text(s, cond, M + 2.6, y, 2.5, 0.95, size=13, valign="middle")
    text(s, act, M + 5.15, y, 2.35, 0.95, size=13, color=C["grey"], valign="middle")
x2 = M + 8.0
w2 = W - M - x2
card(s, x2, 1.45, w2, 4.25)
text(s, "Chống dao động & an toàn", x2 + 0.25, 1.6, w2 - 0.5, 0.4, font=HEAD, size=16, bold=True, color=C["deep"])
bullets(s, ["Hysteresis 15 %: hạ cấp khi ppm < 0,85 × ngưỡng", "Debounce: lên 3 mẫu, xuống 5 mẫu; cấp 3 lên ngay",
            "Hiện chạy rule (chưa có dữ liệu khí đo thật để huấn luyện model)", "Cloud leo thang khi ppm tăng đều 10 phút"],
        x2 + 0.25, 2.1, w2 - 0.5, 3.0, size=14)
text(s, "10 feature: gas_ppm · Rs/R0 · slope10 · std30 · dev_base · temp · dtemp/phút · hum · dhum/phút · lux_rel",
     M, 6.05, W - 2 * M, 0.5, size=14, color=C["grey"], italic=True)

# =============================================================== 9. mlcore
s = slide("mlcore — thư viện học máy tự viết bằng NumPy", notes="Mọi mô hình triển khai đều nạp bằng "
          "mlcore.serialize.load_model; requirements không chứa thư viện ML.")
mods = [("Cây & tổ hợp", "CART histogram · Random Forest · GBDT (MSE, log-loss) · early stopping"),
        ("Tuyến tính & chuỗi", "OLS/Ridge · Logistic · Holt-Winters damped"),
        ("Bất thường", "Isolation Forest · CUSUM · z-score theo giờ"),
        ("Mạng nơ-ron", "MLP · GRU + BPTT · SGD/Momentum/Adam · clipping"),
        ("Đánh giá & giải thích", "MAE/RMSE · F1 · ROC-AUC Mann–Whitney · permutation importance"),
        ("Triển khai", "serialize JSON/.npz · registry · export_micropython → gas_model.py")]
cw = (W - 2 * M - 2 * 0.3) / 3
for i, (t, d) in enumerate(mods):
    x, y = M + (i % 3) * (cw + 0.3), 1.45 + (i // 3) * 1.75
    card(s, x, y, cw, 1.5)
    text(s, t, x + 0.25, y + 0.15, cw - 0.5, 0.4, font=HEAD, size=16, bold=True, color=C["deep"])
    text(s, d, x + 0.25, y + 0.6, cw - 0.5, 0.85, size=14)
stat(s, M, 5.0, 3.6, str(TESTS["ml"]), "unit test pass (dữ liệu đồ chơi, round-trip, không rò rỉ tương lai)")
stat(s, M + 4.1, 5.0, 3.6, "< 1e-5", "sai số gradient check cho Logistic, MLP, GRU")
stat(s, M + 8.2, 5.0, 3.6, "≈ 2 500", "dòng code NumPy, giao diện fit / predict / to_dict")

# =============================================================== 10. Toán GBDT
s = slide("Gradient Boosting trên histogram (dạng Newton)", notes="Cùng một cây hồi quy dùng cho CART-MSE (g = −y, "
          "h = 1, λ = 0) và GBDT. Đây là công thức của XGBoost.")
card(s, M, 1.45, 6.3, 4.9)
f = [("Gradient / hessian", "MSE: g = F − y, h = 1\nLog-loss: g = p − y, h = p(1 − p)"),
     ("Gain khi chia nút", "G_L²/(H_L+λ) + G_R²/(H_R+λ) − G²/(H+λ)"), ("Giá trị lá (bước Newton)", "w* = −G / (H + λ)"),
     ("Cập nhật", "F_m(x) = F_{m−1}(x) + η · f_m(x)")]
for i, (t, e) in enumerate(f):
    text(s, t, M + 0.3, 1.6 + i * 1.18, 5.7, 0.35, size=14, bold=True, color=C["deep"])
    text(s, e, M + 0.3, 1.95 + i * 1.18, 5.7, 0.75, font="Cambria", size=17)
x2 = M + 6.7
w2 = W - M - x2
text(s, "Tăng tốc", x2, 1.5, w2, 0.4, font=HEAD, size=18, bold=True, color=C["deep"])
bullets(s, ["Rời rạc hoá mỗi feature ≤ 64 bin theo phân vị → tìm ngưỡng O(F·B) thay vì sắp xếp",
            "np.bincount theo (nút × bin) — histogram cả tầng trong một lệnh", "Trừ histogram: con lớn = cha − con nhỏ",
            "Subsample hàng + early stopping trên validation"], x2, 2.0, w2, 2.6, size=15)
card(s, x2, 4.75, w2, 1.6, C["cream"])
text(s, "GBDT nhiệt độ 1 h: 123 cây, huấn luyện 7,7 s trên 26 000 giờ, suy luận 17,6 µs/mẫu", x2 + 0.25, 4.9, w2 - 0.5,
     1.3, size=16, valign="middle")

# =============================================================== 11. Edge model -> MicroPython
s = slide("Từ mlcore tới ESP32: xuất mô hình sang MicroPython", notes="Bộ xuất tự viết thay cho emlearn: mảng nút đóng gói "
          "bytes, ngưỡng float32 như số thực của MicroPython. Test so khớp với mlcore trên PC; bench_device.py đo thời "
          "gian suy luận ngay trên ESP32.")
steps = [("Thu dữ liệu", "label_logger.py\nMQ-2 đo thật, gán nhãn"), ("Huấn luyện", "train_gas_edge.py\nDecision Tree / RF nhỏ"),
         ("Xuất Python", "export_micropython.py\n→ gas_model.py (bytes)"), ("Nạp ESP32", "deploy.py (mpremote)\nfusion với rule 1 Hz")]
sw = (W - 2 * M - 3 * 0.45) / 4
for i, (t, d) in enumerate(steps):
    x = M + i * (sw + 0.45)
    card(s, x, 1.5, sw, 1.9, C["cream"] if i == 0 else C["mist"])
    dot(s, x + 0.25, 1.7, 0.5, C["deep"], i + 1)
    text(s, t, x + 0.9, 1.7, sw - 1.1, 0.5, font=HEAD, size=17, bold=True, valign="middle")
    text(s, d, x + 0.25, 2.35, sw - 0.5, 0.95, size=14, color=C["grey"])
    if i < 3:
        arrow(s, x + sw + 0.05, 2.45, 0.35)
stat(s, M, 3.9, 3.8, "0", "lệch lớp gas_model.py ↔ mlcore (unit test, cây và rừng)", C["green"])
stat(s, M + 4.1, 3.9, 3.8, "rule", "chế độ hiện tại: chưa có dữ liệu khí đo thật", C["orange"])
stat(s, M + 8.2, 3.9, 3.6, "10 B", "mỗi nút cây trong flash (int16 × 3 + float32)")
text(s, "Khi chưa có model: gas_model.py đặt AVAILABLE = False → firmware tự chạy rule, không dùng số liệu giả",
     M, 6.0, W - 2 * M, 0.4, size=14, italic=True, color=C["grey"])

# =============================================================== 12. Backend
s = slide("Cloud: alert service và forecast service", notes=f"FastAPI + SQLAlchemy 2 + APScheduler. {TESTS['backend']} "
          "test backend gồm integration test với Mosquitto thật.")
x2 = M + 6.3
card(s, M, 1.45, 5.95, 3.5)
text(s, "Alert service", M + 0.3, 1.6, 5, 0.4, font=HEAD, size=18, bold=True, color=C["deep"])
bullets(s, ["Cấp 1: log · cấp 2: Telegram · cấp 3: Telegram + Email",
            "Cooldown theo (thiết bị, cấp); nhắc lại cấp 3 mỗi phút tới khi ack",
            "Leo thang: độ dốc ppm 10 phút → cmd escalate (Isolation Forest khi đủ dữ liệu trạm)",
            "Offline > 60 s hoặc LWT → cảnh báo device_offline", "Ack qua dashboard hoặc nút inline Telegram"],
        M + 0.3, 2.15, 5.4, 2.75, size=15)
card(s, x2, 1.45, W - M - x2, 3.5)
text(s, "Forecast service (10 phút)", x2 + 0.3, 1.6, 6, 0.4, font=HEAD, size=18, bold=True, color=C["deep"])
bullets(s, ["Pretrain trên 5 năm Open-Meteo tại VKU",
            "Bias correction trạm → Open-Meteo (Ridge; chỉ hiệu chỉnh độ lệch khi tương quan kém)",
            "Dự phòng: dữ liệu trạm → Open-Meteo 4 ngày → persistence", "Khoảng tin cậy 95 %: ŷ ± 1,96 · RMSE_test",
            "Publish forecast (retain) → màn TFT; tin tóm tắt 6 giờ sáng"], x2 + 0.3, 2.15, W - M - x2 - 0.6, 2.75, size=15)
stat(s, M, 5.1, 2.9, "43 824", "giờ dữ liệu Open-Meteo 2021–2025")
stat(s, M + 3.1, 5.1, 2.9, "12", "dự báo mỗi lượt (4 biến × 3 tầm)")
stat(s, M + 6.2, 5.1, 2.9, "0,2 s", "thời gian một lượt dự báo trong Docker")
stat(s, M + 9.3, 5.1, 2.9, str(TESTS["backend"]), "test backend, gồm integration MQTT")

# =============================================================== 13. Dashboard
s = slide("Dashboard: realtime, dự báo, cảnh báo, cấu hình", notes="Demo trực tiếp dashboard với dữ liệu từ trạm thật.")
pages = [("Tổng quan", "cấp cảnh báo hiện tại, số đo, dự báo mới nhất, cảnh báo gần đây"),
         ("Biểu đồ", "cửa sổ 1 giờ / 24 giờ / 7 ngày, tải CSV"), ("Dự báo", "thực tế vs dự báo + khoảng tin cậy 95 %, xác suất mưa"),
         ("Cảnh báo", "dòng thời gian, lọc theo cấp/nguồn, nút xác nhận (ack)"),
         ("Thiết bị", "lệnh thử còi · tắt còi · hiệu chuẩn R0 · cấu hình ngưỡng"),
         ("Mô hình", "model registry đang hoạt động và bảng kết quả")]
for i, (t, d) in enumerate(pages):
    x, y = M + (i % 3) * (cw + 0.3), 1.45 + (i // 3) * 1.85
    card(s, x, y, cw, 1.6)
    text(s, t, x + 0.25, y + 0.15, cw - 0.5, 0.4, font=HEAD, size=17, bold=True, color=C["deep"])
    text(s, d, x + 0.25, y + 0.65, cw - 0.5, 0.85, size=14)
card(s, M, 5.35, W - 2 * M, 1.1)
text(s, f"Streamlit 6 trang, JWT, WebSocket realtime · Grafana provision sẵn đọc TimescaleDB · {TESTS['dashboard']} "
        "smoke test dashboard", M + 0.25, 5.35, W - 2 * M - 0.5, 1.1, size=15, valign="middle")

# =============================================================== 14. Kết quả dự báo
s = slide("Dự báo: GBDT tốt nhất ở mọi biến và mọi tầm", notes="Train 2021–2023, validation 2024, test 2025, chia theo "
          "thời gian. 56 feature. GRU tự viết gần bằng GBDT nhưng huấn luyện lâu hơn nhiều.")
temp = {"Persistence": [0.593, 1.559, 2.759], "Holt-Winters": [0.422, 0.821, 0.925], "Ridge": [0.348, 0.690, 0.837],
        "GBDT": [0.299, 0.543, 0.688], "GRU (NumPy)": [0.310, 0.556, 0.714]}
hum = {"Persistence": [2.968, 7.541, 13.210], "Holt-Winters": [2.384, 4.299, 4.766], "Ridge": [2.045, 3.822, 4.515],
       "GBDT": [1.856, 3.244, 3.980], "GRU (NumPy)": [1.932, 3.295, 4.052]}
chart(s, "MAE nhiệt độ (°C) — test 2025", temp, M, 1.4, 5.9, 3.9)
chart(s, "MAE độ ẩm (%RH) — test 2025", hum, M + 6.25, 1.4, 5.9, 3.9)
stat(s, M, 5.4, 2.9, "0,30 °C", "MAE nhiệt độ 1 h")
stat(s, M + 3.1, 5.4, 2.9, "1,86 %", "MAE độ ẩm 1 h")
stat(s, M + 6.2, 5.4, 2.9, "0,839", "F1 mưa 3 h (AUC 0,926)")
stat(s, M + 9.3, 5.4, 2.9, "−75 %", "MAE nhiệt 6 h so với persistence", C["green"])

# =============================================================== 15. Dự báo minh hoạ
s = slide("Dự báo 3 giờ trong mùa mưa (1–14/11/2025)", notes="Đường đen là thực tế, xanh lá là GBDT, cam là Ridge, "
          "chấm xanh là persistence.")
img(s, "forecast_3h_nov2025.png", M, 1.35, 7.4, 5.4)
x2 = M + 7.8
w2 = W - M - x2
card(s, x2, 1.45, w2, 5.0)
text(s, "Nhận xét", x2 + 0.3, 1.6, w2 - 0.6, 0.4, font=HEAD, size=18, bold=True, color=C["deep"])
bullets(s, ["GBDT bám chu kỳ ngày và các đợt lạnh, persistence trễ pha 3 giờ",
            "Feature mạnh nhất: hour_sin, temp_d1, xu hướng áp suất 3 h, góc thiên đỉnh — đúng trực giác vật lý",
            "Holt-Winters tốt hơn persistence nhưng không dùng được thông tin mưa/mây",
            "Mưa 6 h: GBDT F1 0,854 so với persistence 0,723"], x2 + 0.3, 2.15, w2 - 0.6, 4.2, size=15)

# =============================================================== 16. Cảnh báo khí: trạng thái
s = slide("Cảnh báo khí: chỉ dùng dữ liệu đo thật", notes="Thí nghiệm ở nơi thoáng, lượng nhỏ, có người giám sát. Mọi số "
          "liệu cảnh báo khí sẽ đo trên phần cứng thật.")
card(s, M, 1.45, 5.95, 4.9)
text(s, "Hiện tại", M + 0.3, 1.6, 5, 0.4, font=HEAD, size=18, bold=True, color=C["deep"])
bullets(s, ["Chưa có dữ liệu MQ-2 đo thật → chưa huấn luyện model",
            "Edge chạy rule 4 cấp: 300 / 1 000 / 2 000 ppm, dốc ≥ 15 ppm/s, nhiệt ≥ 1 °C/phút",
            "Hysteresis 15 %, debounce 3 / 5 mẫu — kiểm thử bằng pytest",
            "Random Forest, Isolation Forest, CUSUM đã cài trong mlcore, pipeline sẵn sàng"],
        M + 0.3, 2.15, 5.4, 4.1, size=15)
x2 = M + 6.3
card(s, x2, 1.45, W - M - x2, 4.9, C["cream"])
text(s, "Kế hoạch thu dữ liệu", x2 + 0.3, 1.6, 6, 0.4, font=HEAD, size=18, bold=True, color=C["orange"])
bullets(s, ["label_logger.py ghi 1 Hz kèm nhãn", "Gas bật lửa xả, không đốt: 50 / 20 / 5 cm → nhãn 1 / 2 / 3",
            "Khói nhang trong hộp → 2 · hơi nước, cồn, nước hoa → 0 (đo báo động giả)",
            "Chia train/test theo buổi; so sánh Rule / Model / Hybrid", "Isolation Forest: sau ≥ 3 tuần telemetry trạm"],
        x2 + 0.3, 2.15, W - M - x2 - 0.6, 4.1, size=15)

# =============================================================== 17. Hiệu năng
total = sum(TESTS.values())
s = slide("Hiệu năng và triển khai", notes="Một trạm thật gửi 0,1 msg/s nên 50 msg/s tương đương khoảng 500 trạm.")
stat(s, M, 1.4, 2.9, "0 %", "mất gói với 50 thiết bị × 1 msg/s, QoS 1", C["green"])
stat(s, M + 3.1, 1.4, 2.9, "3,4 ms", "độ trễ broker P95 (Docker)")
stat(s, M + 6.2, 1.4, 2.9, "100 %", "bản ghi vào TimescaleDB")
stat(s, M + 9.3, 1.4, 2.9, "≈ 10 %", "CPU backend trung bình (1 lõi)")
rows = [["Kịch bản", "P50 / P95 / P99 (ms)", "CPU backend"], ["20 thiết bị, SQLite", "0,6 / 2,0 / 3,1", "54,5 %"],
        ["50 thiết bị, SQLite", "0,6 / 2,2 / 4,1", "61,4 %"], ["50 thiết bị, Docker + TimescaleDB", "1,7 / 3,4 / 4,4", "9,8 %"]]
table(s, rows, M, 3.55, 7.0, [3.2, 2.2, 1.6], 0.6)
x2 = M + 7.4
w2 = W - M - x2
card(s, x2, 3.55, w2, 2.9)
text(s, "docker compose up -d --build", x2 + 0.25, 3.7, w2 - 0.5, 0.4, font="Consolas", size=14, bold=True,
     color=C["deep"])
bullets(s, ["Mosquitto · TimescaleDB · backend · dashboard (+ Grafana)", "Healthcheck + thứ tự khởi động",
            "alembic upgrade head tự động",
            f"Kiểm thử: {TESTS['ml']} ML · {TESTS['backend']} backend · {TESTS['firmware']} firmware · "
            f"{TESTS['dashboard']} dashboard"], x2 + 0.25, 4.2, w2 - 0.5, 2.2, size=14)

# =============================================================== 18. Kết luận
s = slide("Kết luận", notes="Nhấn mạnh: hệ thống là nguyên mẫu học thuật, không thay thế thiết bị báo gas đã chứng nhận.")
rows = [["KPI", "Kết quả", ""], ["Dự báo vượt persistence", "12/12 cặp biến × tầm", "✔"],
        ["MAE T 1h · H 1h · F1 mưa 3h", "0,30 °C · 1,86 % · 0,839", "✔"],
        ["Cảnh báo 4 cấp tại edge, chạy offline", "rule, kiểm thử pytest", "✔"],
        ["Model ML cảnh báo khí", "chờ dữ liệu khí đo thật", "⚙"], ["≥ 50 thiết bị, mất gói ≈ 0", "0 %", "✔"],
        ["100 % Python, ML tự viết, Docker", f"MicroPython + mlcore + {total} test", "✔"],
        ["72 h ổn định, độ trễ end-to-end thật", "cần phần cứng", "⚙"]]
table(s, rows, M, 1.4, 7.4, [3.6, 3.1, 0.7], 0.6)
x2 = M + 7.8
w2 = W - M - x2
card(s, x2, 1.4, w2, 5.1)
text(s, "Hướng phát triển", x2 + 0.3, 1.55, w2 - 0.6, 0.4, font=HEAD, size=18, bold=True, color=C["deep"])
bullets(s, ["Thu dữ liệu khí thật, huấn luyện lại, cập nhật gas_model.py qua OTA",
            "MQ-135/MQ-5 giảm nhạy chéo cồn; cảm biến PM2.5", "LoRa/NB-IoT, pin mặt trời, nhiều trạm (mesh)",
            "Federated learning, lượng tử hoá int8", "OTA mô hình qua MQTT"], x2 + 0.3, 2.1, w2 - 0.6, 4.3, size=15)

# =============================================================== 19. Demo
s = slide(dark=True, notes="Kịch bản chi tiết: docs/report/kich_ban_demo.md.")
for i in range(4):
    dot(s, M + i * 0.55, 1.4, 0.38, LV[i])
text(s, "Demo và hỏi đáp", M, 2.3, W - 2 * M, 1.4, font=HEAD, size=40, bold=True, color=C["paper"], valign="bottom")
tb = text(s, "Dashboard → xả gas gần MQ-2 → LED/còi đổi cấp → Telegram → ack → rút Wi-Fi: edge vẫn cảnh báo",
          M, 3.85, W - 2 * M, 1.6, size=18, color=C["light"])
p = tb.text_frame.add_paragraph()
r = p.add_run()
r.text = "github.com/danhle396/pythonnhung"
_style_run(r, BODY, 14, C["light"])

prs.save(OUT)
print("Đã ghi", OUT, f"({_count[0]} slide)")
