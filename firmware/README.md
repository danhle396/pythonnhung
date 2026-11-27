# Firmware ESP32 — MicroPython

Toàn bộ firmware viết bằng **Python (MicroPython)**. Logic thuần (lọc, rule engine, đệm offline, đóng gói
bản tin) chạy được cả trên PC nên được kiểm thử bằng pytest; phần chạm phần cứng nằm riêng trong vài module.

| File                          | Vai trò                                                                                                     |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `main.py`, `boot.py`          | Khởi động: dựng phần cứng, luồng mạng (`_thread`), vòng lặp chính, watchdog 30 s                            |
| `config.py`                   | Chân GPIO, chu kỳ, ngưỡng mặc định, cờ phần cứng (`HAS_LED_YELLOW`, `HAS_RELAY`)                            |
| `credentials.py`              | Wi-Fi/MQTT của trạm, tự tạo trên máy (không đưa lên git) — xem mục Nạp lên board                            |
| `compat.py`                   | `ticks_ms`, giờ Unix/giờ VN, khoá luồng — chạy được cả MicroPython lẫn CPython                              |
| `filters.py`                  | Vòng đệm, median-5, EWMA, điểm sương, chỉ số nhiệt, áp suất mực biển                                        |
| `edge_gas.py`, `alert.py`     | MQ-2 → ppm, độ dốc ppm + nhiệt độ tăng, luật 4 cấp (hysteresis/debounce), mute/escalate                    |
| `readings.py`                 | Số đo thô → `SensorData` đã lọc, mức mưa, lỗi cảm biến                                                      |
| `station.py`, `payloads.py`   | Điều phối: cảm biến → edge → bản tin MQTT; xử lý `cmd`/`config`/`forecast`                                  |
| `storage.py`                  | Đệm offline 2 000 bản ghi, `/config.json`, `seq` trên flash                                                 |
| `sensors.py`, `drivers.py`    | DHT22, ADC (YL-83, MQ-2), driver BMP280/BH1750 tự viết                                                      |
| `st7735.py`, `display.py`     | Driver màn TFT ST7735 (SPI + framebuf) tự viết, 3 trang hiển thị                                            |
| `mqtt.py`, `net.py`, `ota.py` | MQTT 3.1.1 client tự viết, Wi-Fi/NTP/kết nối lại, cập nhật qua HTTP                                         |

## Nạp lên board

```bash
pip install -r firmware/requirements.txt
# 1. lần đầu: nạp MicroPython ESP32_GENERIC (https://micropython.org/download/ESP32_GENERIC/)
python -m esptool --chip esp32 --port COM5 erase_flash
python -m esptool --chip esp32 --port COM5 --baud 460800 write_flash 0x1000 ESP32_GENERIC-<phiên bản>.bin
# 2. cấu hình Wi-Fi/MQTT
#    tạo firmware/src/credentials.py (không đưa lên git):
#      WIFI_SSID = "ten-wifi"
#      WIFI_PASS = "mat-khau"
#      MQTT_HOST = "192.168.1.10"   # IP máy chạy Mosquitto
#      MQTT_PORT = 1883
#      MQTT_USER = "station01"
#      MQTT_PASS = "change-me"
#      # MQTT_CA_FILE = "ca.crt"    # TLS cổng 8883 (tuỳ chọn, chép ca.crt lên board)
# 3. chép code (biên dịch .mpy) và khởi động lại
python firmware/deploy.py --port COM5
python -m mpremote connect COM5 repl         # xem log, Ctrl-] để thoát
```

- Dùng **Thonny**: `python firmware/deploy.py --source --port COM5` (chép nguyên `.py`), hoặc mở từng file trong
  `firmware/src/` rồi *Save as… → MicroPython device*.
- Cập nhật qua mạng: `python firmware/deploy.py --ota build/ota`, `python -m http.server 8080 -d build/ota`, rồi gửi
  lệnh `{"cmd":"ota","url":"http://<IP máy>:8080/manifest.json"}` từ dashboard/API.
- Đo thời gian Edge AI trên ESP32: `python -m mpremote connect COM5 run firmware/bench_device.py`.

## Đấu dây và kiểm tra trước khi cấp điện

Sơ đồ đấu dây: `docs/hardware/wiring-1.png` (cảm biến), `wiring-2.png` (còi, LED, màn TFT); chân theo `src/config.py`.
Đổi chân: sửa `src/config.py` **và** `docs/hardware/gen_wiring_drawio.py`, rồi chạy
`python docs/hardware/gen_wiring_drawio.py` và `python tools/render_drawio.py docs/hardware/wiring.drawio`.

1. Đo thông mạch GND chung; không chập 5V–GND, 3V3–GND.
2. Đo điện áp AO của MQ-2 (cấp 5 V) trong không khí sạch: phải ≤ 3,3 V vì AO nối thẳng GPIO32, không phân áp.
3. Nạp firmware, mở REPL: log `[SENS] I2C ['0x23', '0x76'] BMP280:1 BH1750:1`; màn TFT hiện "Tram AIoT" rồi 3 trang luân phiên.
4. Màn TFT trắng xoá / sai màu / lệch 1–2 hàng điểm ở mép → đổi `TFT_TAB` (`"black"` → `"green"` hoặc `"red"`); hình ngược →
   `TFT_ROTATION = 3`. Cấp VCC màn = 3V3; **không** cấp 5 V nếu jumper J1 đã được hàn nối.
5. MQ-2 cần làm nóng 24–48 giờ trước khi hiệu chuẩn R0 (lệnh `calibrate` trên dashboard).

## Kiểm thử trên PC

```bash
python -m pytest -q firmware/tests          # logic, driver, đệm offline, toàn luồng trạm, MQTT, mpy-cross
python firmware/deploy.py --check           # chỉ biên dịch kiểm tra cú pháp MicroPython
```
