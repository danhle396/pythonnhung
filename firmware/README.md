# Firmware ESP32 — MicroPython

Toàn bộ firmware viết bằng **Python (MicroPython)**. Logic thuần (lọc, rule engine, nowcast, đệm offline, đóng gói
bản tin) chạy được cả trên PC nên được kiểm thử bằng pytest; phần chạm phần cứng nằm riêng trong vài module.

| File | Vai trò |
|---|---|
| `main.py`, `boot.py` | Khởi động: dựng phần cứng, luồng mạng (`_thread`), vòng lặp chính, watchdog 30 s |
| `config.py` | Chân GPIO, chu kỳ, ngưỡng mặc định, cờ phần cứng (`HAS_LED_YELLOW`, `HAS_RELAY`) |
| `credentials_example.py` | Mẫu Wi-Fi/MQTT → chép thành `credentials.py` (không đưa lên git) |
| `compat.py` | `ticks_ms`, giờ Unix/giờ VN, khoá luồng — chạy được cả MicroPython lẫn CPython |
| `filters.py` | Vòng đệm, median-5, EWMA, điểm sương, chỉ số nhiệt, áp suất mực biển |
| `edge_ai.py`, `alert.py` | MQ-2 → ppm, 10 feature, rule 4 cấp (hysteresis/debounce), fusion với model, mute/escalate |
| `nowcast.py` | Zambretti theo xu hướng áp suất 3 giờ, nạp lại mẫu sau khi khởi động lại |
| `readings.py` | Số đo thô → `SensorData` đã lọc, mức mưa, lỗi cảm biến |
| `station.py`, `payloads.py` | Điều phối: cảm biến → edge → bản tin MQTT; xử lý `cmd`/`config`/`forecast` |
| `storage.py` | Đệm offline 2 000 bản ghi, `/config.json`, `seq`, mẫu nowcast trên flash |
| `sensors.py`, `drivers.py` | DHT22, ADC (YL-83, MQ-2), driver BMP280/BH1750 tự viết |
| `st7735.py`, `display.py` | Driver màn TFT ST7735 (SPI + framebuf) tự viết, 3 trang hiển thị |
| `mqtt.py`, `net.py`, `ota.py` | MQTT 3.1.1 client tự viết, Wi-Fi/NTP/kết nối lại, cập nhật qua HTTP |
| `gas_model.py` | Model cây sinh tự động bởi `ml/mlcore/export_micropython.py` (`AVAILABLE = False` khi chưa có dữ liệu thật) |

## Nạp lên board

```bash
pip install -r firmware/requirements.txt
# 1. lần đầu: nạp MicroPython ESP32_GENERIC (https://micropython.org/download/ESP32_GENERIC/)
python -m esptool --chip esp32 --port COM5 erase_flash
python -m esptool --chip esp32 --port COM5 --baud 460800 write_flash 0x1000 ESP32_GENERIC-<phiên bản>.bin
# 2. cấu hình Wi-Fi/MQTT
cp firmware/src/credentials_example.py firmware/src/credentials.py   # rồi sửa
# 3. chép code (biên dịch .mpy) và khởi động lại
python firmware/deploy.py --port COM5
python -m mpremote connect COM5 repl         # xem log, Ctrl-] để thoát
```

- Dùng **Thonny**: `python firmware/deploy.py --source --port COM5` (chép nguyên `.py`), hoặc mở từng file trong
  `firmware/src/` rồi *Save as… → MicroPython device*.
- Cập nhật qua mạng: `python firmware/deploy.py --ota build/ota`, `python -m http.server 8080 -d build/ota`, rồi gửi
  lệnh `{"cmd":"ota","url":"http://<IP máy>:8080/manifest.json"}` từ dashboard/API.
- Đo thời gian Edge AI trên ESP32: `python -m mpremote connect COM5 run firmware/bench_device.py`.

## Kiểm thử trên PC

```bash
python -m pytest -q firmware/tests          # logic, driver, đệm offline, toàn luồng trạm, MQTT, mpy-cross
python firmware/deploy.py --check           # chỉ biên dịch kiểm tra cú pháp MicroPython
```
