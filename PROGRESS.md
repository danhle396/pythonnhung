# Tiến độ thực hiện task.md

> File này ghi lại phần nào của `task.md` **đã xong / đã kiểm chứng** và phần nào **còn lại**.
> Phiên Claude Code tiếp theo: đọc `CLAUDE.md` → `task.md` → file này, rồi làm tiếp mục "CÒN LẠI" theo thứ tự.
> Cập nhật file này sau mỗi hạng mục hoàn thành.

Cập nhật lần cuối: 2026-11-09

## ĐÃ XONG (đã chạy và kiểm chứng)

### ML — `ml/` (task.md §8), chỉ dùng NumPy/pandas, không dùng thư viện ML
- [x] `ml/mlcore/`: preprocessing, model_selection, metrics, linear (OLS/Ridge/Logistic + GD), smoothing (Holt-Winters),
      tree (CART histogram: hồi quy MSE/Newton, phân loại Gini/Entropy có trọng số lớp), ensemble (RF, GBDT MSE/log-loss,
      early stopping), anomaly (Isolation Forest, CUSUM, z-score theo giờ), nn (MLP, GRU + BPTT), optim (SGD/Momentum/Adam),
      explain (split gain, permutation), serialize (JSON/.npz + header), export_c (sinh C header).
- [x] Test: `ml/tests/` **41 test pass** (dữ liệu đồ chơi có đáp án, gradient check < 1e-5 cho Logistic/MLP/GRU,
      so khớp C (g++) với Python 0 lệch, round-trip serialize, feature không rò rỉ tương lai, hysteresis/debounce).
- [x] `ml/src/fetch_open_meteo.py`: đã tải `ml/data/external/vku_hourly_2021_2025.csv` (43 824 giờ).
- [x] `ml/src/train_forecast.py`: kết quả trong `docs/report/results_forecast.md`. GBDT tốt nhất mọi cặp target × horizon:
      MAE T 1h = 0.30 °C, H 1h = 1.86 %RH, F1 mưa 3h = 0.839 (đạt toàn bộ KPI §1.2, vượt persistence). Có GRU NumPy để so sánh.
- [x] Model registry + log thí nghiệm: `ml/models/registry.json`, `ml/experiments/experiments.csv` (chỉ thăng cấp khi tốt hơn).
- [x] `ml/src/train_gas_edge.py` → `firmware/include/gas_model.h` (RF 10 cây, ~17 kB flash), so sánh Rule/Model/Hybrid:
      `docs/report/results_gas_edge.md`. ⚠ **Dữ liệu khí hiện là MÔ PHỎNG** (`gas_sim.py`) — phải chạy lại với dữ liệu thật.
- [x] `ml/src/train_anomaly.py` (Isolation Forest + CUSUM R0) → `ml/models/gas_anomaly.json`, `docs/report/results_anomaly.md` (mô phỏng).
- [x] `ml/src/forecast_infer.py`: suy luận dùng chung, bias correction trạm→Open-Meteo, khoảng tin cậy, fallback.

### Firmware — `firmware/` (task.md §6)
- [x] PlatformIO project, FreeRTOS 3 task (sensors/edgeai/network), WDT, NTP, Wi-Fi/MQTT reconnect + LWT,
      đọc DHT22/BMP280/BH1750/YL-83/MQ-2 + lọc median/EWMA, rule engine 4 cấp (hysteresis/debounce), model cây,
      fusion hybrid, mute 5 phút, sensor_fault, nowcast Zambretti, đệm offline LittleFS (2000 bản ghi), config NVS + ack,
      OLED 3 trang, publish telemetry/alert/status/nowcast.
- [x] `pio run -e esp32dev` **build thành công** (RAM 14.5 %, Flash 46.6 %).
- [x] `pio test -e native` **12/12 pass** (filters, rule engine, alert manager, nowcast, model C khớp Python).

### Backend — `backend/` (task.md §7, §10)
- [x] FastAPI + SQLAlchemy 2 (Postgres/Timescale hoặc SQLite), Alembic migration (hypertable, continuous aggregate, retention 90 ngày).
- [x] MQTT ingest (validate Pydantic, loại giá trị ngoài dải vật lý, chống trùng, ghi lô, WebSocket), publisher cmd/config/forecast.
- [x] Alert service: chính sách thông báo theo cấp, cooldown, nhắc lại cấp 3 tới khi ack, leo thang cloud (xu hướng ppm 10 phút,
      Isolation Forest), offline (> 60 s / LWT), ack qua API + nút inline Telegram.
- [x] Forecast service (APScheduler 10 phút, nguồn trạm → Open-Meteo → persistence), tin 6h sáng, notifier Telegram/Email.
- [x] REST API đủ danh sách §7.5 + JWT + `/docs`; `WS /ws/live`.
- [x] `backend/tests/` **14 test pass**.
- [x] Chạy end-to-end thật: Mosquitto (auth + ACL) → backend → `tools/simulator.py` (kịch bản lpg_mid): 531 tin, 0 lỗi,
      cảnh báo 0→1→2→3→2→1, độ trễ cảm biến→gửi thông báo ≈ 450 ms, nhắc lại cấp 3 mỗi phút, forecast retain về thiết bị.

### Broker & công cụ
- [x] `broker/mosquitto/` (mosquitto.conf, acl theo thiết bị, make_passwd.sh, gen_certs.sh cho TLS).
- [x] `tools/simulator.py`, `tools/load_test.py` (chưa chạy), `tools/label_logger.py`.
- [x] `.gitignore`, `.env.example`.

## CÒN LẠI (làm theo thứ tự)
1. [ ] **Dashboard** `dashboard/app.py` (Streamlit, §9): tổng quan (thẻ T/H/P/Lux/Rain/Gas, đèn cấp, online, RSSI),
       biểu đồ 1h/24h/7 ngày, dự báo thực tế vs dự báo + khoảng tin cậy + xác suất mưa + nowcast, timeline cảnh báo + nút ack,
       trang thiết bị (ngưỡng, chu kỳ, test_alarm/mute/calibrate), trang mô hình (`/api/models`), xuất CSV, responsive.
       Gọi API backend (`API_URL`, đăng nhập JWT `ADMIN_USER/ADMIN_PASS`). Thêm `dashboard/requirements.txt`.
2. [ ] **Docker** (§11): `docker-compose.yml` (mosquitto, timescaledb, backend chạy `alembic upgrade head` rồi uvicorn,
       dashboard, grafana tuỳ chọn), `backend/Dockerfile` (cài `ml/` bằng `pip install -e ../ml`), `dashboard/Dockerfile`,
       healthcheck, tạo passwd mosquitto khi khởi động.
3. [ ] **README.md** (≤ 10 bước cài đặt) + `docs/architecture/mqtt.md` (topic/payload/QoS/retain theo §5) +
       sequence diagram luồng cảnh báo & dự báo (Mermaid) trong `docs/architecture/`.
4. [ ] **Kiểm thử** (§12): chạy `tools/load_test.py` 20 và 50 thiết bị → `docs/report/results_load.md`;
       viết `backend/tests/test_integration_mqtt.py` (tự bật mosquitto nếu có, simulator → broker → ingest → DB → API);
       test mất mạng/gửi bù bằng simulator; ghi bảng độ trễ P50/P95 vào `docs/report/`.
5. [ ] `docs/report/`: khung báo cáo 6 chương (§13) dùng các file results_*.md + hình trong `docs/report/figures/`.
6. [ ] (Nâng cao, tuỳ chọn) OTA qua HTTP trong firmware (`cmd: ota`), TLS 8883.

## VIỆC CẦN NGƯỜI LÀM (phần cứng — Claude không làm được)
- Mua MQ-2, buzzer, LED, nút, điện trở phân áp 10k/20k; lắp theo `firmware/include/config.h`; đo lại `MQ2_RL_KOHM` trên module.
- Copy `firmware/include/secrets.h.example` → `secrets.h`, điền Wi-Fi/MQTT. Nạp: `pio run -e esp32dev -t upload`.
- Burn-in MQ-2 24–48 h → lệnh `calibrate` (đo R0). Hiệu chuẩn YL-83 (`RAIN_MV_*`).
- `pio test -e esp32dev -f test_gas_model` trên ESP32 thật để đo µs suy luận và xác nhận khớp C/Python.
- Thu dữ liệu khí thật bằng `tools/label_logger.py` → `python -m aiot_ml.train_gas_edge --data ml/data/raw/gas_labeled.csv`.
- Lưu ý đã phát hiện: hơi cồn gây báo động giả (MQ-2 nhạy chéo) — nêu trong báo cáo, cân nhắc thêm MQ-135/MQ-5.
