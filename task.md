# TASK — AIoT Environmental Monitoring Station

> **Đề tài:** An AIoT Environmental Monitoring Station for Short-Term Weather Forecasting and Multi-Level Early Warning of Combustible Gas and Smoke Using Hybrid Edge–Cloud AI on ESP32 and MQTT.
>
> **Tên tiếng Việt:** Trạm quan trắc môi trường AIoT dự báo thời tiết ngắn hạn và cảnh báo sớm đa cấp khí dễ cháy và khói, sử dụng AI lai Edge–Cloud trên ESP32 và MQTT.

---

## 0. Ghi chú quan trọng trước khi bắt đầu

- [ ] **Bổ sung cảm biến khí/khói.** Danh sách phần cứng hiện có (YL-83, BH1750, DHT22, BMP280) **không có cảm biến nào đo khí dễ cháy hoặc khói**, mà đây là một nửa đề tài. Cần mua thêm tối thiểu **MQ-2** (LPG, propane, H₂, CH₄, khói). Tuỳ chọn thêm: MQ-5 (LPG/khí thiên nhiên), MQ-135 (chất lượng không khí) để cảnh báo chính xác hơn.
- [ ] Danh sách có ghi BH1750 hai lần. Một module BH1750 là đủ. Nếu có hai module thì cái thứ hai phải đổi địa chỉ I2C (ADDR nối VCC → `0x5C`) hoặc để làm dự phòng.
- [ ] MQ-2 xuất tín hiệu analog tới 5V, còn ADC của ESP32 chỉ chịu được **3.3V**, nên phải dùng cầu phân áp (ví dụ 10kΩ/20kΩ).
- [ ] Mọi chân analog phải nằm trên **ADC1** (GPIO32–39) vì ADC2 không dùng được khi Wi-Fi đang bật.
- [ ] **Toàn bộ mô hình AI/ML tự xây dựng từ đầu**, không dùng thư viện ML có sẵn. Chỉ dùng NumPy/pandas cho tính toán và xử lý dữ liệu (xem mục 8).
- [ ] Hệ thống chỉ là **nguyên mẫu học thuật**, không thay thế thiết bị báo cháy/báo gas đã được chứng nhận. Ghi rõ điều này trong báo cáo.

---

## 1. Mục tiêu đề tài

### 1.1 Mục tiêu chức năng
1. Thu thập liên tục: nhiệt độ, độ ẩm (DHT22), áp suất và nhiệt độ phụ (BMP280), cường độ ánh sáng (BH1750), mưa (YL-83), khí dễ cháy/khói (MQ-2).
2. Truyền dữ liệu thời gian thực qua **MQTT** lên server.
3. **Dự báo thời tiết ngắn hạn** (1h / 3h / 6h): nhiệt độ, độ ẩm, áp suất, xác suất mưa.
4. **Cảnh báo sớm đa cấp** khí dễ cháy/khói: 4 cấp (Bình thường → Chú ý → Cảnh báo → Nguy hiểm).
5. **AI lai Edge–Cloud:**
   - **Edge (ESP32):** phát hiện bất thường và cảnh báo khí ngay tại chỗ, vẫn hoạt động khi mất mạng; nowcast thời tiết đơn giản theo xu hướng áp suất.
   - **Cloud (Python):** mô hình dự báo thời tiết, xác nhận/leo thang cảnh báo, huấn luyện lại và đẩy cấu hình/ngưỡng xuống thiết bị.
6. Dashboard web theo dõi realtime, lịch sử, dự báo và cảnh báo; thông báo qua Telegram/Email.

### 1.2 Chỉ tiêu đánh giá (KPI)
| Hạng mục | Chỉ tiêu mục tiêu |
|---|---|
| Độ trễ cảnh báo tại edge (từ lúc vượt ngưỡng đến khi còi kêu) | < 1 giây |
| Độ trễ cảnh báo end-to-end (từ cảm biến đến Telegram) | < 5 giây |
| Tỉ lệ mất gói MQTT (QoS 1) | < 1% |
| MAE dự báo nhiệt độ 1h | < 1.0 °C |
| MAE dự báo độ ẩm 1h | < 5 %RH |
| F1 phân loại mưa / không mưa (3h tới) | > 0.75 |
| Recall cảnh báo khí cấp ≥ 2 | ≥ 0.95 (ưu tiên không bỏ sót) |
| Thời gian chạy liên tục không treo | ≥ 72 giờ |

### 1.3 Địa điểm triển khai
| Thông số | Giá trị | Dùng cho |
|---|---|---|
| Vị trí | Trường ĐH CNTT & TT Việt – Hàn (VKU), 470 Trần Đại Nghĩa, P. Hoà Quý, Q. Ngũ Hành Sơn, Đà Nẵng | — |
| Toạ độ | ≈ **15.975°N, 108.253°E** (xác nhận lại trên Google Maps tại đúng chỗ đặt trạm) | Tải Open-Meteo, tính góc mặt trời và lux khi trời quang |
| Độ cao | ≈ 5–10 m so với mực nước biển (đo lại bằng bản đồ địa hình hoặc GPS) | Quy áp suất về mực nước biển |
| Múi giờ | `Asia/Ho_Chi_Minh` (UTC+7) | NTP, Open-Meteo, feature giờ trong ngày |
| Khí hậu | Nhiệt đới gió mùa. **Mùa mưa tháng 9–12** (cao điểm tháng 10–11, có bão và áp thấp nhiệt đới), mùa khô tháng 1–8. Gần biển, độ ẩm trung bình khoảng 80% | Tập test phải bao trọn mùa mưa. Nhãn mưa mất cân bằng theo mùa |

- [ ] Đặt các giá trị trên vào `firmware/include/config.h` (`STATION_LAT`, `STATION_LON`, `STATION_ALT_M`) và `.env` của backend.
- [ ] Đề tài đang triển khai **giữa mùa mưa (tháng 11/2026)**, rất thuận lợi để thu dữ liệu mưa thật. Nên đặt trạm ngoài trời và thu liên tục càng sớm càng tốt.
- [ ] Vị trí đặt: nơi thoáng, không bị mái che chắn mưa, tránh phản xạ nhiệt từ tường bê tông và máy lạnh. Tấm YL-83 nghiêng 30–45°.

---

## 2. Phần cứng

### 2.1 Danh sách linh kiện (BOM)
| # | Linh kiện | Chức năng | Giao tiếp | Ghi chú |
|---|---|---|---|---|
| 1 | ESP32 DevKit V1 (ESP-WROOM-32) | Vi điều khiển, Wi-Fi, Edge AI | — | Có sẵn |
| 2 | DHT22 (AM2302) | Nhiệt độ, độ ẩm | 1-Wire (GPIO) | Có sẵn. Đọc tối đa 1 lần / 2 giây |
| 3 | BMP280 | Áp suất, nhiệt độ | I2C `0x76`/`0x77` | Có sẵn |
| 4 | BH1750 | Cường độ ánh sáng (lux) | I2C `0x23` | Có sẵn |
| 5 | YL-83 (+ module LM393) | Phát hiện / mức độ mưa | Analog + Digital | Có sẵn |
| 6 | **MQ-2** | Khí dễ cháy, khói | Analog + Digital | **Cần mua** |
| 7 | Buzzer active 5V/3.3V | Còi cảnh báo | GPIO | Cần mua |
| 8 | LED xanh / vàng / đỏ (+ điện trở 220Ω) | Đèn báo cấp cảnh báo | GPIO | Cần mua |
| 9 | OLED SSD1306 0.96" (tuỳ chọn) | Hiển thị tại chỗ | I2C `0x3C` | Khuyến nghị |
| 10 | Relay 5V hoặc quạt nhỏ (tuỳ chọn) | Hành động tự động (bật quạt hút) | GPIO | Tuỳ chọn |
| 11 | Nút nhấn | Tắt còi / xác nhận cảnh báo | GPIO (pull-up) | Cần mua |
| 12 | Điện trở 10kΩ + 20kΩ | Phân áp cho MQ-2 AO | — | Cần mua |
| 13 | Nguồn 5V/2A, breadboard, dây | Cấp nguồn | — | MQ-2 tiêu thụ khoảng 150mA do có bộ gia nhiệt |
| 14 | Hộp nhựa có khe thông gió | Đóng gói trạm | — | YL-83 đặt ngoài trời, DHT22 đặt trong vỏ che nắng |

### 2.2 Sơ đồ chân (đề xuất)
| Thiết bị | Chân thiết bị | Chân ESP32 |
|---|---|---|
| I2C bus (BMP280, BH1750, OLED) | SDA / SCL | GPIO21 / GPIO22 |
| DHT22 | DATA | GPIO4 (pull-up 10kΩ) |
| YL-83 | AO / DO | GPIO34 / GPIO35 |
| MQ-2 | AO (qua phân áp) / DO | GPIO32 / GPIO33 |
| Buzzer | + | GPIO25 |
| LED xanh / vàng / đỏ | Anode | GPIO26 / GPIO27 / GPIO14 |
| Nút nhấn | — | GPIO13 (INPUT_PULLUP) |
| Relay/quạt | IN | GPIO23 |

### 2.3 Công việc phần cứng
- [ ] Vẽ sơ đồ nguyên lý (Fritzing hoặc KiCad) và lưu vào `docs/hardware/`.
- [ ] Chạy I2C scanner để xác nhận địa chỉ của BMP280, BH1750 và OLED.
- [ ] Test riêng từng cảm biến bằng sketch tối giản và ghi kết quả.
- [ ] **Burn-in MQ-2 24–48 giờ** trước khi hiệu chuẩn.
- [ ] Hiệu chuẩn MQ-2: đo `R0` trong không khí sạch (`Rs/R0 ≈ 9.83`), sau đó tính ppm theo đường cong datasheet (`ppm = a · (Rs/R0)^b`).
- [ ] Hiệu chuẩn YL-83: ghi giá trị ADC khi khô, ẩm nhẹ và ướt đẫm để chia thành 4 mức (khô / mưa phùn / mưa vừa / mưa to).
- [ ] So sánh nhiệt độ DHT22 và BMP280 để phát hiện lệch, đồng thời so với nhiệt kế tham chiếu nếu có.
- [ ] Lắp ráp vào hộp, chụp ảnh thực tế cho báo cáo.

---

## 3. Kiến trúc hệ thống

```
┌──────────────────────── EDGE (ESP32) ────────────────────────┐
│ Sensors → Sampling → Filter (median/EWMA) → Feature extract  │
│     │                                         │              │
│     │                     ┌───────────────────┴───────────┐  │
│     │                     │ Edge AI                        │  │
│     │                     │ • Gas/Smoke risk classifier    │  │
│     │                     │ • Rule engine (threshold+ROC)  │  │
│     │                     │ • Pressure-trend nowcast       │  │
│     │                     └───────────────┬───────────────┘  │
│     │           Local actuators ◄─────────┤ (buzzer/LED/OLED)│
│     │           Offline buffer (SPIFFS) ◄─┤ khi mất mạng     │
└─────┼─────────────────────────────────────┼──────────────────┘
      │ MQTT (TLS tuỳ chọn), QoS 0/1, LWT    │
┌─────▼─────────────────────────────────────▼──────── CLOUD ───┐
│ Mosquitto Broker                                              │
│   ├─► Ingestion service (Python, paho-mqtt) ─► DB (Postgres/  │
│   │                                            Timescale/     │
│   │                                            InfluxDB)      │
│   ├─► Alert service: xác nhận / leo thang ─► Telegram/Email   │
│   ├─► Forecast service: mô hình ML/DL, chạy mỗi 10–15 phút    │
│   └─► Config/OTA service: đẩy ngưỡng, model mới xuống edge    │
│ REST API (FastAPI) + WebSocket ─► Dashboard (React/Streamlit) │
└───────────────────────────────────────────────────────────────┘
```

### 3.1 Phân chia trách nhiệm Edge và Cloud
| Chức năng | Edge (ESP32) | Cloud (Python) |
|---|---|---|
| Lọc nhiễu, tính feature | ✅ | — |
| Cảnh báo khí/khói tức thì | ✅ (quyết định chính) | Xác nhận, leo thang, thông báo |
| Hoạt động khi mất mạng | ✅ (đệm offline) | — |
| Nowcast thời tiết (xu hướng áp suất) | ✅ (kiểu Zambretti) | — |
| Dự báo 1h/3h/6h | — | ✅ (ML/DL) |
| Huấn luyện mô hình | — | ✅ |
| Lưu trữ dài hạn, dashboard | — | ✅ |
| Cập nhật ngưỡng / model | Nhận | Gửi (MQTT `config`, OTA) |

---

## 4. Cấu trúc thư mục dự án

```
final/
├── task.md
├── README.md
├── docker-compose.yml          # mosquitto, db, api, dashboard, grafana (tuỳ chọn)
├── .env.example
├── docs/
│   ├── hardware/               # sơ đồ, ảnh lắp ráp
│   ├── architecture/           # sơ đồ kiến trúc, sequence, MQTT topics
│   └── report/                 # báo cáo, slide
├── firmware/                   # PlatformIO project (ESP32, Arduino framework)
│   ├── platformio.ini
│   ├── include/
│   │   ├── config.h            # pin, Wi-Fi, MQTT, ngưỡng mặc định
│   │   └── gas_model.h         # model edge sinh từ ml/mlcore/export_c.py
│   └── src/
│       ├── main.cpp
│       ├── sensors.cpp/.h
│       ├── filters.cpp/.h
│       ├── edge_ai.cpp/.h
│       ├── alert.cpp/.h
│       ├── nowcast.cpp/.h
│       ├── mqtt_client.cpp/.h
│       └── storage.cpp/.h      # đệm offline SPIFFS/LittleFS
├── broker/
│   └── mosquitto/
│       ├── mosquitto.conf
│       ├── passwd
│       └── acl
├── backend/                    # Python
│   ├── pyproject.toml / requirements.txt
│   ├── app/
│   │   ├── main.py             # FastAPI
│   │   ├── core/config.py
│   │   ├── db/ (models.py, session.py, migrations/)
│   │   ├── mqtt/ (ingest.py, publisher.py)
│   │   ├── services/ (alert_service.py, forecast_service.py, notifier.py)
│   │   ├── api/ (telemetry.py, alerts.py, forecast.py, devices.py, ws.py)
│   │   └── schemas/
│   └── tests/
├── ml/
│   ├── requirements.txt        # chỉ numpy, pandas, matplotlib
│   ├── data/ (raw/, external/, processed/)
│   ├── notebooks/              # EDA, thử nghiệm
│   ├── mlcore/                 # thư viện ML tự xây dựng (xem mục 8.1)
│   │   ├── preprocessing.py, model_selection.py, metrics.py
│   │   ├── linear.py, smoothing.py, tree.py, ensemble.py
│   │   ├── anomaly.py, nn.py, optim.py, explain.py
│   │   └── serialize.py, export_c.py
│   ├── tests/                  # unit test + gradient check cho mlcore
│   ├── src/
│   │   ├── fetch_open_meteo.py
│   │   ├── features.py
│   │   ├── train_forecast.py
│   │   ├── train_gas_edge.py
│   │   ├── export_edge_model.py
│   │   └── evaluate.py
│   └── models/                 # *.json (cây), *.npz (trọng số) + model card
├── dashboard/                  # Streamlit hoặc React + Vite
└── tools/
    ├── simulator.py            # giả lập ESP32 publish MQTT
    └── load_test.py
```

- [ ] Khởi tạo cấu trúc thư mục trên.
- [ ] `git init`, thêm `.gitignore` (bỏ qua `.env`, `__pycache__`, `.pio`, `ml/data/raw`, `ml/models/*.npz`).

---

## 5. Thiết kế MQTT

### 5.1 Topic
Tiền tố: `vku/aiot/{device_id}/...` (ví dụ `device_id = station01`)

| Topic | Chiều | QoS | Retain | Nội dung |
|---|---|---|---|---|
| `.../telemetry` | Edge → Cloud | 0 hoặc 1 | ❌ | Dữ liệu cảm biến định kỳ (5–10 giây) |
| `.../alert` | Edge → Cloud | 1 | ❌ | Sự kiện cảnh báo khí/khói (khi đổi cấp) |
| `.../nowcast` | Edge → Cloud | 0 | ✅ | Kết quả nowcast tại edge |
| `.../status` | Edge → Cloud | 1 | ✅ | `online` / `offline` (LWT), RSSI, uptime, heap |
| `.../forecast` | Cloud → Edge | 1 | ✅ | Dự báo 1h/3h/6h để hiển thị trên OLED |
| `.../cmd` | Cloud → Edge | 1 | ❌ | `mute`, `reboot`, `calibrate`, `test_alarm` |
| `.../config` | Cloud → Edge | 1 | ✅ | Ngưỡng, chu kỳ gửi, phiên bản model |
| `.../ack` | Edge → Cloud | 1 | ❌ | Xác nhận đã nhận cmd/config |

### 5.2 Payload mẫu (JSON)
```json
// telemetry
{
  "device_id": "station01",
  "ts": 1762671600,
  "seq": 10234,
  "temp_dht": 29.4, "hum": 78.2,
  "temp_bmp": 29.9, "pressure": 1008.6,
  "lux": 15230,
  "rain_raw": 3810, "rain_level": 0,
  "gas_raw": 812, "gas_rs_r0": 7.9, "gas_ppm": 210,
  "gas_slope": 0.4,
  "edge_risk": 0, "edge_score": 0.03,
  "fw": "1.0.0", "model_ver": "gas-v1"
}
```
```json
// alert
{
  "device_id": "station01", "ts": 1762671620,
  "level": 2, "prev_level": 1,
  "cause": ["gas_ppm>1000", "slope_high"],
  "gas_ppm": 1350, "score": 0.87,
  "action": ["buzzer_intermittent", "led_red_blink"]
}
```

### 5.3 Công việc MQTT
- [ ] Cài Mosquitto (Docker), bật xác thực username/password và ACL theo thiết bị.
- [ ] Cấu hình LWT: topic `.../status`, payload `offline`, retain.
- [ ] (Nâng cao) Bật TLS cổng 8883 với self-signed CA và nhúng CA vào firmware.
- [ ] Viết `tools/simulator.py` để giả lập thiết bị (kể cả kịch bản rò gas) nhằm phát triển backend khi chưa có phần cứng.
- [ ] Viết tài liệu topic/payload trong `docs/architecture/mqtt.md`.

---

## 6. Firmware ESP32 (Edge)

**Nền tảng:** PlatformIO + Arduino framework (hoặc ESP-IDF). Thư viện: `PubSubClient` hoặc `AsyncMqttClient`, `DHT sensor library`, `Adafruit BMP280`, `BH1750` (claws), `ArduinoJson`, `Adafruit SSD1306`, `LittleFS`.

### 6.1 Nền tảng
- [ ] Tạo project PlatformIO, cấu hình `platformio.ini` (board `esp32dev`, monitor 115200, partition có LittleFS).
- [ ] `config.h`: pin, ngưỡng mặc định, chu kỳ đọc. Tách thông tin Wi-Fi/MQTT ra `secrets.h` (đưa vào .gitignore).
- [ ] Kết nối Wi-Fi có tự kết nối lại; (tuỳ chọn) WiFiManager để cấu hình qua captive portal.
- [ ] Đồng bộ thời gian NTP (`pool.ntp.org`, GMT+7).
- [ ] Bật watchdog (Task WDT).
- [ ] Dùng FreeRTOS tasks:
  - `TaskSensors` (core 1): đọc cảm biến mỗi 1 giây (DHT22 mỗi 2 giây).
  - `TaskEdgeAI` (core 1): tính feature, chạy rule và model, điều khiển còi/LED.
  - `TaskNetwork` (core 0): MQTT publish/subscribe, đệm offline.
  - Giao tiếp giữa các task bằng Queue và Mutex.

### 6.2 Đọc và tiền xử lý cảm biến
- [ ] Driver từng cảm biến, xử lý lỗi (NaN, timeout I2C) và đánh dấu `sensor_ok`.
- [ ] Lọc median (cửa sổ 5) để loại spike, rồi EWMA (α = 0.2–0.3).
- [ ] ADC: dùng `analogReadMilliVolts()` (đã hiệu chỉnh), lấy trung bình 16 mẫu.
- [ ] MQ-2: tính `Rs = RL·(Vc − Vout)/Vout`, `Rs/R0` và ppm. Sau khi bật nguồn, đợi warm-up khoảng 60 giây (trạng thái `warming_up`, chưa cảnh báo).
- [ ] YL-83: ánh xạ ADC sang `rain_level` 0–3. Chỉ cấp nguồn cho module lúc đọc (qua GPIO) để giảm ăn mòn bản mạch.
- [ ] Tính áp suất quy về mực nước biển (độ cao trạm tại VKU ≈ 5–10 m, xem mục 1.3) để so sánh được với `pressure_msl` của Open-Meteo.
- [ ] Tính các đại lượng dẫn xuất: điểm sương, heat index.

### 6.3 Edge AI — Cảnh báo khí/khói đa cấp
**Feature (cửa sổ trượt 10–30 giây):** `gas_ppm`, `rs_r0`, độ dốc `d(ppm)/dt`, độ lệch chuẩn, độ lệch so với baseline động, `temp` và `d(temp)/dt`, `hum` (độ ẩm ảnh hưởng MQ-2), `lux` (lửa hoặc khói có thể làm thay đổi ánh sáng).

**Cấp cảnh báo (ngưỡng mặc định, có thể chỉnh qua `config`):**
| Cấp | Tên | Điều kiện gợi ý (LPG, ppm) | Hành động tại edge |
|---|---|---|---|
| 0 | Normal | ppm < 300 và slope thấp | LED xanh |
| 1 | Advisory (Chú ý) | 300–1000 ppm **hoặc** slope tăng bất thường **hoặc** model score > 0.5 | LED vàng, gửi alert |
| 2 | Warning (Cảnh báo) | 1000–2000 ppm **hoặc** score > 0.75 kéo dài ≥ 5 giây | LED đỏ nhấp nháy, còi ngắt quãng, bật quạt |
| 3 | Danger (Nguy hiểm) | > 2000 ppm (≈ 10% LEL của LPG) **hoặc** cấp 2 kèm nhiệt độ tăng nhanh (> 1°C/phút) | LED đỏ sáng liên tục, còi liên tục, relay |

- [ ] **Rule engine:** ngưỡng ppm, rate-of-change, có **hysteresis** (ví dụ phải xuống dưới ngưỡng − 15% mới hạ cấp) và **debounce** (thoả điều kiện N mẫu liên tiếp mới tăng cấp, riêng cấp 3 tăng ngay).
- [ ] **Model nhẹ** (chạy trên ESP32): Decision Tree, Random Forest nhỏ hoặc Logistic Regression **tự build** trong `ml/mlcore`, huấn luyện ở `ml/src/train_gas_edge.py`, xuất sang C header bằng `mlcore/export_c.py` tự viết. Firmware chỉ cần duyệt mảng node, không dùng thư viện suy luận nào. (Nâng cao: MLP nhỏ tự viết, xuất trọng số thành mảng C, suy luận bằng vòng lặp nhân ma trận.)
- [ ] **Hợp nhất (fusion):** `level = max(rule_level, model_level)`. Quy tắc an toàn: model không được phép hạ cấp do rule đưa ra.
- [ ] Nút nhấn: tắt còi 5 phút (mute) nhưng vẫn giữ cấp và LED. Nếu cấp tăng thêm thì còi kêu lại.
- [ ] Publish `alert` mỗi khi cấp thay đổi, kèm `cause`.
- [ ] Bộ phát hiện **lỗi cảm biến**: MQ-2 đứng yên giá trị (stuck), mất kết nối, ADC bão hoà. Khi đó gửi alert loại `sensor_fault`.

### 6.4 Edge — Nowcast thời tiết
- [ ] Lưu áp suất 3 giờ gần nhất (vòng đệm, 1 mẫu / 10 phút).
- [ ] Tính xu hướng áp suất: tăng / ổn định / giảm (ngưỡng ±1.6 hPa / 3h).
- [ ] Áp dụng thuật toán kiểu **Zambretti** kết hợp `rain_level` và `hum` để đưa ra nowcast: "Trời đẹp", "Có thể mưa", "Mưa sắp tới"...
- [ ] Publish lên `.../nowcast` và hiển thị trên OLED.

### 6.5 Truyền thông và độ tin cậy
- [ ] Publish telemetry mỗi 5–10 giây (cấu hình được). Khi đang có cảnh báo thì tăng lên 1 giây.
- [ ] Đệm offline: khi mất MQTT, ghi bản ghi vào LittleFS (vòng đệm khoảng 2000 bản ghi). Khi kết nối lại, gửi bù (có `seq` để chống trùng).
- [ ] Subscribe `cmd`, `config`, `forecast`. Kiểm tra hợp lệ JSON, áp dụng config, lưu config vào NVS (Preferences) và gửi `ack`.
- [ ] Gửi `status` định kỳ: RSSI, uptime, free heap, phiên bản firmware và model.
- [ ] (Nâng cao) OTA firmware qua HTTP (`HTTPUpdate`) khi nhận lệnh `cmd: ota`.

### 6.6 Hiển thị cục bộ (OLED)
- [ ] Trang 1: T / H / P / Lux / Rain.
- [ ] Trang 2: Gas ppm, cấp cảnh báo.
- [ ] Trang 3: Nowcast tại edge và dự báo từ cloud.
- [ ] Trạng thái Wi-Fi/MQTT ở góc màn hình. Khi có cảnh báo cấp ≥ 2 thì luôn ưu tiên hiển thị trang cảnh báo.

---

## 7. Backend Cloud (Python)

**Stack:** Python 3.11+, FastAPI, paho-mqtt (hoặc `aiomqtt`), SQLAlchemy 2 + Alembic, PostgreSQL (+ TimescaleDB) **hoặc** InfluxDB, Pydantic v2, APScheduler, python-telegram-bot hoặc gọi trực tiếp HTTP API của Telegram, Docker Compose.

### 7.1 Cơ sở dữ liệu
- [ ] Bảng `devices` (id, name, location, lat, lon, altitude, fw, last_seen, status).
- [ ] Bảng `telemetry` (hypertable theo `ts`): toàn bộ trường trong payload.
- [ ] Bảng `alerts` (id, device_id, ts, level, prev_level, cause, source = edge/cloud, acknowledged_by, ack_ts).
- [ ] Bảng `forecasts` (device_id, created_at, horizon, target, value, lower, upper, model_ver).
- [ ] Bảng `nowcasts`, `device_configs`, `model_registry`.
- [ ] Viết migration Alembic.
- [ ] Downsampling/continuous aggregate theo 1 phút, 10 phút, 1 giờ. Chính sách giữ dữ liệu: dữ liệu thô 90 ngày.

### 7.2 Ingestion service
- [ ] Subscribe `vku/aiot/+/telemetry|alert|status|nowcast|ack`.
- [ ] Kiểm tra hợp lệ bằng Pydantic, loại giá trị ngoài dải vật lý (ví dụ T ngoài khoảng −10..60 °C, P ngoài 900..1100 hPa).
- [ ] Chống trùng theo `(device_id, seq)`.
- [ ] Ghi DB theo lô (batch insert), đồng thời đẩy sang WebSocket cho dashboard.
- [ ] Cập nhật `last_seen`. Nếu quá 60 giây không nhận dữ liệu thì đánh dấu offline và tạo alert `device_offline`.

### 7.3 Alert service (Cloud AI cho cảnh báo)
- [ ] Nhận alert từ edge và lưu lại, kèm logic **xác nhận/leo thang** ở cloud:
  - Kiểm tra ngữ cảnh dài hơn (5–15 phút): ppm tăng đều kéo dài thì leo thang.
  - Mô hình phát hiện bất thường ở cloud (Isolation Forest tự build trong `mlcore`, hoặc thống kê theo giờ trong ngày) để phát hiện rò rỉ chậm mà edge có thể bỏ sót.
  - Khi cloud leo thang thì gửi `cmd` xuống edge để nâng cấp cảnh báo.
- [ ] Gửi thông báo theo cấp:
  - Cấp 1: chỉ ghi log và hiện trên dashboard.
  - Cấp 2: Telegram.
  - Cấp 3: Telegram + Email, nhắc lại mỗi 1 phút cho tới khi có người xác nhận (ack).
- [ ] Rate-limit/cooldown để tránh spam thông báo.
- [ ] API xác nhận cảnh báo (ack) từ dashboard và từ nút inline trên Telegram.

### 7.4 Forecast service
- [ ] Chạy theo lịch mỗi 10–15 phút (APScheduler): lấy dữ liệu gần nhất, tạo feature, gọi model, lưu `forecasts`, publish `.../forecast`.
- [ ] Nạp model từ `model_registry` (phiên bản đang active): đọc JSON/.npz, suy luận bằng `mlcore`. Backend cài `ml/` dưới dạng package (`pip install -e ml/`) để dùng chung code với phần huấn luyện.
- [ ] Fallback: khi thiếu dữ liệu thì dùng mô hình persistence hoặc kết quả nowcast.

### 7.5 REST API và WebSocket
- [ ] `GET /api/devices`, `GET /api/devices/{id}`
- [ ] `GET /api/telemetry?device_id&from&to&resolution`
- [ ] `GET /api/telemetry/latest`
- [ ] `GET /api/forecast/{device_id}`
- [ ] `GET /api/alerts?level&from&to`, `POST /api/alerts/{id}/ack`
- [ ] `PUT /api/devices/{id}/config` (publish xuống topic `config`)
- [ ] `POST /api/devices/{id}/cmd` (`mute`, `test_alarm`, `calibrate`, `reboot`)
- [ ] `GET /api/export.csv`
- [ ] `WS /ws/live` để đẩy telemetry và alert realtime.
- [ ] Xác thực JWT cho các API ghi. Swagger tự sinh tại `/docs`.

---

## 8. Machine Learning (tự xây dựng từ đầu)

> **Ràng buộc:** Không dùng thư viện ML, deep learning hay thống kê dựng sẵn: scikit-learn, XGBoost, LightGBM, TensorFlow, Keras, PyTorch, statsmodels, Prophet, SHAP, emlearn, micromlgen. Mọi thuật toán (huấn luyện, suy luận, metric, chia dữ liệu, tối ưu, xuất sang C) đều tự cài đặt trong package `ml/mlcore/`.
>
> **Được phép dùng:** NumPy (phép toán mảng/ma trận), pandas (đọc ghi dữ liệu, resample chuỗi thời gian), matplotlib (vẽ hình cho báo cáo), thư viện chuẩn của Python (`json`, `math`, `random`, `pickle`...). Nếu giảng viên cấm cả NumPy, xem mục 8.9.

### 8.1 Thư viện `mlcore` tự xây dựng
| Module | Nội dung tự cài đặt |
|---|---|
| `preprocessing.py` | StandardScaler, MinMaxScaler, nội suy khoảng trống, loại outlier (IQR / z-score), tạo lag và rolling features, mã hoá sin/cos cho thời gian |
| `model_selection.py` | Chia train/val/test theo thời gian, TimeSeriesSplit (expanding window), grid search và random search |
| `metrics.py` | MAE, RMSE, MAPE, R², Accuracy, Precision, Recall, F1 (theo từng lớp và macro), confusion matrix, ROC-AUC (tính theo xếp hạng), Brier score |
| `linear.py` | Linear/Ridge Regression (nghiệm đóng `(XᵀX + λI)⁻¹Xᵀy` và bản gradient descent), Logistic Regression (mini-batch GD, L2) |
| `smoothing.py` | Holt-Winters (triple exponential smoothing, chu kỳ mùa 24h) |
| `tree.py` | CART: cây hồi quy (MSE) và cây phân loại (Gini/Entropy, có trọng số lớp), histogram binning, `max_depth`, `min_samples_leaf`, lưu cây dưới dạng mảng node |
| `ensemble.py` | Random Forest (bootstrap + chọn ngẫu nhiên tập feature), Gradient Boosting Trees (loss MSE và log-loss, learning rate, subsample, early stopping) |
| `anomaly.py` | Isolation Forest (độ dài đường đi, hệ số chuẩn hoá `c(n)`, anomaly score), CUSUM để phát hiện drift |
| `nn.py` | (Nâng cao) Dense, MLP, GRU/LSTM viết tay: forward, backprop/BPTT, gradient clipping |
| `optim.py` | SGD, Momentum, Adam |
| `explain.py` | Feature importance theo split gain, permutation importance (thay cho SHAP) |
| `serialize.py` | Lưu và tải model: cây ở dạng JSON, trọng số ở dạng `.npz`, kèm `model_ver` và hash dữ liệu huấn luyện |
| `export_c.py` | Sinh `gas_model.h` từ cây/rừng: mảng node `const` (feature, threshold, left, right, value) và hàm `predict()` viết bằng C |

- [ ] Cài đặt từng module, docstring ghi công thức toán (dùng lại cho chương 2 của báo cáo).
- [ ] Vector hoá bằng NumPy, tránh vòng lặp Python trên từng mẫu. Cây dùng histogram binning (64–256 bin) để huấn luyện đủ nhanh.
- [ ] Cố định `seed` cho mọi thành phần ngẫu nhiên để tái lập được kết quả.
- [ ] Mọi model có chung giao diện `fit(X, y)`, `predict(X)`, `predict_proba(X)`, `to_dict()`, `from_dict()`.

### 8.2 Kiểm chứng code tự viết là đúng
- [ ] Unit test trên dữ liệu đồ chơi có đáp án biết trước. Ví dụ: với `y = 3x + 2`, Linear Regression phải ra hệ số ≈ 3 và 2; với bài toán XOR, cây sâu 2 phải phân loại đúng 100%; Isolation Forest phải cho điểm cao với điểm ngoại lai được cài vào.
- [ ] **Gradient check** bằng sai phân hữu hạn cho Logistic Regression, MLP và GRU/LSTM, sai số tương đối < 1e-5.
- [ ] Đối chiếu metric với kết quả tính tay trên ví dụ nhỏ.
- [ ] Kiểm tra `predict()` bằng C trên ESP32 khớp 100% với `predict()` của Python trên cùng tập test (xuất một file vector kiểm thử dùng chung).
- [ ] (Tuỳ chọn, chỉ để đối chiếu trong báo cáo, **không** dùng trong pipeline) so sánh kết quả với scikit-learn trên cùng dữ liệu. Chênh lệch nhỏ chứng minh cài đặt đúng. Bỏ bước này nếu giảng viên cấm tuyệt đối.

### 8.3 Dữ liệu
- [ ] **Dữ liệu tự thu:** chạy trạm liên tục càng sớm càng tốt (mục tiêu ≥ 3–4 tuần).
- [ ] **Dữ liệu ngoài** (vì dữ liệu tự thu quá ít để huấn luyện): tải lịch sử thời tiết theo giờ tại VKU từ **Open-Meteo Historical API** (miễn phí, không cần key), khoảng 5 năm. Viết `ml/src/fetch_open_meteo.py`:
  ```
  https://archive-api.open-meteo.com/v1/archive
    ?latitude=15.975&longitude=108.253
    &start_date=2021-01-01&end_date=2025-12-31
    &hourly=temperature_2m,relative_humidity_2m,dew_point_2m,surface_pressure,
            pressure_msl,precipitation,rain,shortwave_radiation
    &timezone=Asia/Ho_Chi_Minh
  ```
  Lưu vào `ml/data/external/vku_hourly_2021_2025.csv`. Chỉ dùng các feature mà trạm cũng có (T, RH, P quy về mực nước biển, điểm sương, bức xạ hoặc lux quy về tỉ lệ so với trời quang, giờ, ngày).
- [ ] Chiến lược: **pretrain trên Open-Meteo, sau đó fine-tune hoặc hiệu chỉnh bias bằng dữ liệu trạm** (transfer learning hoặc bias correction). Ghi rõ trong báo cáo.
- [ ] **Dữ liệu khí/khói:** tự tạo kịch bản có kiểm soát và gán nhãn:
  - Không khí sạch ở nhiều mức nhiệt độ/độ ẩm (nhãn 0).
  - Bật lửa gas xả (không đốt) ở các khoảng cách 50 / 20 / 5 cm (nhãn 1/2/3).
  - Khói từ nhang hoặc giấy đốt trong hộp kín (nhãn khói).
  - Nhiễu: hơi nước, cồn, nước hoa (dùng để kiểm tra báo động giả).
  - **Thí nghiệm ở nơi thoáng, lượng nhỏ, có người giám sát, tránh xa nguồn lửa khi xả gas.**
- [ ] Ghi log nhãn bằng script (bấm phím để đánh dấu thời điểm bắt đầu/kết thúc sự kiện).

### 8.4 Tiền xử lý và feature (dùng `mlcore.preprocessing`)
- [ ] Resample về 10 phút / 1 giờ (pandas), nội suy khoảng trống ngắn, loại outlier (IQR / z-score tự viết).
- [ ] Feature thời gian: giờ trong ngày, ngày trong năm (mã hoá sin/cos).
- [ ] Lag features (t−1..t−6), rolling mean/std (1h, 3h, 6h), xu hướng áp suất 3h, điểm sương, chênh lệch nhiệt độ và điểm sương.
- [ ] Chia train/val/test **theo thời gian** (không shuffle), cross-validation bằng TimeSeriesSplit tự viết.
- [ ] Chuẩn hoá bằng StandardScaler tự viết. Chỉ `fit` trên tập train, lưu mean/std cùng model.

### 8.5 Mô hình dự báo thời tiết (Cloud)
| Mô hình (tự build) | Vai trò |
|---|---|
| Persistence / Seasonal naive (lặp lại giá trị cùng giờ hôm trước) | Baseline bắt buộc |
| Holt-Winters | Baseline thống kê (thay cho SARIMA/Prophet) |
| Ridge Regression trên lag features | Baseline tuyến tính |
| **Gradient Boosting Trees (loss MSE)** | **Mô hình chính** cho T/H/P, mỗi cặp target × horizon một model |
| **Gradient Boosting Trees (log-loss)**, so sánh với Logistic Regression | Xác suất mưa trong 1h / 3h |
| GRU/LSTM viết bằng NumPy (nâng cao) | So sánh với deep learning |

**Chi tiết Gradient Boosting cần cài đặt:**
- Giá trị khởi tạo: trung bình của `y` (MSE) hoặc log-odds (log-loss).
- Mỗi vòng: tính gradient `g` và hessian `h`, dựng một cây hồi quy theo histogram, giá trị lá tính theo bước Newton `−Σg / (Σh + λ)`.
- Shrinkage `η = 0.05–0.1`, `max_depth = 3–6`, subsample hàng 0.8, early stopping theo loss trên tập val.

**Công việc:**
- [ ] Huấn luyện các mô hình cho các horizon 1h, 3h, 6h.
- [ ] Metric (`mlcore.metrics`): MAE, RMSE, MAPE cho hồi quy; Accuracy, F1, ROC-AUC, Brier score cho dự báo mưa.
- [ ] Lập bảng so sánh các mô hình và chọn mô hình triển khai.
- [ ] Giải thích mô hình bằng split-gain importance và permutation importance tự viết, đưa vào báo cáo.
- [ ] Đo thời gian huấn luyện và suy luận của code tự viết.
- [ ] Lưu model (JSON/.npz qua `mlcore.serialize`), ghi `model_registry`, viết model card.

### 8.6 Mô hình cảnh báo khí/khói (Edge)
- [ ] Tự build Decision Tree CART (Gini, `max_depth ≤ 6`) hoặc Random Forest nhỏ (≤ 10 cây) trên feature cửa sổ trượt.
- [ ] Dùng **trọng số lớp** trong Gini (phạt nặng hơn khi bỏ sót cấp 2 và 3) để ưu tiên Recall.
- [ ] Metric: Precision/Recall/F1 theo từng cấp, ma trận nhầm lẫn. **Ưu tiên Recall** cho cấp ≥ 2.
- [ ] Xuất sang C bằng `mlcore/export_c.py` thành `firmware/include/gas_model.h`. Tuỳ chọn lượng tử hoá ngưỡng sang số nguyên (ví dụ ppm × 10) để tránh tính toán số thực.
- [ ] Đo kích thước model (kB flash), RAM và thời gian suy luận trên ESP32 (µs).
- [ ] Kiểm tra kết quả trên Python và trên ESP32 khớp nhau (mục 8.2).
- [ ] So sánh 3 phương án: chỉ rule, chỉ model, rule + model (hybrid). Đây là kết quả chính chứng minh giá trị của hybrid.

### 8.7 Phát hiện bất thường ở cloud
- [ ] Isolation Forest tự build trên chuỗi gas ppm dài hạn (kèm T/H) để phát hiện rò rỉ chậm.
- [ ] Z-score theo giờ trong ngày làm phương án đơn giản để so sánh.
- [ ] Phát hiện drift của MQ-2 bằng CUSUM tự viết trên baseline `R0`. Khi phát hiện drift thì đề xuất hiệu chuẩn lại.

### 8.8 Vòng đời mô hình (MLOps tối giản)
- [ ] Script `train_*.py` chạy được bằng CLI, cấu hình qua YAML/JSON.
- [ ] Ghi log thí nghiệm tự viết (CSV/JSON: tham số, metric, thời gian, `seed`).
- [ ] Huấn luyện lại định kỳ (hàng tuần) khi có thêm dữ liệu. Chỉ đổi sang model mới khi nó tốt hơn model cũ trên tập kiểm tra.
- [ ] Đẩy ngưỡng hoặc model edge mới qua `config`/OTA và ghi `model_ver`.

### 8.9 Phương án dự phòng nếu cấm cả NumPy
- [ ] Viết thêm `mlcore/linalg.py` bằng Python thuần: nhân ma trận, chuyển vị, giải hệ phương trình bằng khử Gauss.
- [ ] Giảm quy mô: resample về 1 giờ, dùng 1–2 năm dữ liệu, số bin ≤ 32, số cây ≤ 100.
- [ ] Bỏ GRU/LSTM, giữ Ridge, Holt-Winters, Gradient Boosting, CART/Random Forest và Isolation Forest.

---

## 9. Dashboard

**Lựa chọn:** Streamlit (nhanh, thuần Python) **hoặc** React + Vite + Recharts (đẹp, realtime qua WebSocket). Có thể dùng thêm Grafana để giám sát.

- [ ] **Trang Tổng quan:** thẻ giá trị hiện tại (T, H, P, Lux, Rain, Gas), cấp cảnh báo dạng đèn màu, trạng thái online/offline, RSSI.
- [ ] **Biểu đồ realtime** của từng đại lượng (cửa sổ 1h / 24h / 7 ngày).
- [ ] **Dự báo:** biểu đồ thực tế so với dự báo, kèm khoảng tin cậy và xác suất mưa 1h/3h/6h. So sánh với nowcast tại edge.
- [ ] **Cảnh báo:** timeline, lọc theo cấp, nút xác nhận (ack), nguồn cảnh báo (edge/cloud).
- [ ] **Thiết bị:** chỉnh ngưỡng, chu kỳ gửi, nút `test_alarm`, `mute`, `calibrate`.
- [ ] **Mô hình:** phiên bản model, metric, lần huấn luyện gần nhất.
- [ ] Xuất CSV.
- [ ] Giao diện responsive, xem được trên điện thoại.

---

## 10. Thông báo
- [ ] Tạo Telegram bot (BotFather), lấy `chat_id`, lưu vào `.env`.
- [ ] Mẫu tin nhắn theo cấp (emoji, giá trị, thời gian, vị trí, link dashboard).
- [ ] Nút inline "Đã xử lý" để gọi API ack.
- [ ] Gửi tin tóm tắt thời tiết hằng ngày lúc 6h sáng (dự báo trong ngày).
- [ ] (Tuỳ chọn) Email qua SMTP cho cấp 3.

---

## 11. Triển khai
- [ ] `docker-compose.yml`: `mosquitto`, `postgres/timescaledb` (hoặc `influxdb`), `backend` (API + ingest + scheduler), `dashboard`, `grafana` (tuỳ chọn).
- [ ] `.env.example` liệt kê đầy đủ biến môi trường.
- [ ] Chạy local trên laptop, hoặc deploy lên VPS / Oracle Cloud Free Tier / Raspberry Pi.
- [ ] (Tuỳ chọn) HiveMQ Cloud / EMQX Cloud làm broker công khai để demo từ xa.
- [ ] Healthcheck cho các container và log tập trung.
- [ ] README: hướng dẫn cài đặt từ đầu trong ≤ 10 bước.

---

## 12. Kiểm thử

### 12.1 Phần mềm
- [ ] Unit test cho `mlcore` (pytest): dữ liệu đồ chơi có đáp án, gradient check, tính khớp giữa C và Python, `to_dict()`/`from_dict()` khôi phục model cho ra cùng kết quả dự đoán.
- [ ] Unit test Python (pytest): validate schema, feature engineering, logic cảnh báo (hysteresis, debounce, leo thang), API.
- [ ] Integration test: simulator → broker → ingest → DB → API.
- [ ] Load test: giả lập 20–50 thiết bị, mỗi thiết bị gửi 1 msg/giây, đo độ trễ và CPU.
- [ ] Unit test firmware (PlatformIO `test/`, Unity) cho filter và rule engine.

### 12.2 Phần cứng / hệ thống
- [ ] Đo độ trễ cảnh báo tại edge (từ lúc xả gas đến khi còi kêu) và độ trễ end-to-end (đến Telegram).
- [ ] Test mất Wi-Fi: cảnh báo tại edge vẫn hoạt động, có đệm offline, gửi bù đúng sau khi kết nối lại.
- [ ] Test mất điện broker: kiểm tra LWT và trạng thái offline trên dashboard.
- [ ] Test báo động giả: hơi nước, cồn, nước hoa. Ghi tỉ lệ false positive.
- [ ] Chạy liên tục ≥ 72 giờ, theo dõi heap (phát hiện rò rỉ bộ nhớ), số lần reconnect, số lần watchdog reset.
- [ ] So sánh dữ liệu trạm với Open-Meteo hoặc trạm khí tượng gần nhất để đánh giá độ lệch cảm biến.

### 12.3 Bảng kết quả cần có trong báo cáo
- [ ] Bảng metric dự báo (các mô hình × các horizon).
- [ ] Bảng metric cảnh báo (rule / model / hybrid).
- [ ] Bảng độ trễ (edge, end-to-end, P50/P95).
- [ ] Tài nguyên edge: flash, RAM, thời gian suy luận, công suất tiêu thụ.

---

## 13. Báo cáo và bảo vệ
- [ ] **Chương 1 — Giới thiệu:** bối cảnh (thời tiết Đà Nẵng, tai nạn cháy nổ gas trong gia đình), mục tiêu, phạm vi, đóng góp.
- [ ] **Chương 2 — Cơ sở lý thuyết:** IoT/AIoT, MQTT (QoS, LWT, retain), Edge vs Cloud computing, nguyên lý từng cảm biến (đặc biệt cảm biến MOS của MQ-2), các mô hình dự báo chuỗi thời gian, TinyML, các công trình liên quan. **Trình bày toán học của các thuật toán đã tự cài đặt:** CART (Gini/MSE), Random Forest, Gradient Boosting (gradient và hessian, bước Newton), Logistic Regression, Holt-Winters, Isolation Forest, CUSUM, (nâng cao) GRU/LSTM và BPTT.
- [ ] **Chương 3 — Thiết kế hệ thống:** kiến trúc, phần cứng, sơ đồ chân, MQTT, CSDL (ERD), sequence diagram cho luồng cảnh báo và luồng dự báo.
- [ ] **Chương 4 — Hiện thực:** firmware, backend, thư viện `mlcore` tự xây dựng (kiến trúc, giao diện API, cách vector hoá, cách kiểm chứng tính đúng), quy trình xuất model sang C, dashboard (kèm ảnh chụp màn hình).
- [ ] **Chương 5 — Thực nghiệm và đánh giá:** kịch bản, kết quả, so sánh, thảo luận.
- [ ] **Chương 6 — Kết luận và hướng phát triển:** LoRa/NB-IoT, pin năng lượng mặt trời, nhiều trạm (mesh), cảm biến PM2.5, federated learning.
- [ ] Tài liệu tham khảo (datasheet, paper, chuẩn LEL).
- [ ] Slide 15–20 trang và video demo 3–5 phút.
- [ ] **Kịch bản demo trực tiếp:** dashboard đang chạy → đưa bật lửa gas lại gần → LED/còi đổi cấp → Telegram nhận tin → bấm ack → rút Wi-Fi để chứng minh edge vẫn cảnh báo.

---

## 14. Kế hoạch thời gian (gợi ý 10 tuần)

| Tuần | Công việc chính | Sản phẩm bàn giao |
|---|---|---|
| 1 | Mua MQ-2 và linh kiện phụ, test từng cảm biến, I2C scan, dựng cấu trúc repo, Docker Mosquitto | Ảnh test cảm biến, repo |
| 2 | Firmware: đọc + lọc + MQTT telemetry + NTP + LWT. Burn-in MQ-2 | Thiết bị gửi telemetry ổn định |
| 3 | Backend: ingest + DB + API cơ bản. **Bắt đầu thu dữ liệu 24/7.** Tải dữ liệu Open-Meteo. `mlcore` phần nền tảng: preprocessing, model_selection, metrics, linear + unit test | Dữ liệu vào DB, `/docs` chạy, test `mlcore` pass |
| 4 | Hiệu chuẩn MQ-2 và YL-83. Rule engine đa cấp + còi/LED/nút. Đệm offline. `mlcore`: CART, Random Forest, `export_c.py` | Cảnh báo edge hoạt động, cây xuất được sang C |
| 5 | Thu dữ liệu khí có gán nhãn. Huấn luyện model edge bằng `mlcore`, xuất C, nhúng vào firmware, kiểm tra khớp C/Python | `gas_model.h`, bảng so sánh rule/model/hybrid |
| 6 | EDA và feature. Tự build Holt-Winters và Gradient Boosting (MSE, log-loss). Huấn luyện baseline + GBDT trên Open-Meteo | Notebook, bảng metric |
| 7 | Isolation Forest + CUSUM. (Nâng cao) GRU/LSTM bằng NumPy + gradient check. Fine-tune bằng dữ liệu trạm, chọn model. Forecast service + publish `forecast` | Dự báo chạy tự động |
| 8 | Dashboard + Telegram + alert service (leo thang, ack). Nowcast edge + OLED | Hệ thống end-to-end |
| 9 | Kiểm thử (unit, integration, load, 72h, mất mạng, báo động giả). Sửa lỗi | Bảng kết quả kiểm thử |
| 10 | Báo cáo, slide, video demo, đóng hộp hoàn thiện | Bản nộp cuối |

---

## 15. Definition of Done
- [ ] Trạm đọc đủ 5 loại cảm biến, gửi MQTT ổn định ≥ 72 giờ.
- [ ] Cảnh báo khí/khói 4 cấp chạy **tại edge kể cả khi mất mạng**, có hysteresis/debounce, nút mute.
- [ ] Cloud lưu dữ liệu, xác nhận/leo thang cảnh báo, gửi Telegram.
- [ ] Dự báo 1h/3h/6h chạy tự động, có bảng so sánh với baseline và vượt baseline persistence.
- [ ] Dashboard hiển thị realtime, lịch sử, dự báo, cảnh báo, cho phép chỉnh cấu hình thiết bị.
- [ ] Có số liệu chứng minh lợi ích của hybrid edge–cloud (độ trễ, khả năng chạy offline, độ chính xác).
- [ ] Toàn bộ model chạy bằng `mlcore` tự viết. `requirements.txt` của `ml/` và `backend/` không chứa thư viện ML nào. Unit test và gradient check của `mlcore` đều pass.
- [ ] `docker compose up` dựng lại được toàn bộ backend. README đầy đủ.
- [ ] Báo cáo, slide và video demo hoàn chỉnh.

---

## 16. Rủi ro và phương án dự phòng
| Rủi ro | Phương án |
|---|---|
| Dữ liệu tự thu quá ít để huấn luyện dự báo | Pretrain trên Open-Meteo, fine-tune hoặc bias-correct bằng dữ liệu trạm |
| MQ-2 trôi giá trị, nhạy với nhiệt độ/độ ẩm | Burn-in, bù nhiệt ẩm (đưa T/H vào feature), hiệu chuẩn lại R0 định kỳ, phát hiện drift ở cloud |
| YL-83 bị ăn mòn khi để ngoài trời lâu | Chỉ cấp nguồn khi đọc, phủ lớp bảo vệ, có module dự phòng |
| DHT22 đọc lỗi hoặc NaN | Retry, dùng nhiệt độ BMP280 làm dự phòng, gắn cờ `sensor_ok` |
| Wi-Fi không ổn định | Đệm offline, tự kết nối lại, cảnh báo edge độc lập với mạng |
| Không có phần cứng khi phát triển backend | `tools/simulator.py` |
| Báo động giả gây phiền | Hysteresis, debounce, model hybrid, cooldown thông báo |
| Code ML tự viết có bug khó phát hiện | Test bằng dữ liệu đồ chơi, gradient check, so khớp kết quả C/Python, (tuỳ chọn) đối chiếu với scikit-learn chỉ trong báo cáo |
| Code tự viết huấn luyện chậm | Vector hoá bằng NumPy, histogram binning, resample về 1 giờ, giới hạn số cây và độ sâu, early stopping |
| Không kịp làm GRU/LSTM | Đây là phần nâng cao, có thể bỏ. Gradient Boosting vẫn là mô hình chính |
| An toàn khi thí nghiệm gas | Lượng nhỏ, nơi thoáng, không có nguồn lửa, có người giám sát |
