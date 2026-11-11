# Phần cứng — sơ đồ đấu dây

**Trang 1 — Cảm biến**

![Sơ đồ đấu dây — cảm biến](wiring-1.png)

**Trang 2 — Cảnh báo và điều khiển**

![Sơ đồ đấu dây — cảnh báo](wiring-2.png)

Chấm tròn = nối · vòng cung = dây cắt qua, **không** nối · nét đứt = nối cố định để chọn địa chỉ/chế độ.

- **`wiring.drawio`** (2 trang): mở bằng [draw.io / diagrams.net](https://app.diagrams.net) (File → Open) để xem và sửa.
- `wiring-1.png`, `wiring-2.png`: ảnh xuất cho báo cáo/slide.
- Sinh lại sau khi đổi chân: sửa `gen_wiring_drawio.py` **và** `firmware/include/config.h`, rồi
  `python docs/hardware/gen_wiring_drawio.py` và `cd tools/slides && node ../render_drawio.js ../../docs/hardware/wiring.drawio`.

## Bảng đấu dây

| Linh kiện | Chân linh kiện | Nối tới | Ghi chú |
|---|---|---|---|
| Nguồn 5 V / 2 A | +5V / GND | VIN / GND của ESP32, MQ-2 | GND chung toàn mạch |
| BMP280 | VCC / GND / SCL / SDA / SDO | 3V3 / GND / GPIO22 / GPIO21 / GND | địa chỉ 0x76 |
| BH1750 | VCC / GND / SCL / SDA / ADDR | 3V3 / GND / GPIO22 / GPIO21 / GND | địa chỉ 0x23 |
| OLED SSD1306 | VCC / GND / SCL / SDA | 3V3 / GND / GPIO22 / GPIO21 | 0x3C |
| DHT22 | VCC / DATA / GND | 3V3 / GPIO4 / GND | trở kéo lên 10 kΩ DATA → 3V3 |
| YL-83 (LM393) | VCC / GND / AO / DO | **GPIO18** / GND / GPIO34 / GPIO35 | GPIO18 chỉ cấp nguồn khi đọc (giảm ăn mòn) |
| MQ-2 | VCC / GND / AO / DO | 5V / GND / **R1 10 kΩ → GPIO32**, R2 20 kΩ GPIO32 → GND / *để trống* | AO tối đa 5 V → 3,33 V |
| Còi active (2 chân) | + / − | GPIO25 / GND | nối thẳng, không cần transistor (còi 3,3 V ≈ 20 mA) |
| Module còi 3 chân | I/O / VCC / GND | GPIO25 / 3V3 / GND | có transistor sẵn; kêu khi I/O = LOW ⇒ `BUZZER_ACTIVE_LOW 1` |
| LED xanh / đỏ | anode / cathode | 220 Ω ← GPIO26 / 14 · GND | cấp 1 = xanh nháy 1 Hz (không có LED vàng) |
| Nút tắt còi | 2 chân | GPIO13 / GND | INPUT_PULLUP nội |
| *(không dùng)* LED vàng, transistor S8050, relay/quạt | — | GPIO27, GPIO23 để trống | `config.h`: `HAS_LED_YELLOW 0`, `HAS_RELAY 0` |

## Kiểm tra trước khi cấp điện
1. Đo thông mạch GND chung; không chập 5V–GND, 3V3–GND.
2. Đo điện áp nút giữa R1/R2 khi MQ-2 cấp 5 V: phải ≤ 3,3 V.
3. Nạp firmware, mở `pio device monitor`: kiểm tra log I²C tìm thấy 0x23, 0x3C, 0x76.
4. MQ-2 cần làm nóng 24–48 giờ trước khi hiệu chuẩn R0 (lệnh `calibrate` trên dashboard).
