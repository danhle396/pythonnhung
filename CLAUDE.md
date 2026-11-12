# Hướng dẫn cho Claude Code (và người tiếp quản)

Đề tài: Trạm quan trắc môi trường AIoT (ESP32 + MQTT), dự báo thời tiết ngắn hạn và cảnh báo khí/khói đa cấp, AI lai Edge–Cloud — VKU Đà Nẵng.
Kế hoạch đầy đủ ở `task.md`. **Tiến độ ở `PROGRESS.md`.**

## Khi người dùng nói "chạy tiếp task.md"
1. Đọc `PROGRESS.md` → làm các mục trong phần **CÒN LẠI** theo thứ tự, không làm lại phần đã xong.
2. Sau mỗi hạng mục: chạy test liên quan, đánh dấu [x] trong `PROGRESS.md`.
3. Trả lời bằng **tiếng Việt**.

## Ràng buộc bắt buộc
- **Không dùng thư viện ML** (sklearn, xgboost, lightgbm, torch, tensorflow, statsmodels, prophet, shap, emlearn...).
  Mọi model nằm trong `ml/mlcore/` (chỉ NumPy). Backend nạp model qua `mlcore.serialize.load_model`.
- Toạ độ trạm: 15.975°N, 108.253°E, cao ≈ 8 m, múi giờ Asia/Ho_Chi_Minh.
- Logic edge ở `ml/src/gas_edge.py` (Python) và `firmware/src/edge_ai.cpp` + `alert.cpp` (C++) phải **giống hệt nhau**.
  Đổi feature ⇒ sửa cả hai và chạy lại `python -m aiot_ml.train_gas_edge` (sinh lại `firmware/include/gas_model.h`).

## Cài môi trường (máy mới, Windows/Git Bash)
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt -r ml/requirements.txt streamlit platformio
.venv/Scripts/python -m pip install -e ml          # package mlcore + aiot_ml
export PYTHONUTF8=1                                 # bắt buộc trên Windows (log tiếng Việt)
```
(Linux/macOS: thay `.venv/Scripts/` bằng `.venv/bin/`.)

## Lệnh kiểm thử
```bash
cd ml && ../.venv/Scripts/python -m pytest -q                 # 42 test mlcore + pipeline
cd backend && ../.venv/Scripts/python -m pytest -q tests      # 20 test backend (gồm integration với Mosquitto nếu có)
cd firmware && ../.venv/Scripts/pio test -e native            # 14 test firmware trên PC (cần g++; test_gas_model bỏ qua khi chưa có model)
.venv/Scripts/python -m pytest -q dashboard/tests              # 8 smoke test dashboard (phản hồi API chụp từ trạm thật)
cd firmware && cp -n include/secrets.h.example include/secrets.h && ../.venv/Scripts/pio run -e esp32dev
```

## Docker
```bash
docker compose up -d --build            # trùng cổng 1883 với Mosquitto Windows? đặt MQTT_HOST_PORT=11883 trong .env
docker compose --profile monitoring up -d grafana
```

## Báo cáo / slide (docs/report/)
- Nội dung: `bao_cao.md` (nguồn) → `python tools/md_to_docx.py docs/report/bao_cao.md` (cần MS Word, pip install markdown).
- Slide: `cd tools/slides && npm install && node build_slides.js` — số liệu chép tay trong script, cập nhật khi huấn luyện lại.
- Hình: `tools/make_report_figures.py`, `node tools/render_mermaid.js` (từ tools/slides sau npm install).

## Chạy hệ thống local (không Docker)
```bash
# 1. broker: mosquitto với broker/mosquitto/acl + passwd (make_passwd.sh); user backend/backend-pass, station01/change-me
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
- `Arduino.h` định nghĩa macro `RISING/FALLING/HIGH/LOW` — không đặt tên enum trùng.
- PubSubClient chỉ publish QoS 0; độ tin cậy dựa vào `seq` + đệm offline + chống trùng ở backend.
- Telemetry DB khoá chính (device_id, ts, seq) — phù hợp hypertable TimescaleDB.
- `ml/models/registry.json` phải lưu đường dẫn kiểu POSIX (`models/forecast/...`) — backend chạy trong Linux container.
- **Chỉ dùng số liệu đo thật** (Open-Meteo + cảm biến trạm). Không sinh/giả lập dữ liệu để huấn luyện hay đưa vào báo cáo.
  Chưa có dữ liệu khí đo thật ⇒ `firmware/include/gas_model.h` để `GAS_MODEL_AVAILABLE 0`, edge chạy rule; không có
  `ml/models/gas_edge.json`, `gas_anomaly.json` (backend tự bỏ qua bước Isolation Forest).
