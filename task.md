# TASK — Trạm AIoT giám sát môi trường

> **Đề tài:** Trạm AIoT giám sát môi trường, dự báo thời tiết ngắn hạn và cảnh báo sớm khí dễ cháy, khói theo mức nguy hiểm với AI lai Edge–Cloud trên ESP32 và MQTT.
>
> **Tên tiếng Anh:** An AIoT Station for Environment Monitoring, Short-Term Weather Forecasts, and Early Warnings of Flammable Gas and Smoke by Danger Level, Using Edge–Cloud AI on ESP32 and MQTT.
>
> **Sinh viên thực hiện:** Lê Thành Danh (23CE010), Nguyễn Bá Thiện (23CE076).

**Cập nhật theo code lần cuối: 2026-11-14.** Ký hiệu: `[x]` đã làm và đã kiểm chứng (test/chạy thật) · `[ ]` chưa làm ·
⚙ cần phần cứng/người làm · ~~gạch ngang~~ đã bỏ khỏi đề tài (có lý do). Nhật ký chi tiết từng đợt: `PROGRESS.md`.

---

## 0. Nguyên tắc bắt buộc

> **NGUYÊN TẮC 1 — CHỈ DÙNG PYTHON.** Đề tài thuộc môn *Python cho hệ thống nhúng*: **mọi mã nguồn của dự án
> phải viết bằng Python**.
> - Firmware ESP32 viết bằng **MicroPython** (`firmware/src/*.py`), nạp bằng `mpremote` (hoặc Thonny). **Không** dùng
>   C/C++, Arduino, PlatformIO, ESP-IDF.
> - Backend, ML, dashboard, công cụ (vẽ sơ đồ, tạo mật khẩu/chứng chỉ broker, kiểm thử tải) đều là Python.
>   **Không** viết script JavaScript/Node.js, shell, PowerShell trong repo.
> - Mô hình edge xuất sang **module Python** (`firmware/src/gas_model.py`), không sinh header C.
> - Kiểm thử firmware bằng **pytest** trên PC (logic thuần Python chạy được cả CPython lẫn MicroPython).
> - Ngoại lệ duy nhất là file cấu hình không phải mã chương trình: `docker-compose.yml`, `Dockerfile`, `mosquitto.conf`,
>   `acl`, `.env`, JSON/YAML provisioning của Grafana.

> **NGUYÊN TẮC 2 — CHỈ DÙNG SỐ LIỆU ĐO THẬT.** Không dùng dữ liệu mô phỏng/giả lập cho huấn luyện, kết quả, hình,
> demo. Dữ liệu thời tiết lịch sử lấy từ Open-Meteo (số liệu tái phân tích thật). Mô hình ML khí và bộ phát hiện bất
> thường chỉ huấn luyện khi có dữ liệu MQ-2/telemetry đo thật; trong lúc chờ, edge chạy luật ngưỡng (`gas_model.AVAILABLE = False`).

> **NGUYÊN TẮC 3 — LUÔN ĐỒNG BỘ MỌI THỨ VỚI NHAU.** Code, tài liệu, sơ đồ, báo cáo, slide và kế hoạch phải luôn nói
> cùng một điều. **Mỗi thay đổi code phải cập nhật luôn mọi chỗ liên quan trong cùng một lần sửa**, không để "sửa sau".
> Trước khi coi một việc là xong, rà theo bảng dưới và chạy lại toàn bộ test.
>
> | Khi thay đổi…                                       | Phải cập nhật đồng bộ                                                                                                                                                                                                                                 |
> | --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
> | Bất kỳ code nào                                     | `task.md` (đánh dấu `[x]`, sửa mô tả cho khớp code), `PROGRESS.md` (nhật ký + mục CÒN LẠI), `README.md`                                                                                                                                               |
> | Chân GPIO, linh kiện (`firmware/src/config.py`)     | `task.md` §2.1–2.2, `docs/hardware/README.md`, `docs/hardware/gen_wiring_drawio.py` → `wiring.drawio` → `wiring-*.png` (`tools/render_drawio.py`), `firmware/README.md`, báo cáo §3.2, slide                                                           |
> | Topic / payload MQTT                                | firmware (`station.py`, `payloads.py`, `net.py`), `broker/mosquitto/acl`, `backend/app/mqtt/ingest.py` + `schemas/payloads.py`, `docs/architecture/mqtt.md`, `task.md` §5, `sequences.md`                                                            |
> | Bảng / cột CSDL (`backend/app/db/models.py`)        | migration Alembic mới trong `backend/app/db/migrations/versions/`, ERD trong `docs/architecture/diagrams.md`, `task.md` §7.1, báo cáo chương 3                                                                                                       |
> | API REST/WS (`backend/app/api/`)                    | `dashboard/app.py` + `dashboard/tests/` (fixture), `task.md` §7.5, `README.md`, báo cáo chương 4                                                                                                                                                      |
> | Target / feature / model ML                         | `ml/configs/*.json`, `ml/src/features.py`, `ml/models/registry.json`, `docs/report/results_*.md`, hình `tools/make_report_figures.py`, forecast service, dashboard, báo cáo chương 5, slide                                                           |
> | Kiến trúc / luồng xử lý                             | `docs/architecture/system_block_diagram.drawio`, `ipo.md`, `diagrams.md`, `sequences.md` (→ PNG bằng `tools/render_mermaid.py`), `task.md` §3, báo cáo chương 3                                                                                       |
> | Số lượng test                                       | `README.md` (mục Kiểm thử), `PROGRESS.md`, `docs/report/bao_cao.md` (chương 4, 6, phụ lục), `docs/report/kich_ban_demo.md`, `task.md` §12                                                                                                            |
> | Báo cáo nguồn                                       | sinh lại `bao_cao.docx` (`tools/md_to_docx.py`, cần MS Word)                                                                                                                                                                                         |
> | Xoá / đổi tên tính năng, file, module               | `grep` toàn repo tìm tham chiếu cũ (code, test, tài liệu, sơ đồ, slide) và xoá hết; bảng CSDL bị bỏ phải có migration `drop`                                                                                                                         |
>
> Lệnh kiểm tra trước khi kết thúc (Windows: đặt `PYTHONUTF8=1`):
> ```bash
> cd ml && pytest -q && cd ..            # 21 test
> cd backend && pytest -q tests && cd .. # 21 test
> pytest -q firmware/tests               # 33 test
> pytest -q dashboard/tests              # 8 test   → tổng 83
> ```

### 0.1 Ghi chú phần cứng trước khi bắt đầu
- [x] **Bổ sung cảm biến khí/khói.** Danh sách phần cứng ban đầu (YL-83, BH1750, DHT22, BMP280) không có cảm biến khí → thêm **MQ-2** (LPG, propane, H₂, CH₄, khói). Tuỳ chọn thêm MQ-5/MQ-135 (hướng phát triển). ⚙ Trạm hiện báo `sensor_ok.gas = false` (ADC kẹt 142 mV) — kiểm tra module, nguồn 5 V và cầu phân áp.
- [x] Chỉ dùng **một** BH1750 (`0x23`); module thứ hai (nếu có) đổi ADDR → `0x5C` hoặc để dự phòng.
- [x] MQ-2 AO tới 5 V, ADC ESP32 chỉ chịu **3.3 V** → cầu phân áp 10 kΩ/20 kΩ (`MQ2_DIVIDER = 2/3`, nút giữa nối GPIO32).
- [x] Mọi chân analog nằm trên **ADC1** (GPIO32–39) vì ADC2 không dùng được khi Wi-Fi bật (YL-83 → GPIO34, MQ-2 → GPIO32).
- [x] **Mô hình AI/ML dùng thư viện chuẩn** (scikit-learn, LightGBM, statsmodels, PyTorch) để bảo đảm tính đúng đắn của dự báo (xem mục 8). ~~Tự xây dựng từ đầu trong `ml/mlcore`~~ — bỏ (2026-11-14), `mlcore` đã xoá.
- [x] Hệ thống chỉ là **nguyên mẫu học thuật**, không thay thế thiết bị báo cháy/báo gas đã chứng nhận — đã ghi trong README và báo cáo.

---

## 1. Mục tiêu đề tài

### 1.1 Mục tiêu chức năng
1. Thu thập liên tục: nhiệt độ, độ ẩm (DHT22), áp suất và nhiệt độ phụ (BMP280), cường độ ánh sáng (BH1750), mưa (YL-83), khí dễ cháy/khói (MQ-2).
2. Truyền dữ liệu thời gian thực qua **MQTT** lên server.
3. **Dự báo thời tiết ngắn hạn** (1h / 3h / 6h): nhiệt độ, độ ẩm, xác suất mưa. Áp suất chỉ là feature đầu vào, **không dự báo** (đã bỏ target `pres` và nowcast Zambretti ngày 2026-11-13).
4. **Cảnh báo sớm đa cấp** khí dễ cháy/khói: 4 cấp (Bình thường → Chú ý → Cảnh báo → Nguy hiểm).
5. **AI lai Edge–Cloud:**
   - **Edge (ESP32):** cảnh báo khí ngay tại chỗ (rule engine + cây quyết định khi có model), phát hiện lỗi cảm biến, vẫn hoạt động khi mất mạng.
   - **Cloud (Python):** mô hình dự báo thời tiết, xác nhận/leo thang cảnh báo (xu hướng ppm 10 phút), huấn luyện lại và đẩy cấu hình/ngưỡng xuống thiết bị.
6. Dashboard web (Streamlit) theo dõi realtime, lịch sử, dự báo và cảnh báo; thông báo qua Telegram/Email.

### 1.2 Chỉ tiêu đánh giá (KPI)
| Hạng mục                                                      | Chỉ tiêu mục tiêu             | Hiện trạng (2026-11-13)                                      |
| ------------------------------------------------------------- | ----------------------------- | ------------------------------------------------------------ |
| Độ trễ cảnh báo tại edge (từ lúc vượt ngưỡng đến khi còi kêu) | < 1 giây                      | ⚙ chờ đo trên trạm (có trường `edge_latency_ms` trong alert) |
| Độ trễ cảnh báo end-to-end (từ cảm biến đến Telegram)         | < 5 giây                      | ⚙ chờ đo trên trạm                                           |
| Tỉ lệ mất gói MQTT (QoS 1)                                    | < 1%                          | **0 %** (50 thiết bị × 1 msg/s, local và Docker)             |
| MAE dự báo nhiệt độ 1h                                        | < 1.0 °C                      | **0.30 °C** (GBDT, test 2025)                                |
| MAE dự báo độ ẩm 1h                                           | < 5 %RH                       | **1.87 %RH**                                                 |
| F1 phân loại mưa / không mưa (3h tới)                         | > 0.75                        | **0.833**                                                    |
| Recall cảnh báo khí cấp ≥ 2                                   | ≥ 0.95 (ưu tiên không bỏ sót) | ⚙ chờ dữ liệu khí đo thật                                    |
| Thời gian chạy liên tục không treo                            | ≥ 72 giờ                      | ⚙ chờ chạy trạm                                              |

### 1.3 Địa điểm triển khai
| Thông số | Giá trị                                                                                                                                                 | Dùng cho                                                       |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| Vị trí   | Trường ĐH CNTT & TT Việt – Hàn (VKU), 470 Trần Đại Nghĩa, P. Hoà Quý, Q. Ngũ Hành Sơn, Đà Nẵng                                                          | —                                                              |
| Toạ độ   | ≈ **15.975°N, 108.253°E** (xác nhận lại trên Google Maps tại đúng chỗ đặt trạm)                                                                         | Tải Open-Meteo, tính góc mặt trời và lux khi trời quang        |
| Độ cao   | ≈ 5–10 m so với mực nước biển (đang dùng **8 m**)                                                                                                       | Quy áp suất về mực nước biển                                   |
| Múi giờ  | `Asia/Ho_Chi_Minh` (UTC+7)                                                                                                                              | NTP, Open-Meteo, feature giờ trong ngày                        |
| Khí hậu  | Nhiệt đới gió mùa. **Mùa mưa tháng 9–12** (cao điểm tháng 10–11, có bão và áp thấp nhiệt đới), mùa khô tháng 1–8. Gần biển, độ ẩm trung bình khoảng 80% | Tập test phải bao trọn mùa mưa. Nhãn mưa mất cân bằng theo mùa |

- [x] Giá trị đã đặt trong `firmware/src/config.py` (`STATION_LAT = 15.975`, `STATION_LON = 108.253`, `STATION_ALT_M = 8.0`, `TZ_HOURS = 7`) và backend (`STATION_LAT/LON/ALT_M/TZ` trong `backend/app/core/config.py`, ghi đè được bằng `.env`).
- [ ] ⚙ Trạm thử trong nhà; sau khi làm hộp bảo vệ mạch, đặt ngoài trời **một đêm** để đối chiếu dự báo với số đo (bảng sai số trên trang Dự báo của dashboard → báo cáo 5.1). Không thu dữ liệu ngoài trời dài ngày.
- [ ] ⚙ Vị trí đặt: nơi thoáng, không bị mái che chắn mưa, tránh phản xạ nhiệt từ tường bê tông và máy lạnh. Tấm YL-83 nghiêng 30–45°.

---

## 2. Phần cứng

### 2.1 Danh sách linh kiện (BOM)
| #   | Linh kiện                         | Chức năng                                                        | Giao tiếp           | Ghi chú                                                                                       |
| --- | --------------------------------- | ---------------------------------------------------------------- | ------------------- | --------------------------------------------------------------------------------------------- |
| 1   | ESP32 DevKit V1 (ESP-WROOM-32)    | Vi điều khiển, Wi-Fi, Edge AI                                    | —                   | Có sẵn                                                                                        |
| 2   | DHT22 (AM2302)                    | Nhiệt độ, độ ẩm                                                  | 1-Wire (GPIO)       | Có sẵn. Đọc tối đa 1 lần / 2 giây                                                             |
| 3   | BMP280                            | Áp suất, nhiệt độ                                                | I2C `0x76`          | Có sẵn                                                                                        |
| 4   | BH1750                            | Cường độ ánh sáng (lux)                                          | I2C `0x23`          | Có sẵn                                                                                        |
| 5   | YL-83 (+ module LM393)            | Phát hiện / mức độ mưa                                           | Analog + Digital    | Có sẵn. Cấp nguồn từ GPIO18 chỉ khi đọc                                                       |
| 6   | **MQ-2**                          | Khí dễ cháy, khói                                                | Analog + Digital    | ⚙ Trạm đang báo lỗi `gas` — kiểm tra module/nguồn 5 V/phân áp                                 |
| 7   | Buzzer active 2 chân              | Còi cảnh báo (nối thẳng GPIO, `BUZZER_ACTIVE_LOW = False`)       | GPIO                | Có sẵn                                                                                        |
| 8   | LED xanh / đỏ (+ điện trở 220Ω)   | Đèn báo cấp cảnh báo (không có LED vàng: cấp 1 = xanh nhấp nháy) | GPIO                | `HAS_LED_YELLOW = False`                                                                      |
| 9   | Màn hình TFT 1.8" ST7735S 128×160 | Hiển thị tại chỗ (màu)                                           | SPI (CS/A0/SDA/SCK) | Có sẵn. Driver tự viết `st7735.py`                                                            |
| 10  | ~~Relay 5V hoặc quạt nhỏ~~        | Không dùng (nhóm không có) — hướng phát triển                    | GPIO                | `HAS_RELAY = False` (code vẫn giữ `PIN_RELAY = 23`)                                           |
| 11  | ~~Nút nhấn~~                      | Không dùng — tắt còi bằng lệnh `mute` trên dashboard             | —                   | Đã xoá code đọc GPIO13                                                                        |
| 12  | Điện trở 10kΩ + 20kΩ              | Phân áp cho MQ-2 AO                                              | —                   | —                                                                                             |
| 13  | Nguồn 5V/2A, breadboard, dây      | Cấp nguồn                                                        | —                   | MQ-2 tiêu thụ ≈ 150 mA. ⚙ Cấp qua USB làm board tự reset khi bật Wi-Fi → dùng 5 V/2 A vào VIN |
| 14  | Hộp nhựa có khe thông gió         | Đóng gói trạm                                                    | —                   | YL-83 đặt ngoài trời, DHT22 đặt trong vỏ che nắng                                             |

### 2.2 Sơ đồ chân (theo `firmware/src/config.py` và `docs/hardware/README.md`)
| Thiết bị                 | Chân thiết bị               | Chân ESP32                                        |
| ------------------------ | --------------------------- | ------------------------------------------------- |
| I2C bus (BMP280, BH1750) | SDA / SCL                   | GPIO21 / GPIO22                                   |
| DHT22                    | DATA                        | GPIO4 (pull-up 10kΩ)                              |
| YL-83                    | VCC / AO / DO               | GPIO18 (cấp nguồn khi đọc) / GPIO34 / GPIO35      |
| MQ-2                     | AO (qua phân áp) / DO       | GPIO32 / GPIO33                                   |
| Buzzer                   | +                           | GPIO25                                            |
| LED xanh / đỏ            | Anode                       | GPIO26 / GPIO14                                   |
| TFT ST7735S              | CS / A0 / SDA / SCK / RESET | GPIO5 / GPIO16 (RX2) / GPIO17 (TX2) / GPIO19 / EN |

### 2.3 Công việc phần cứng
- [x] Sơ đồ đấu dây draw.io (thay Fritzing/KiCad): `docs/hardware/wiring.drawio` (2 trang: cảm biến / cảnh báo), sinh bằng `docs/hardware/gen_wiring_drawio.py`, xuất `wiring-1.png`, `wiring-2.png`; bảng đấu dây `docs/hardware/README.md`.
- [x] Quét I2C tự động lúc khởi động (log `[SENS] I2C [...] BMP280:1 BH1750:1`). [ ] ⚙ Chụp ảnh màn TFT hiển thị đúng màu/hướng.
- [ ] ⚙ Test riêng từng cảm biến và ghi kết quả vào báo cáo.
- [ ] ⚙ **Burn-in MQ-2 24–48 giờ** trước khi hiệu chuẩn.
- [x] Hiệu chuẩn MQ-2 có sẵn trong firmware: lệnh `calibrate` đo `R0` trong không khí sạch (`Rs/R0 ≈ 9.83`), ppm theo `ppm = 574.25 · (Rs/R0)^−2.222`. [ ] ⚙ Chạy lệnh sau burn-in, đo lại `MQ2_RL_KOHM` trên module.
- [x] Hiệu chuẩn YL-83 theo dataset đo thật (608 mẫu khô, 54 mẫu ướt): khô ≥ 3130 mV, mưa phùn 3000–3129, mưa vừa 2900–2999, mưa to < 2900 mV; giữ mức mưa 3 lần đọc. ⚙ ADC đang kẹt trần 3134 mV kể cả khi nhỏ nước → kiểm tra dây tấm cảm biến ↔ LM393, AO → GPIO34.
- [ ] ⚙ So sánh nhiệt độ DHT22 và BMP280 (dashboard có cả hai trường), đối chiếu nhiệt kế tham chiếu nếu có.
- [ ] ⚙ Lắp ráp vào hộp, chụp ảnh thực tế cho báo cáo.

---

## 3. Kiến trúc hệ thống

Sơ đồ khối chính thức: `docs/architecture/system_block_diagram.drawio`; Input – Xử lý – Output: `docs/architecture/ipo.md`;
kiến trúc + ERD (Mermaid): `docs/architecture/diagrams.md`; sơ đồ tuần tự: `docs/architecture/sequences.md`.

```
┌──────────────────── EDGE (ESP32, MicroPython) ───────────────┐
│ Sensors → Sampling → Filter (median/EWMA) → Feature extract  │
│     │                                         │              │
│     │                     ┌───────────────────┴───────────┐  │
│     │                     │ Edge AI (edge_ai.py)           │  │
│     │                     │ • Rule engine (ngưỡng + slope, │  │
│     │                     │   hysteresis, debounce)        │  │
│     │                     │ • Cây quyết định gas_model.py  │  │
│     │                     │   (khi có dữ liệu thật)        │  │
│     │                     │ • Phát hiện lỗi cảm biến       │  │
│     │                     └───────────────┬───────────────┘  │
│     │           Local actuators ◄─────────┤ (buzzer/LED/TFT) │
│     │           Offline buffer (LittleFS)◄┤ khi mất mạng     │
└─────┼─────────────────────────────────────┼──────────────────┘
      │ MQTT (TLS tuỳ chọn), LWT, seq chống trùng│
┌─────▼─────────────────────────────────────▼──────── CLOUD ───┐
│ Mosquitto Broker (auth + ACL theo thiết bị)                   │
│   ├─► Ingestion (paho-mqtt) ─► TimescaleDB (Docker) / SQLite  │
│   ├─► Alert service: xác nhận / leo thang ─► Telegram/Email   │
│   ├─► Forecast service: LightGBM, mỗi 10 phút (APScheduler)   │
│   └─► Publisher: cmd / config / forecast xuống edge, OTA      │
│ REST API (FastAPI, JWT) + WebSocket ─► Dashboard (Streamlit)  │
│                                     └► Grafana (tuỳ chọn)     │
└───────────────────────────────────────────────────────────────┘
```

### 3.1 Phân chia trách nhiệm Edge và Cloud
| Chức năng                  | Edge (ESP32)          | Cloud (Python)                 |
| -------------------------- | --------------------- | ------------------------------ |
| Lọc nhiễu, tính feature    | ✅                    | —                              |
| Cảnh báo khí/khói tức thì  | ✅ (quyết định chính) | Xác nhận, leo thang, thông báo |
| Hoạt động khi mất mạng     | ✅ (đệm offline)      | —                              |
| Dự báo 1h/3h/6h            | —                     | ✅ (ML/DL)                     |
| Huấn luyện mô hình         | —                     | ✅                             |
| Lưu trữ dài hạn, dashboard | —                     | ✅                             |
| Cập nhật ngưỡng / model    | Nhận                  | Gửi (MQTT `config`, OTA)       |

---

## 4. Cấu trúc thư mục dự án (hiện tại)

```
final/
├── task.md                     # kế hoạch + trạng thái (file này)
├── PROGRESS.md                 # nhật ký tiến độ, mục CÒN LẠI
├── README.md                   # cài đặt ≤ 10 bước, kiểm thử, kết quả chính
├── docker-compose.yml          # mosquitto, db (TimescaleDB), backend, dashboard, grafana (profile monitoring)
├── .env                        # tuỳ chọn, gitignore — ghi đè mặc định (mọi biến có mặc định)
├── .gitignore, .gitattributes, .dockerignore
├── docs/
│   ├── hardware/               # README (bảng đấu dây), gen_wiring_drawio.py → wiring.drawio, wiring-1/2.png
│   ├── architecture/           # mqtt.md, ipo.md, diagrams.md (kiến trúc + ERD), sequences.md, system_block_diagram.drawio
│   └── report/                 # bao_cao.md/.docx, bao_cao_khung.md, kich_ban_demo.md, results_*.md, VKU-SLIDE.pptx, figures/
├── firmware/                   # MicroPython cho ESP32 (chỉ Python)
│   ├── README.md               # nạp MicroPython, credentials.py, deploy
│   ├── deploy.py               # biên dịch .mpy (mpy-cross) + chép lên board bằng mpremote; tạo gói OTA
│   ├── bench_device.py         # chạy trên ESP32: đo thời gian suy luận, RAM
│   ├── config_reader.py        # đọc config.py của firmware từ PC (dùng cho tool/test)
│   ├── requirements.txt        # esptool, mpremote, mpy-cross, pytest
│   ├── src/                    # các file được chép vào thư mục gốc của ESP32
│   │   ├── boot.py, main.py    # khởi động: dựng phần cứng, luồng mạng + vòng lặp chính
│   │   ├── config.py           # pin, chu kỳ, ngưỡng mặc định, FW_VERSION = "2.0.0"
│   │   ├── credentials.py      # Wi-Fi/MQTT, tự tạo trên máy (gitignore)
│   │   ├── compat.py           # ticks/thời gian/khoá chạy được cả MicroPython lẫn CPython (test)
│   │   ├── filters.py, edge_ai.py, alert.py               # lọc, feature, rule engine, fusion, lỗi cảm biến
│   │   ├── gas_model.py        # model edge sinh từ ml/src/export_micropython.py (hiện AVAILABLE = False)
│   │   ├── station.py, readings.py, payloads.py, storage.py  # điều phối, đại lượng dẫn xuất, JSON, đệm offline + cấu hình
│   │   ├── sensors.py, drivers.py, st7735.py, display.py  # driver cảm biến (BMP280/BH1750 tự viết), màn TFT
│   │   └── mqtt.py, net.py, ota.py                        # MQTT client tự viết, Wi-Fi/NTP, OTA qua HTTP
│   └── tests/                  # pytest (33 test)
├── broker/mosquitto/
│   ├── mosquitto.conf, acl
│   ├── make_passwd.py          # sinh passwd (Docker tự sinh từ env)
│   └── gen_certs.py            # CA + chứng chỉ TLS 8883 (tuỳ chọn)
├── backend/                    # Python 3.11+, FastAPI
│   ├── Dockerfile, requirements.txt, alembic.ini
│   ├── app/
│   │   ├── main.py             # FastAPI + APScheduler (forecast, escalation, offline, reminders, tin 6h sáng)
│   │   ├── runtime.py          # dựng các service dùng chung
│   │   ├── core/ (config.py, security.py)     # Settings (env), JWT
│   │   ├── db/ (models.py, session.py, migrations/versions/0001_initial.py, 0002_drop_nowcasts.py)
│   │   ├── mqtt/ (ingest.py, publisher.py)
│   │   ├── services/ (alert_service.py, forecast_service.py, notifier.py, hub.py)  # hub = WebSocket broadcast
│   │   ├── api/ (routes.py, ws.py)
│   │   └── schemas/payloads.py
│   └── tests/                  # 21 test (gồm integration với Mosquitto thật)
├── ml/                         # package cài bằng `pip install -e ml` → `aiot_ml`
│   ├── pyproject.toml, requirements.txt   # numpy, pandas, scikit-learn, lightgbm, statsmodels, joblib (+ torch tuỳ chọn)
│   ├── configs/forecast.json
│   ├── data/ (external/vku_hourly_2021_2025.csv, raw/, processed/)   # raw/processed gitignore
│   ├── src/ (= aiot_ml)
│   │   ├── config.py, fetch_open_meteo.py, prep.py, features.py, forecast_infer.py
│   │   ├── train_forecast.py, train_gas_edge.py, train_anomaly.py, gas_edge.py, export_micropython.py
│   │   └── serialize.py (joblib + JSON), tracking.py (registry + log thí nghiệm), mdtable.py (bảng Markdown)
│   ├── models/ (forecast/*.joblib + *.json, registry.json)
│   ├── experiments/ (experiments.csv, forecast_results.json, train_forecast.log)
│   └── tests/                  # 21 test (lưu/nạp, Holt-Winters ≡ statsmodels, khớp MicroPython ↔ scikit-learn)
├── dashboard/                  # Streamlit: app.py (6 trang), Dockerfile, tests/ (8 test, fixture từ trạm thật)
├── grafana/                    # datasource + dashboard provision sẵn (vku_aiot.json)
└── tools/
    ├── label_logger.py         # ghi dữ liệu khí đo thật có nhãn
    ├── load_test.py            # kiểm thử tải N thiết bị (tự xoá thiết bị tạm)
    ├── make_report_figures.py, render_mermaid.py, render_drawio.py, browser_cdp.py
    └── md_to_docx.py           # bao_cao.md → .docx (MS Word)
```

- [x] Cấu trúc thư mục như trên. (Không có `ml/notebooks/`, `ml/src/export_edge_model.py`, `evaluate.py` như kế hoạch ban đầu: xuất model nằm trong `train_gas_edge.py`, đánh giá nằm trong các script `train_*.py`.)
- [x] Git + `.gitignore` (`.env`, `__pycache__`, `firmware/build`, `firmware/src/credentials.py`, `broker/mosquitto/passwd`, `certs/`, `ml/data/raw`, `ml/data/processed`, `ml/models/*.npz`, `backend/*.db`). Không có file mẫu `.env.example`/`credentials_example.py` — biến và cách tạo ghi trong README và `firmware/README.md`.

---

## 5. Thiết kế MQTT (chi tiết: `docs/architecture/mqtt.md`)

### 5.1 Topic
Tiền tố: `vku/aiot/{device_id}/...` (`device_id = station01`). Broker trên máy phát triển: cổng host `11883`
(`MQTT_HOST_PORT` trong `.env`, vì Mosquitto Windows chiếm 1883); trong Docker vẫn là 1883.

| Topic           | Chiều        | QoS     | Retain | Nội dung                                                       |
| --------------- | ------------ | ------- | ------ | -------------------------------------------------------------- |
| `.../telemetry` | Edge → Cloud | 0*      | ❌     | Dữ liệu cảm biến + kết quả edge AI, 10 s (1 s khi cấp ≥ 1)     |
| `.../alert`     | Edge → Cloud | 0*      | ❌     | Sự kiện khí/khói (khi đổi cấp), `sensor_fault`, `test`         |
| `.../status`    | Edge → Cloud | 1 (LWT) | ✅     | `online` + RSSI, uptime, heap; LWT `{"state":"offline"}`       |
| `.../forecast`  | Cloud → Edge | 1       | ✅     | Dự báo 1h/3h/6h + `summary` cho màn TFT                        |
| `.../cmd`       | Cloud → Edge | 1       | ❌     | `mute`, `test_alarm`, `calibrate`, `reboot`, `escalate`, `ota` |
| `.../config`    | Cloud → Edge | 1       | ✅     | Ngưỡng, chu kỳ gửi, chế độ edge, R0, `version`                 |
| `.../ack`       | Edge → Cloud | 0*      | ❌     | Xác nhận đã nhận/áp dụng cmd/config                            |

\* MQTT client tự viết trên ESP32 chỉ publish QoS 0; "ít nhất một lần" bảo đảm ở tầng ứng dụng bằng `seq` + đệm offline +
gửi bù, backend chống trùng theo `(device_id, ts, seq)`. Backend và `tools/load_test.py` dùng QoS 1 thật.
~~`.../nowcast`~~ đã bỏ (2026-11-13).

### 5.2 Payload mẫu (JSON) — nguồn chuẩn là `docs/architecture/mqtt.md`
```json
// telemetry
{"device_id":"station01","ts":1762671600,"seq":10234,
 "temp_dht":29.4,"hum":78.2,"temp_bmp":29.9,"pressure":1008.6,"pressure_msl":1009.5,
 "lux":15230,"dew_point":25.1,"heat_index":34.2,"rain_raw":3810,"rain_level":0,
 "gas_raw":812,"gas_rs_r0":7.9,"gas_ppm":210,"gas_slope":0.4,
 "edge_risk":0,"edge_score":0.03,"warming_up":false,
 "sensor_ok":{"dht":true,"bmp":true,"bh":true,"rain":true,"gas":true},
 "fw":"2.0.0","model_ver":"gas-v1"}
```
```json
// alert
{"device_id":"station01","ts":1762671620,"seq":10240,"type":"gas",
 "level":2,"prev_level":1,"level_name":"warning","cause":["gas_ppm>1000","model"],
 "gas_ppm":1350,"score":0.87,"rule_level":2,"model_level":2,
 "action":["led_red_blink","buzzer_intermittent","fan_on"],"edge_latency_ms":3}
```
Giá trị lỗi gửi `null`; `ts = 0` khi ESP32 chưa có NTP (backend thay bằng giờ nhận nếu `ts` < 2020).

### 5.3 Công việc MQTT
- [x] Mosquitto (Docker, `eclipse-mosquitto:2.0.20`), xác thực username/password, ACL theo thiết bị (thiết bị chỉ ghi topic của chính nó).
- [x] LWT: topic `.../status`, payload `{"state":"offline"}`, retain.
- [x] TLS cổng 8883: `broker/mosquitto/gen_certs.py`, firmware đặt `MQTT_CA_FILE`/`MQTT_PORT = 8883` trong `credentials.py`. [ ] ⚙ Chạy thử TLS trên board.
- [x] ~~`tools/simulator.py`~~ — đã bỏ (2026-11-11): đề tài chỉ dùng số liệu đo thật.
- [x] Tài liệu topic/payload: `docs/architecture/mqtt.md`.

---

## 6. Firmware ESP32 (Edge)

**Nền tảng:** **MicroPython** (bản ESP32_GENERIC chính thức, nạp bằng `esptool`). Chỉ dùng module có sẵn của
MicroPython (`machine`, `network`, `dht`, `framebuf`, `ntptime`, `_thread`, `json`, `socket`); driver BMP280, BH1750,
ST7735 và MQTT client **tự viết bằng Python**. Nạp code bằng `python firmware/deploy.py --port COM3` (mpremote) hoặc Thonny.

### 6.1 Nền tảng
- [x] `deploy.py`: biên dịch `.mpy` (mpy-cross) + chép `firmware/src/` lên board; xem log bằng `python -m mpremote connect COM3 repl`.
- [x] `config.py` (pin, ngưỡng, chu kỳ) tách khỏi `credentials.py` (Wi-Fi/MQTT, gitignore).
- [x] Wi-Fi tự kết nối lại; MQTT keep-alive 15 s, backoff 2 → 30 s. ~~WiFiManager/captive portal~~ không làm (tuỳ chọn).
- [x] NTP (`pool.ntp.org`, `time.google.com`, `vn.pool.ntp.org`, GMT+7), khởi động lại SNTP khi Wi-Fi vừa lên (có giờ sau ≈ 20 s).
- [x] Watchdog `machine.WDT` 30 s; luồng mạng không báo nhịp > 60 s (`NET_STALL_MS`) thì ngừng feed WDT → board tự reset.
- [x] Hai luồng: **luồng chính** đọc cảm biến 1 s (DHT22 2 s, YL-83 10 s), feature, rule + model, còi/LED, màn hình — không phụ thuộc mạng; **luồng mạng** (`_thread`, `net.py`): Wi-Fi, NTP, MQTT, đệm offline, OTA. Giao tiếp qua hàng đợi có khoá (`_thread.allocate_lock`, `OUTBOX_MAX = 20`).
- [ ] ⚙ Nạp lên board thật bản MicroPython hiện tại và kiểm tra log `[SENS]`, màn TFT, telemetry vào DB.

### 6.2 Đọc và tiền xử lý cảm biến
- [x] Driver từng cảm biến, xử lý lỗi (NaN, timeout I2C) và cờ `sensor_ok` (dht/bmp/bh/rain/gas).
- [x] Lọc median (cửa sổ 5) rồi EWMA.
- [x] ADC: `ADC.read_uv()` (hiệu chỉnh eFuse), suy giảm 11 dB, trung bình 16 mẫu.
- [x] MQ-2: `Rs = RL·(Vc − Vout)/Vout`, `Rs/R0`, ppm; warm-up 60 s (`warming_up`, chưa cảnh báo).
- [x] YL-83: ADC → `rain_level` 0–3, cấp nguồn qua GPIO18 chỉ khi đọc.
- [x] Áp suất quy về mực nước biển (`pressure_msl`, độ cao 8 m), so được với `pressure_msl` của Open-Meteo.
- [x] Đại lượng dẫn xuất: điểm sương, heat index.

### 6.3 Edge AI — Cảnh báo khí/khói đa cấp
**Feature (10, khớp `ml/src/gas_edge.EDGE_FEATURES`):** `gas_ppm`, `rs_r0`, `slope10` (d(ppm)/dt 10 s), `std30`,
`dev_base` (lệch baseline động), `temp`, `dtemp_min`, `hum`, `dhum_min`, `lux_rel`.

**Cấp cảnh báo (ngưỡng mặc định trong `config.py`, chỉnh qua `config`):**
| Cấp | Tên                | Điều kiện (LPG, ppm)                                                                | Hành động tại edge (phần cứng hiện có)                   |
| --- | ------------------ | ----------------------------------------------------------------------------------- | -------------------------------------------------------- |
| 0   | Normal             | ppm < 300 và slope thấp                                                             | LED xanh sáng                                            |
| 1   | Advisory (Chú ý)   | 300–1000 ppm **hoặc** slope ≥ `slope1` (15) **hoặc** model score > 0.5              | LED xanh nhấp nháy (không có LED vàng), gửi alert        |
| 2   | Warning (Cảnh báo) | 1000–2000 ppm **hoặc** score > 0.75 kéo dài                                         | LED đỏ nhấp nháy, còi ngắt quãng (relay/quạt: không lắp) |
| 3   | Danger (Nguy hiểm) | > 2000 ppm (≈ 10% LEL của LPG) **hoặc** cấp 2 kèm nhiệt độ tăng nhanh (> 1 °C/phút) | LED đỏ sáng liên tục, còi liên tục                       |

- [x] **Rule engine** (`alert.py`): ngưỡng ppm, rate-of-change, **hysteresis** 15 %, **debounce** lên 3 / xuống 5 mẫu (cấp 3 lên ngay).
- [x] **Model nhẹ**: Decision Tree/Random Forest của scikit-learn, huấn luyện bằng `ml/src/train_gas_edge.py`, xuất sang `firmware/src/gas_model.py` bằng `ml/src/export_micropython.py` (mảng node đóng gói `bytes`, `predict_proba()` duyệt cây, float32). [ ] ⚙ **Chưa có model** vì chưa có dữ liệu khí đo thật → `AVAILABLE = False`, edge tự chạy rule.
- [x] **Fusion:** `level = max(rule_level, model_level)`; model không được hạ cấp do rule đưa ra. Chế độ `rule`/`model`/`hybrid` chọn qua `config`.
- [x] Tắt còi 5 phút bằng lệnh `mute` từ dashboard (không có nút vật lý), vẫn giữ cấp và LED; cấp tăng thêm thì còi kêu lại.
- [x] Publish `alert` mỗi khi đổi cấp, kèm `cause`, `rule_level`, `model_level`, `edge_latency_ms`.
- [x] Phát hiện **lỗi cảm biến** MQ-2: đứng yên (stuck), mất kết nối, ADC bão hoà → alert `sensor_fault`.
- [x] Lệnh `test_alarm` gửi alert `type: test` (backend không gửi Telegram/Email cho `test`); lệnh `escalate` từ cloud nâng cấp.

### 6.4 Truyền thông và độ tin cậy
- [x] Telemetry 10 s (cấu hình được qua `telemetry_ms`), 1 s khi đang có cảnh báo.
- [x] Đệm offline: file trên flash (LittleFS), vòng đệm 2000 bản ghi, gửi bù khi kết nối lại (tối đa 200 bản/lượt); `seq` lưu `/seq.txt` để chống trùng.
- [x] Subscribe `cmd`, `config`, `forecast`; kiểm tra hợp lệ (th1 < th2 < th3, dải giá trị), lưu `/config.json`, gửi `ack` (`ok:false` khi từ chối).
- [x] `status` mỗi 60 s: RSSI, uptime, free heap, số lần reconnect, bản ghi chờ gửi, fw, model_ver, `inference_us`.
- [x] OTA qua HTTP: `cmd: ota` + `url` manifest (`ota.py`, gói tạo bằng `deploy.py`); API `POST /api/devices/{id}/cmd {"cmd":"ota","url":...}`. [ ] ⚙ Thử OTA trên board.

### 6.5 Hiển thị cục bộ (TFT 1.8" ST7735, `display.py`)
- [x] Trang 1: T / H / P / Lux / Rain.
- [x] Trang 2: Gas ppm, cấp cảnh báo.
- [x] Trang 3: Dự báo nhận từ cloud (`summary` của topic `forecast`).
- [x] Trạng thái Wi-Fi/MQTT ở dòng tiêu đề, đồng hồ + fw + số trang ở dòng cuối; cấp ≥ 2 luôn ưu tiên trang cảnh báo.

---

## 7. Backend Cloud (Python)

**Stack:** Python 3.11+, FastAPI, paho-mqtt, SQLAlchemy 2 + Alembic, PostgreSQL 16 + TimescaleDB 2.17 (Docker) hoặc SQLite (dev), Pydantic v2, APScheduler, gọi trực tiếp HTTP API của Telegram, SMTP, Docker Compose.

### 7.1 Cơ sở dữ liệu (`backend/app/db/models.py`)
- [x] `devices` (id, name, location, lat, lon, altitude, fw, last_seen, status…).
- [x] `telemetry` (hypertable theo `ts`): toàn bộ trường payload + `extra` (giá trị bị loại).
- [x] `alerts` (id, device_id, ts, type, level, prev_level, cause, source = edge/cloud, acknowledged_by, ack_ts…).
- [x] `forecasts` (device_id, created_at, horizon, target, value, lower, upper, model_ver, source).
- [x] `device_configs`, `commands`, `model_registry`, `notifications`.
- [x] Alembic: `0001_initial` (bảng + hypertable + continuous aggregate 1 phút / 10 phút / 1 giờ + retention dữ liệu thô 90 ngày trên TimescaleDB), `0002_drop_nowcasts` (bỏ bảng `nowcasts`).

### 7.2 Ingestion service (`mqtt/ingest.py`)
- [x] Subscribe `vku/aiot/+/telemetry|alert|status|ack`.
- [x] Validate Pydantic, loại giá trị ngoài dải vật lý (T −10..60 °C, P 900..1100 hPa, RH 0..100 %…) → lưu vào `extra.rejected`.
- [x] Chống trùng theo `(device_id, ts, seq)`; bỏ qua bản tin rỗng (xoá retained) thay vì tạo thiết bị ma.
- [x] Ghi DB theo lô, đẩy WebSocket (`services/hub.py`).
- [x] Cập nhật `last_seen`; > 60 s không có dữ liệu hoặc nhận LWT → offline + alert `device_offline`.

### 7.3 Alert service (`services/alert_service.py`)
- [x] Lưu alert từ edge + **xác nhận/leo thang** ở cloud (chạy mỗi 30 s): xu hướng ppm 10 phút so với 60 phút trước; cloud leo thang thì gửi `cmd: escalate` xuống edge.
- [x] Thông báo theo cấp: cấp 1 chỉ ghi log + dashboard; cấp 2 Telegram; cấp 3 Telegram + Email, nhắc lại tới khi ack (`test` không gửi, không nhắc).
- [x] Cooldown chống spam, bảng `notifications` lưu lịch sử gửi.
- [x] Ack từ dashboard (`POST /api/alerts/{id}/ack`) và nút inline "Đã xử lý" trên Telegram.

### 7.4 Forecast service (`services/forecast_service.py` + `ml/src/forecast_infer.py`)
- [x] APScheduler mỗi 10 phút (`FORECAST_EVERY_MIN`): lấy dữ liệu, tạo feature, gọi model, lưu `forecasts`, publish `.../forecast`.
- [x] Nạp model active từ `ml/models/registry.json` (joblib + JSON), suy luận bằng LightGBM; backend cài `pip install -e ml` (image có `libgomp1`).
- [x] Đầu vào dự báo: **luôn là quan trắc Open-Meteo** gần nhất tại toạ độ trạm (trạm ở mặt đất, chủ yếu trong nhà, chỉ ra ngoài trời từng đêm); số đo trạm chỉ để đối chiếu. Khoảng tin cậy; kẹp độ ẩm [0, 100].
- [x] Targets: `temp`, `hum` (1/3/6 h) + xác suất mưa 1/3/6 h — **không** dự báo áp suất.
- [x] Tin tóm tắt thời tiết 6h sáng (cron).

### 7.5 REST API và WebSocket (`api/routes.py`, `api/ws.py`, tiền tố `/api`)
- [x] `POST /api/auth/token` (JWT), `GET /api/health`
- [x] `GET /api/devices`, `GET /api/devices/{id}`, `DELETE /api/devices/{id}`
- [x] `PUT /api/devices/{id}/config` (publish `config`), `GET /api/devices/{id}/configs`
- [x] `POST /api/devices/{id}/cmd` (`mute`, `test_alarm`, `calibrate`, `reboot`, `escalate`, `ota`), `GET /api/devices/{id}/commands`
- [x] `GET /api/sensors/{id}` — tình trạng từng cảm biến (ok / chập chờn / lỗi / mất dữ liệu / trạm offline)
- [x] `GET /api/telemetry?device_id&from&to&resolution`, `GET /api/telemetry/latest`, `GET /api/export.csv`
- [x] `GET /api/alerts?level&from&to`, `POST /api/alerts/{id}/ack`
- [x] `GET /api/forecast/{device_id}`, `POST /api/forecast/{device_id}/run`
- [x] `GET /api/models`
- [x] `WS /ws/live` đẩy telemetry và alert realtime.
- [x] JWT cho các API ghi; Swagger tại `/docs`.

---

## 8. Machine Learning (thư viện chuẩn)

> **Quyết định (2026-11-14):** dùng thư viện học máy chuẩn để bảo đảm tính đúng đắn của dự báo và để số liệu so sánh mô
> hình đáng tin: **scikit-learn** 1.9.1 (Ridge, Logistic, Decision Tree, Random Forest, Isolation Forest, StandardScaler,
> độ đo, permutation importance), **LightGBM** 4.7.0 (GBDT — mô hình triển khai), **statsmodels** 0.15.0 (Holt-Winters),
> **PyTorch** 2.15 CPU (GRU, chỉ để so sánh, không cài trên backend). Thư viện `ml/mlcore` tự viết trước đây đã xoá;
> phiên bản scikit-learn/LightGBM được ghim trong `ml/pyproject.toml` để file `.joblib` nạp được ở backend.

### 8.1 Pipeline `ml/src/` (gói `aiot_ml`) — [x]
| Module                                       | Nội dung                                                                                                                 |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `prep.py`                                    | Xử lý chuỗi (NumPy): nội suy khoảng trống, lọc ngoại lai median/MAD, trễ, cửa sổ trượt, sin/cos; z-score theo giờ, CUSUM |
| `features.py`                                | 56 feature không rò rỉ tương lai, target Δ, seasonal naive                                                               |
| `train_forecast.py`                          | So sánh Persistence, Seasonal naive, Holt-Winters, Ridge, GBDT, GRU (+ Logistic/GBDT cho mưa)                            |
| `forecast_infer.py`                          | Nạp model active trong registry cho forecast service                                                                     |
| `train_gas_edge.py`, `export_micropython.py` | Decision Tree / Random Forest (scikit-learn) → `firmware/src/gas_model.py` (bytes + `predict_proba()`)                   |
| `train_anomaly.py`                           | Isolation Forest (scikit-learn), z-score theo giờ, CUSUM                                                                 |
| `serialize.py`, `tracking.py`                | joblib + JSON đầu mục (`model_ver`, hash dữ liệu, phiên bản thư viện); registry, log thí nghiệm                          |

- [x] Cố định `seed` (42) cho mọi thành phần ngẫu nhiên (`random_state`, `torch.manual_seed`).

### 8.2 Kiểm thử (`ml/tests/`, 21 test)
- [x] Lưu/nạp joblib giữ nguyên dự đoán (LightGBM, Ridge).
- [x] Công thức dự báo Holt-Winters h bước trùng `forecast()` của statsmodels; tốt hơn persistence trên chuỗi mùa.
- [x] `gas_model.py` sinh ra (mô phỏng float32) khớp `predict_proba()` của scikit-learn 100 % và biên dịch được bằng mpy-cross (`test_export_micropython.py`); logic edge firmware ≡ `ml/src/gas_edge.py` (`test_edge_parity.py`).
- [x] Feature không rò rỉ tương lai, hysteresis/debounce, chọn ngưỡng F1, bảng Markdown.

### 8.3 Dữ liệu
- [x] **Dữ liệu tự thu:** trạm gửi dữ liệu vào DB từ 2026-11-12 (trong nhà). Không dùng để huấn luyện dự báo; chỉ đối chiếu trong đêm đặt ngoài trời. ~~Thu liên tục ≥ 3–4 tuần~~ — bỏ (trạm ở mặt đất, chủ yếu trong nhà).
- [x] **Dữ liệu ngoài:** `ml/src/fetch_open_meteo.py` → `ml/data/external/vku_hourly_2021_2025.csv` (43 824 giờ, Open-Meteo Archive, 15.975/108.253, `Asia/Ho_Chi_Minh`). Chỉ dùng feature trạm cũng có.
- [x] Chiến lược: huấn luyện và dự báo từ Open-Meteo; bỏ bias correction trạm → Open-Meteo (cần ≥ 2 tuần đo ngoài trời, không có).
- [ ] ⚙ **Dữ liệu khí/khói đo thật** có kiểm soát và gán nhãn: không khí sạch (0), bật lửa gas xả không đốt ở 50/20/5 cm (1/2/3), khói nhang/giấy trong hộp kín, nhiễu (hơi nước, cồn, nước hoa). **Thí nghiệm nơi thoáng, lượng nhỏ, có người giám sát, xa nguồn lửa.**
- [x] Script ghi nhãn: `tools/label_logger.py --session N` (bấm phím đánh dấu sự kiện) → `ml/data/raw/gas_labeled.csv`.

### 8.4 Tiền xử lý và feature (`ml/src/features.py`, dùng `ml/src/prep.py`)
- [x] Resample về 1 giờ, nội suy khoảng trống ngắn, loại outlier.
- [x] Feature thời gian (giờ, ngày trong năm, sin/cos), lag t−1..t−6, rolling mean/std (1h/3h/6h), xu hướng áp suất 3h, điểm sương, chênh T − Td — tổng 56 feature; test bảo đảm không rò rỉ tương lai.
- [x] Chia theo thời gian: train 2021-01-02 → 2023-12-31, val 2024, test 2025.
- [x] StandardScaler (scikit-learn), chỉ `fit` trên train, lưu cùng model (Ridge/Logistic).

### 8.5 Mô hình dự báo thời tiết (Cloud) — `ml/src/train_forecast.py`, cấu hình `ml/configs/forecast.json`
| Mô hình (thư viện)                                                | Vai trò                                                       | Trạng thái     |
| ----------------------------------------------------------------- | ------------------------------------------------------------- | -------------- |
| Persistence / Seasonal naive                                      | Baseline bắt buộc                                             | [x]            |
| Holt-Winters (statsmodels)                                        | Baseline thống kê                                             | [x]            |
| Ridge Regression trên lag features (scikit-learn)                 | Baseline tuyến tính                                           | [x]            |
| **GBDT LightGBM (loss MSE)**                                      | **Mô hình chính** cho T/H, mỗi cặp target × horizon một model | [x] triển khai |
| **GBDT LightGBM (log-loss)**, so sánh với Logistic (scikit-learn) | Xác suất mưa trong 1h / 3h / 6h                               | [x] triển khai |
| GRU (PyTorch)                                                     | So sánh với deep learning (không lưu, không triển khai)       | [x]            |

**GBDT (LightGBM):** `learning_rate = 0.05`, `max_depth = 6/5`, `num_leaves = 63/31`, `min_child_samples = 30/40`,
subsample 0.8, colsample 0.8, `max_bin = 63`, early stopping 50 vòng trên val (`ml/configs/forecast.json`).

- [x] Huấn luyện 1h/3h/6h: **9 mô hình GBDT** đang active (`temp_*`, `hum_*`, `rain_*`) trong `ml/models/forecast/`.
- [x] Metric MAE/RMSE (hồi quy), F1/ROC-AUC/Brier (mưa) → `docs/report/results_forecast.md`, `ml/experiments/forecast_results.json`.
- [x] Bảng so sánh: GBDT tốt nhất 4/6 cặp target × horizon và 3/3 tầm mưa (MAE T 1h 0.299 °C, H 1h 1.870 %RH, F1 mưa 3h 0.833); GRU nhỉnh hơn 0.002 ở tầm 3h; mọi mô hình học vượt persistence.
- [x] Gain importance (LightGBM) + permutation importance (scikit-learn) (`docs/report/figures/importance_temp_1h.png`).
- [x] Thời gian huấn luyện/suy luận (ví dụ temp_1h: 0.4 s, 261 cây, 1.7 µs/mẫu).
- [x] `ml/src/serialize.py` (joblib) + `ml/models/registry.json` (chỉ thăng cấp khi tốt hơn; `--force-promote` khi đổi định dạng) + model card trong registry.
- [x] ~~Dự báo áp suất `pres_1/3/6h`~~ — đã bỏ (2026-11-13): trạm mặt đất không dự báo được trường khí áp.

### 8.6 Mô hình cảnh báo khí/khói (Edge) — `ml/src/train_gas_edge.py --data <csv thật>`
- [x] Pipeline: Decision Tree (Gini, `max_depth ≤ 6`) hoặc RF nhỏ (≤ 10 cây) của scikit-learn trên 10 feature cửa sổ trượt, **trọng số lớp** ưu tiên Recall cấp 2–3.
- [x] Metric Precision/Recall/F1 theo cấp, ma trận nhầm lẫn; so sánh 3 phương án rule / model / hybrid.
- [x] Xuất `firmware/src/gas_model.py` (float32) + kiểm tra khớp bằng Python (không dùng g++).
- [ ] ⚙ **Chạy với dữ liệu khí đo thật** (`--data` bắt buộc) → điền bảng rule/model/hybrid và Recall cấp ≥ 2 vào báo cáo 5.2.
- [ ] ⚙ Đo kích thước model (kB), RAM và µs suy luận trên ESP32 bằng `firmware/bench_device.py`.

### 8.7 Phát hiện bất thường ở cloud — `ml/src/train_anomaly.py` (đã cài, **không triển khai**)
- [x] Isolation Forest của scikit-learn (gas ppm + T/H) để phát hiện rò rỉ chậm; z-score theo giờ trong ngày để so sánh.
- [x] CUSUM trên baseline `R0` phát hiện drift MQ-2 → đề xuất hiệu chuẩn lại.
- [x] ~~Huấn luyện trên ≥ 3 tuần telemetry trạm~~ — bỏ: không có dữ liệu dài ngày. Pipeline giữ lại; alert service chỉ dùng Isolation Forest nếu có file `gas_anomaly.json/.joblib` (hiện không có) → leo thang chỉ theo xu hướng ppm.

### 8.8 Vòng đời mô hình (MLOps tối giản)
- [x] Script `train_*.py` chạy bằng CLI (`python -m aiot_ml.train_forecast`…), cấu hình JSON.
- [x] Log thí nghiệm `ml/experiments/experiments.csv` (tham số, metric, thời gian, `seed`).
- [x] Chỉ thăng cấp model mới khi tốt hơn trên tập test (`tracking.py`). ~~Lịch huấn luyện lại hằng tuần~~ — bỏ (không thu dữ liệu dài ngày).
- [x] Đẩy ngưỡng qua `config`, model edge qua OTA, ghi `model_ver`.


---

## 9. Dashboard (Streamlit, `dashboard/app.py`)

- [x] **Tổng quan:** thẻ giá trị hiện tại (T, H, P, Lux, Rain, Gas), banner cấp cảnh báo (riêng trạng thái offline / MQ-2 lỗi / thử còi / làm nóng), online/offline, RSSI, khung **Tình trạng cảm biến**.
- [x] **Biểu đồ** từng đại lượng (1h / 24h / 7 ngày), tải CSV.
- [x] **Dự báo:** thực tế vs dự báo, khoảng tin cậy, xác suất mưa 1h/3h/6h (T, H, mưa).
- [x] **Cảnh báo:** timeline, lọc theo cấp, nút ack, nguồn edge/cloud.
- [x] **Thiết bị:** form ngưỡng/chu kỳ/chế độ, nút `test_alarm`, `mute`, `calibrate`, `reboot`; lịch sử config/lệnh.
- [x] **Mô hình:** registry (phiên bản, metric, ngày train) + kết quả.
- [x] URL `?page=` / `?device=`, giờ địa phương, trục 24h; dùng được trên điện thoại (layout Streamlit).
- [x] Grafana (profile `monitoring`): datasource TimescaleDB + dashboard `grafana/dashboards/vku_aiot.json`.
- [ ] ⚙ Chụp lại ảnh 6 trang dashboard + Grafana từ dữ liệu trạm thật cho báo cáo.

---

## 10. Thông báo (`backend/app/services/notifier.py`)
- [x] Telegram bot: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` trong `.env`. [ ] ⚙ Tạo bot thật (BotFather) và điền `chat_id`.
- [x] Mẫu tin theo cấp (emoji, giá trị, thời gian, vị trí, link dashboard).
- [x] Nút inline "Đã xử lý" gọi ack.
- [x] Tin tóm tắt thời tiết 6h sáng.
- [x] Email SMTP cho cấp 3 (`SMTP_*`, `ALERT_EMAIL_TO`).

---

## 11. Triển khai
- [x] `docker-compose.yml`: `mosquitto`, `db` (TimescaleDB 2.17 / PG16), `backend` (API + ingest + scheduler, chạy `alembic upgrade head`), `dashboard`, `grafana` (profile `monitoring`); healthcheck; cổng host đổi được (`MQTT_HOST_PORT`, `API_HOST_PORT`, `DASHBOARD_HOST_PORT`, `DB_HOST_PORT`, `GRAFANA_HOST_PORT`).
- [x] README liệt kê biến môi trường (`.env` tuỳ chọn, mặc định trong `backend/app/core/config.py`, `docker-compose.yml`).
- [x] Chạy local (Docker Desktop, Windows 11/WSL2): 4 container healthy. [ ] ⚙ Chạy lại `docker compose up -d --build` sau khi đổi lệnh sinh passwd của container mosquitto sang Python.
- [ ] (Tuỳ chọn) VPS / Oracle Cloud / Raspberry Pi; HiveMQ/EMQX Cloud để demo từ xa.
- [x] README: cài đặt từ đầu ≤ 10 bước (Docker hoặc chạy trực tiếp với SQLite).

---

## 12. Kiểm thử

### 12.1 Phần mềm — tổng **83 test pass** (2026-11-14)
- [x] `ml/tests/` — **21 test**: lưu/nạp joblib, Holt-Winters ≡ statsmodels, khớp MicroPython ↔ scikit-learn, feature không rò rỉ, hysteresis/debounce, edge ≡ firmware, bảng Markdown.
- [x] `backend/tests/` — **21 test**: schema, ingest, chống trùng, cảnh báo (cấp, cooldown, leo thang, `test`), forecast, API, integration Mosquitto thật → ingest → DB → API (gửi bù, cmd, LWT).
- [x] `firmware/tests/` — **33 test**: filter, rule engine, alert manager, driver BMP280, đệm offline, toàn luồng trạm với schema backend, MQTT client với broker tối giản + Mosquitto thật, mpy-cross biên dịch mọi module, không còn file C/C++.
- [x] `dashboard/tests/` — **8 test**: 6 trang + ack + gửi config trên API giả (fixture chụp từ trạm thật bằng `capture_fixture.py`).
- [x] Load test (`tools/load_test.py`): 20 và 50 thiết bị × 1 msg/s, QoS 1 → mất gói 0 %, P95 broker ≈ 2 ms (local) / 3.4 ms (Docker + TimescaleDB), CPU backend ≈ 10 % (Docker). Kết quả: `docs/report/results_load_*.md`.

### 12.2 Phần cứng / hệ thống (⚙ cần trạm thật)
- [ ] Độ trễ cảnh báo tại edge (xả gas → còi) và end-to-end (→ Telegram), P50/P95.
- [ ] Mất Wi-Fi: edge vẫn cảnh báo, đệm offline, gửi bù đúng.
- [ ] Mất broker: LWT và trạng thái offline trên dashboard.
- [ ] Báo động giả: hơi nước, cồn (MQ-2 nhạy chéo), nước hoa → tỉ lệ false positive.
- [ ] Chạy liên tục ≥ 72 giờ: heap, số lần reconnect, watchdog reset.
- [ ] Đêm đặt ngoài trời: ghi bảng sai số dự báo so với số đo trạm (trang Dự báo của dashboard) vào báo cáo 5.1.

### 12.3 Bảng kết quả trong báo cáo
- [x] Bảng metric dự báo (các mô hình × các horizon).
- [ ] ⚙ Bảng metric cảnh báo (rule / model / hybrid) — chờ dữ liệu khí thật.
- [ ] ⚙ Bảng độ trễ (edge, end-to-end, P50/P95) — có sẵn độ trễ broker từ load test.
- [ ] ⚙ Tài nguyên edge: flash, RAM, thời gian suy luận, công suất.

---

## 13. Báo cáo và bảo vệ (`docs/report/`)
- [x] `bao_cao.md` → `bao_cao.docx` đủ 6 chương (`tools/md_to_docx.py`), khung nguồn số liệu `bao_cao_khung.md`.
- [x] **Chương 1 — Giới thiệu.** **Chương 2 — Cơ sở lý thuyết** (IoT/AIoT, MQTT, edge/cloud, cảm biến MOS, cơ sở CART, RF, GBDT/LightGBM, Logistic, Holt-Winters, Isolation Forest, CUSUM, GRU — kèm thư viện cài đặt).
- [x] **Chương 3 — Thiết kế:** kiến trúc, sơ đồ khối, phần cứng + sơ đồ đấu dây, MQTT, ERD, sơ đồ tuần tự, IPO.
- [x] **Chương 4 — Hiện thực:** firmware MicroPython, backend, pipeline ML (scikit-learn, LightGBM, statsmodels, PyTorch), xuất model sang **MicroPython** (`export_micropython.py`), dashboard.
- [x] **Chương 5 — Thực nghiệm:** dự báo, tải MQTT. [ ] ⚙ Các mục đánh dấu ⚙ (khí, độ trễ, 72 h, tài nguyên edge).
- [x] **Chương 6 — Kết luận và hướng phát triển.** Tài liệu tham khảo.
- [x] Họ tên, MSSV hai thành viên ở đầu `bao_cao.md`, README, slide. [ ] ⚙ Điền GVHD vào `bao_cao.md` rồi sinh lại `.docx`.
- [x] Slide bảo vệ `docs/report/VKU-SLIDE.pptx` (template VKU, 10 trang: bìa, giới thiệu, thành viên, sơ đồ hệ thống, 2 trang sơ đồ chân, 3 trang so sánh mô hình theo số liệu **bài báo đã công bố**, tài liệu tham khảo); số liệu trang 7–9 trích nguyên văn từ Dong 2026, Darmawan 2023, Ke 2017 (LightGBM), Yu 2021 — cũng ở báo cáo §2.5 (Bảng 2.1–2.4).
- [x] Kịch bản demo + video + câu hỏi bảo vệ: `docs/report/kich_ban_demo.md`. [ ] ⚙ Quay video demo trên trạm thật.
- **Kịch bản demo trực tiếp:** dashboard đang chạy → đưa bật lửa gas lại gần → LED/còi đổi cấp → Telegram nhận tin → bấm ack → rút Wi-Fi để chứng minh edge vẫn cảnh báo.

---

## 14. Kế hoạch thời gian (10 tuần) và trạng thái

| Tuần | Công việc chính                                                                                                      | Trạng thái (2026-11-13)                              |
| ---- | -------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| 1    | Mua MQ-2 và linh kiện phụ, test từng cảm biến, I2C scan, dựng cấu trúc repo, Docker Mosquitto                        | Repo + broker xong; ⚙ test cảm biến                  |
| 2    | Firmware: đọc + lọc + MQTT telemetry + NTP + LWT. Burn-in MQ-2                                                       | Firmware xong; trạm gửi dữ liệu thật; ⚙ burn-in      |
| 3    | Backend: ingest + DB + API. Open-Meteo. Pipeline ML nền tảng + unit test                                             | Xong                                                 |
| 4    | Hiệu chuẩn MQ-2 và YL-83. Rule engine đa cấp + còi/LED. Đệm offline. CART/RF (scikit-learn), `export_micropython.py` | Phần mềm xong; ⚙ dây YL-83/MQ-2                      |
| 5    | Thu dữ liệu khí có gán nhãn. Huấn luyện model edge, xuất MicroPython, nạp ESP32, kiểm tra khớp                       | Pipeline xong; ⚙ dữ liệu khí thật                    |
| 6    | EDA và feature. Holt-Winters, GBDT (MSE, log-loss). Baseline + GBDT trên Open-Meteo                                  | Xong                                                 |
| 7    | Isolation Forest + CUSUM. GRU (PyTorch) đối chứng. Forecast service + publish `forecast`                             | Xong (Isolation Forest/CUSUM không triển khai)       |
| 8    | Dashboard + Telegram + alert service (leo thang, ack). Màn TFT                                                       | Xong; ⚙ bot Telegram thật                            |
| 9    | Kiểm thử (unit, integration, load, 72h, mất mạng, báo động giả). Sửa lỗi                                             | Unit/integration/load xong; ⚙ thử nghiệm phần cứng   |
| 10   | Báo cáo, slide, video demo, đóng hộp hoàn thiện                                                                      | Báo cáo xong; ⚙ slide, video, đóng hộp, thông tin SV |

---

## 15. Definition of Done
- [ ] ⚙ Trạm đọc đủ 5 loại cảm biến, gửi MQTT ổn định ≥ 72 giờ (đang lỗi YL-83, MQ-2, nguồn USB).
- [x] Cảnh báo khí/khói 4 cấp chạy **tại edge kể cả khi mất mạng**, có hysteresis/debounce, tắt còi từ xa (mute) — kiểm chứng bằng pytest; ⚙ xác nhận trên phần cứng.
- [x] Cloud lưu dữ liệu, xác nhận/leo thang cảnh báo, gửi Telegram/Email.
- [x] Dự báo 1h/3h/6h chạy tự động, có bảng so sánh, vượt baseline persistence.
- [x] Dashboard hiển thị realtime, lịch sử, dự báo, cảnh báo, chỉnh cấu hình thiết bị.
- [ ] ⚙ Số liệu chứng minh lợi ích hybrid edge–cloud (độ trễ, chạy offline, độ chính xác rule/model/hybrid).
- [x] Mô hình dùng thư viện chuẩn (scikit-learn, LightGBM, statsmodels, PyTorch), phiên bản ghim; số liệu so sánh chạy lại được bằng `python -m aiot_ml.train_forecast`.
- [x] Toàn bộ mã nguồn bằng Python (firmware MicroPython), 0 file C/C++/JS/shell (có test kiểm tra).
- [x] `docker compose up` dựng lại toàn bộ backend; README đầy đủ.
- [ ] ⚙ Báo cáo (thông tin SV), slide và video demo hoàn chỉnh.
- [x] Mọi tài liệu, sơ đồ, báo cáo, slide đồng bộ với code (Nguyên tắc 3).

---

## 16. Rủi ro và phương án dự phòng
| Rủi ro                                          | Phương án                                                                                                               |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Dữ liệu tự thu quá ít để huấn luyện dự báo      | Huấn luyện, dự báo từ Open-Meteo; trạm chỉ để đối chiếu                                                                 |
| Chưa có dữ liệu khí đo thật                     | Edge chạy rule (`AVAILABLE = False`); pipeline ML sẵn sàng, chỉ cần `--data`                                            |
| MQ-2 trôi giá trị, nhạy với nhiệt độ/độ ẩm      | Burn-in, đưa T/H vào feature, hiệu chuẩn R0 bằng lệnh `calibrate` (CUSUM đã cài nhưng không triển khai)                 |
| YL-83 bị ăn mòn khi để ngoài trời lâu           | Chỉ cấp nguồn khi đọc (GPIO18), phủ lớp bảo vệ, có module dự phòng                                                      |
| DHT22 đọc lỗi hoặc NaN                          | Retry, dùng nhiệt độ BMP280 làm dự phòng, cờ `sensor_ok`                                                                |
| Wi-Fi không ổn định / board reset khi bật Wi-Fi | Đệm offline, tự kết nối lại, cảnh báo edge độc lập với mạng; cấp nguồn 5 V/2 A vào VIN thay vì USB                      |
| Trùng cổng broker 1883 với Mosquitto Windows    | Docker map ra cổng host 11883 (`MQTT_HOST_PORT`), board dùng 11883                                                      |
| Không có phần cứng khi phát triển backend       | Integration test MQTT (`backend/tests/`); dữ liệu thật chờ phần cứng                                                    |
| Báo động giả gây phiền                          | Hysteresis, debounce, model hybrid, cooldown thông báo                                                                  |
| Sai số do cài đặt mô hình                       | Dùng thư viện chuẩn (scikit-learn, LightGBM, statsmodels, PyTorch); so khớp `gas_model.py` (MicroPython) ↔ scikit-learn |
| Phiên bản thư viện lệch khi nạp model           | Ghim scikit-learn/LightGBM trong `ml/pyproject.toml`; file JSON đầu mục ghi phiên bản thư viện lúc huấn luyện           |
| Tài liệu lệch với code                          | Nguyên tắc 3 (mục 0): sửa code là sửa luôn tài liệu/sơ đồ/báo cáo/slide, grep tham chiếu cũ, chạy lại toàn bộ test      |
| An toàn khi thí nghiệm gas                      | Lượng nhỏ, nơi thoáng, không có nguồn lửa, có người giám sát                                                            |
