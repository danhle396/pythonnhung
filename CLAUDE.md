# Hướng dẫn cho Claude Code (và người tiếp quản)

Đề tài: Trạm quan trắc môi trường AIoT (ESP32 + MQTT), dự báo thời tiết ngắn hạn và cảnh báo khí/khói đa cấp, AI lai Edge–Cloud — VKU Đà Nẵng.
Môn học: **Python cho hệ thống nhúng**. Kế hoạch đầy đủ ở `task.md`. **Tiến độ ở `PROGRESS.md`.**

## Khi người dùng nói "chạy tiếp task.md"
1. Đọc `PROGRESS.md` → làm các mục trong phần **CÒN LẠI** theo thứ tự, không làm lại phần đã xong.
2. Sau mỗi hạng mục: chạy test liên quan, đánh dấu [x] trong `PROGRESS.md`.
3. Trả lời bằng **tiếng Việt**.

## Ràng buộc bắt buộc
- **CHỈ DÙNG PYTHON** cho mọi mã nguồn (task.md §0). Firmware ESP32 là **MicroPython** (`firmware/src/*.py`).
  Không thêm C/C++/Arduino/PlatformIO, JavaScript/Node.js, shell hay PowerShell vào repo. Chỉ file cấu hình
  (docker-compose.yml, Dockerfile, mosquitto.conf, acl, .env, provisioning Grafana) là ngoại lệ.
- Code chạy trên ESP32 phải tương thích MicroPython: không `dataclasses`, `typing`, `numpy`, f-string lồng phức tạp;
  thời gian dùng `compat.ticks_ms/ticks_diff`; kiểm tra bằng `python firmware/deploy.py --check` (mpy-cross).
- **Không dùng thư viện ML** (sklearn, xgboost, lightgbm, torch, tensorflow, statsmodels, prophet, shap, emlearn...).
  Mọi model nằm trong `ml/mlcore/` (chỉ NumPy). Backend nạp model qua `mlcore.serialize.load_model`.
- Toạ độ trạm: 15.975°N, 108.253°E, cao ≈ 8 m, múi giờ Asia/Ho_Chi_Minh.
- Logic edge ở `ml/src/gas_edge.py` (NumPy, dùng khi huấn luyện) và `firmware/src/edge_ai.py` + `alert.py` (MicroPython)
  phải **giống hệt nhau** — `ml/tests/test_edge_parity.py` kiểm tra. Đổi feature ⇒ sửa cả hai và chạy lại
  `python -m aiot_ml.train_gas_edge` (sinh lại `firmware/src/gas_model.py` + `firmware/tests/gas_model_testvec.json`).

## Cài môi trường (máy mới, Windows/Git Bash)
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt -r ml/requirements.txt -r firmware/requirements.txt streamlit python-pptx
.venv/Scripts/python -m pip install -e ml          # package mlcore + aiot_ml
export PYTHONUTF8=1                                 # bắt buộc trên Windows (log tiếng Việt)
```
(Linux/macOS: thay `.venv/Scripts/` bằng `.venv/bin/`.)

## Lệnh kiểm thử
```bash
cd ml && ../.venv/Scripts/python -m pytest -q                 # 44 test mlcore + pipeline + khớp edge firmware
cd backend && ../.venv/Scripts/python -m pytest -q tests      # 20 test backend (gồm integration với Mosquitto nếu có)
.venv/Scripts/python -m pytest -q firmware/tests               # 35 test firmware MicroPython chạy trên PC (+ mpy-cross, MQTT thật nếu có)
.venv/Scripts/python -m pytest -q dashboard/tests              # 8 smoke test dashboard (phản hồi API chụp từ trạm thật)
.venv/Scripts/python firmware/deploy.py --check                # biên dịch toàn bộ firmware bằng mpy-cross (cú pháp MicroPython)
```

## Nạp firmware ESP32 (MicroPython)
```bash
# lần đầu: nạp MicroPython ESP32_GENERIC (https://micropython.org/download/ESP32_GENERIC/)
.venv/Scripts/python -m esptool --chip esp32 --port COM5 erase_flash
.venv/Scripts/python -m esptool --chip esp32 --port COM5 --baud 460800 write_flash 0x1000 ESP32_GENERIC-<ver>.bin
cp -n firmware/src/credentials_example.py firmware/src/credentials.py   # điền Wi-Fi/MQTT (gitignore)
.venv/Scripts/python firmware/deploy.py --port COM5            # .mpy + mpremote + reset ("--source" để chép .py cho Thonny)
.venv/Scripts/python -m mpremote connect COM5 repl             # xem log
.venv/Scripts/python -m mpremote connect COM5 run firmware/bench_device.py   # đo thời gian edge trên ESP32
```

## Docker
```bash
docker compose up -d --build            # trùng cổng 1883 với Mosquitto Windows? đặt MQTT_HOST_PORT=11883 trong .env
docker compose --profile monitoring up -d grafana
```

## Báo cáo / slide (docs/report/)
- Nội dung: `bao_cao.md` (nguồn) → `python tools/md_to_docx.py docs/report/bao_cao.md` (cần MS Word, pip install markdown).
- Slide: `python tools/slides/build_slides.py` (python-pptx) — số liệu chép tay trong script, cập nhật khi huấn luyện lại.
- Hình: `tools/make_report_figures.py`; sơ đồ Mermaid `python tools/render_mermaid.py`; draw.io `python tools/render_drawio.py <file>`
  (dùng Edge/Chrome headless qua CDP, cần Internet để tải thư viện vẽ).

## Chạy hệ thống local (không Docker)
```bash
# 1. broker: mosquitto với broker/mosquitto/acl + passwd (python broker/mosquitto/make_passwd.py); user backend/backend-pass, station01/change-me
# 2. backend
cd backend && MQTT_PORT=1883 ../.venv/Scripts/python -m uvicorn app.main:app --port 8000
# 3. cấp nguồn trạm ESP32 thật (không có bộ giả lập — chỉ dùng số liệu đo thật)
```

## Huấn luyện lại
```bash
cd ml
../.venv/Scripts/python -m aiot_ml.fetch_open_meteo --start 2021-01-01 --end 2025-12-31
../.venv/Scripts/python -m aiot_ml.train_forecast        # ~5 phút
../.venv/Scripts/python -m aiot_ml.train_gas_edge --data data/raw/gas_labeled.csv   # cần dữ liệu MQ-2 đo thật (label_logger.py)
../.venv/Scripts/python -m aiot_ml.train_anomaly --data <telemetry.csv>              # cần vài tuần telemetry trạm
```

## Lưu ý kỹ thuật
- Firmware 2 luồng: luồng chính (cảm biến → edge → còi/LED → TFT) không phụ thuộc mạng; luồng mạng `_thread`
  (Wi-Fi, NTP, MQTT, đệm offline, OTA). Watchdog 30 s chỉ được cho ăn khi luồng mạng còn sống.
- `firmware/src/station.py` không import phần cứng → test toàn bộ luồng trên PC (`firmware/tests/test_station.py`,
  kiểm tra bản tin bằng schema Pydantic của backend).
- MQTT client tự viết (`firmware/src/mqtt.py`) chỉ publish QoS 0; độ tin cậy dựa vào `seq` + đệm offline + chống trùng ở backend.
- MicroPython trên ESP32 dùng số thực 32 bit → `gas_model.py` lưu ngưỡng float32; `predict_float32` mô phỏng để so khớp.
- Telemetry DB khoá chính (device_id, ts, seq) — phù hợp hypertable TimescaleDB.
- `ml/models/registry.json` phải lưu đường dẫn kiểu POSIX (`models/forecast/...`) — backend chạy trong Linux container.
- **Chỉ dùng số liệu đo thật** (Open-Meteo + cảm biến trạm). Không sinh/giả lập dữ liệu để huấn luyện hay đưa vào báo cáo.
  Chưa có dữ liệu khí đo thật ⇒ `firmware/src/gas_model.py` để `AVAILABLE = False`, edge chạy rule; không có
  `ml/models/gas_edge.json`, `gas_anomaly.json` (backend tự bỏ qua bước Isolation Forest).
