# Trạm AIoT giám sát môi trường — VKU Đà Nẵng

**Trạm AIoT giám sát môi trường, dự báo thời tiết ngắn hạn và cảnh báo sớm khí dễ cháy, khói theo mức nguy hiểm với AI lai Edge–Cloud trên ESP32 và MQTT.**

*An AIoT Station for Environment Monitoring, Short-Term Weather Forecasts, and Early Warnings of Flammable Gas and Smoke by Danger Level, Using Edge–Cloud AI on ESP32 and MQTT.*

Sinh viên thực hiện: Lê Thành Danh (23CE010), Nguyễn Bá Thiện (23CE076).

ESP32 đọc DHT22, BMP280, BH1750, YL-83, MQ-2 → cảnh báo khí/khói 4 cấp **ngay tại edge** (rule + cây quyết định,
chạy cả khi mất mạng) → MQTT → backend Python dự báo thời tiết 1h/3h/6h, xác nhận và leo thang cảnh báo, gửi Telegram/Email
→ dashboard realtime. **Toàn bộ mã nguồn là Python** (firmware ESP32 viết bằng MicroPython); mô hình học máy dùng
thư viện chuẩn: **LightGBM** (GBDT dự báo), **scikit-learn** (Ridge, Logistic, Random Forest, Isolation Forest),
**statsmodels** (Holt-Winters), **PyTorch** (GRU, chỉ để so sánh).

> ⚠ Nguyên mẫu học thuật — không thay thế thiết bị báo cháy/báo gas đã được chứng nhận.

```
firmware/   ESP32 + MicroPython: cảm biến, edge AI, cảnh báo, MQTT client tự viết, đệm offline, màn TFT ST7735
ml/         pipeline huấn luyện/suy luận (scikit-learn, LightGBM, statsmodels, PyTorch) + xuất Random Forest sang MicroPython
backend/    FastAPI + SQLAlchemy + MQTT ingest + alert/forecast service + Telegram
dashboard/  Streamlit (6 trang) + smoke test · grafana/  dashboard Grafana provision sẵn (tuỳ chọn)
broker/     cấu hình Mosquitto (auth + ACL theo thiết bị, TLS tuỳ chọn)
tools/      label_logger.py (thu dữ liệu khí có nhãn), load_test.py, make_report_figures.py, render_mermaid.py,
            render_drawio.py, md_to_docx.py
docs/       kiến trúc, MQTT, sơ đồ, kết quả thực nghiệm, báo cáo + slide (docs/report/)
```

## Cài đặt từ đầu (≤ 10 bước)

**Cách 1 — Docker (khuyến nghị):**
1. `git clone https://github.com/danhle396/pythonnhung.git && cd pythonnhung`
2. (Tuỳ chọn) tạo `.env` ở thư mục gốc để đổi mặc định: `JWT_SECRET`, `ADMIN_PASS`, `MQTT_PASS`, `MQTT_DEVICE_PASS`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`
   (danh sách đầy đủ và giá trị mặc định: `backend/app/core/config.py`, `docker-compose.yml`).
3. `docker compose up -d --build` → API `http://localhost:8000/docs`, dashboard `http://localhost:8501`
   (Grafana: `docker compose --profile monitoring up -d` → `http://localhost:3000`, admin/admin).
   Trùng cổng với dịch vụ có sẵn trên máy (vd. Mosquitto Windows ở 1883): đặt `MQTT_HOST_PORT=11883` (tương tự
   `API_HOST_PORT`, `DASHBOARD_HOST_PORT`, `DB_HOST_PORT`, `GRAFANA_HOST_PORT`) trong `.env`.
4. Nạp firmware MicroPython (chi tiết: `firmware/README.md`): `pip install -r firmware/requirements.txt`; nạp MicroPython
   ESP32_GENERIC bằng `python -m esptool`; tạo `firmware/src/credentials.py` (Wi-Fi,
   IP broker, mật khẩu thiết bị — xem `firmware/README.md`) → `python firmware/deploy.py --port COM5` → `python -m mpremote connect COM5 repl`.
5. Sau 24–48 h burn-in MQ-2 trong không khí sạch: dashboard → Thiết bị → **Hiệu chuẩn R0**.

**Cách 2 — chạy trực tiếp (dev, SQLite):**
1. `python -m venv .venv` và kích hoạt; `pip install -r backend/requirements.txt -r dashboard/requirements.txt && pip install -e ml`
2. Chạy Mosquitto với `broker/mosquitto/mosquitto.conf` (tạo passwd: `python broker/mosquitto/make_passwd.py`; sửa 2 dòng
   `password_file`/`acl_file` trỏ tới file passwd và `acl` trên máy, `persistence_location` tới thư mục có quyền ghi).
3. `cd backend && uvicorn app.main:app --port 8000`
4. `streamlit run dashboard/app.py`
5. Cấp nguồn trạm ESP32 (dữ liệu chỉ lấy từ cảm biến thật)

Windows: đặt `PYTHONUTF8=1` để log tiếng Việt hiển thị đúng.

## Huấn luyện lại mô hình
```bash
pip install -r ml/requirements.txt   # scikit-learn, LightGBM, statsmodels (+ torch CPU nếu cần GRU)
cd ml
python -m aiot_ml.fetch_open_meteo --start 2021-01-01 --end 2025-12-31   # 5 năm dữ liệu giờ tại VKU
python -m aiot_ml.train_forecast      # baseline + Holt-Winters + Ridge + GBDT (LightGBM) + GRU (PyTorch) → models/, docs/report/
python -m aiot_ml.train_gas_edge --data <csv thật>   # model edge → firmware/src/gas_model.py
python -m aiot_ml.train_anomaly       # Isolation Forest + CUSUM (không triển khai: cần vài tuần telemetry)
```
Model mới chỉ được thăng cấp trong `ml/models/registry.json` khi tốt hơn model đang dùng trên tập test
(`--force-promote` để thay bắt buộc, ví dụ khi đổi định dạng file model).

## Kiểm thử
```bash
cd ml && pytest -q                    # 21 test: feature, luật edge ≡ firmware, Holt-Winters ≡ statsmodels, khớp MicroPython ↔ scikit-learn
cd backend && pytest -q tests         # 21 test API, ingest, cảnh báo, forecast, integration với Mosquitto thật
pytest -q firmware/tests              # 33 test firmware MicroPython chạy trên PC (logic, driver, toàn luồng, mpy-cross)
pytest -q dashboard/tests             # 8 test: 6 trang dashboard + ack + gửi cấu hình (API giả)
python tools/load_test.py --devices 50 --duration 60 --api http://localhost:8000
```

## Kết quả chính
| Hạng mục                                    | KPI      | Kết quả                                                       |
| ------------------------------------------- | -------- | ------------------------------------------------------------- |
| MAE nhiệt độ 1h (GBDT, test 2025)           | < 1.0 °C | **0.30 °C**                                                   |
| MAE độ ẩm 1h                                | < 5 %RH  | **1.87 %RH**                                                  |
| F1 mưa 3h tới                               | > 0.75   | **0.833**                                                     |
| Mất gói MQTT (50 thiết bị × 1 msg/s, QoS 1) | < 1 %    | **0 %**                                                       |
| Độ trễ cảm biến → gửi thông báo             | < 5 s    | ⚙ chờ đo trên trạm thật                                       |
| Mất gói, Docker + TimescaleDB (50 thiết bị) | < 1 %    | **0 %**, P95 broker 3.4 ms, CPU backend ≈ 10 %                |
| Firmware ESP32 (MicroPython, có OTA)        | —        | ⚙ đo RAM/thời gian trên board bằng `firmware/bench_device.py` |

Chi tiết: `docs/report/results_*.md`. Dự án **chỉ dùng số liệu đo thật**. Chưa có dữ liệu khí MQ-2 đo thật nên chưa có mô
hình ML cảnh báo khí: firmware chạy luật ngưỡng (`firmware/src/gas_model.py`: `AVAILABLE = False`). Thu dữ liệu bằng
`tools/label_logger.py` rồi `python -m aiot_ml.train_gas_edge --data <csv>`.

## Tài liệu
- Kế hoạch: `task.md` · Tiến độ: `PROGRESS.md`
- MQTT: `docs/architecture/mqtt.md` · Sơ đồ tuần tự: `docs/architecture/sequences.md`
- Sơ đồ khối: `docs/architecture/system_block_diagram.drawio` · Kiến trúc + ERD (Mermaid): `docs/architecture/diagrams.md`
- Toàn dự án theo mô hình Input – Xử lý – Output: `docs/architecture/ipo.md` · Firmware: `firmware/README.md`
- **Báo cáo**: `docs/report/bao_cao.md` / `bao_cao.docx` · **Slide**: `docs/report/VKU-SLIDE.pptx` ·
  Kịch bản demo/video: `docs/report/kich_ban_demo.md`

### Sinh lại hình và báo cáo Word
```bash
python tools/make_report_figures.py --api http://localhost:8000 --minutes 4 --start <mốc UTC kịch bản>   # hình kết quả
python tools/render_mermaid.py       # sơ đồ Mermaid → PNG (Edge/Chrome có sẵn, điều khiển bằng Python qua CDP)
python tools/render_drawio.py docs/hardware/wiring.drawio   # sơ đồ đấu dây → PNG
pip install markdown && python tools/md_to_docx.py docs/report/bao_cao.md   # → .docx (cần MS Word)
```
