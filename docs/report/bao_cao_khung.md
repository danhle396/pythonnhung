# Khung báo cáo đồ án (task.md §13)

> **Bản đầy đủ đã viết: `docs/report/bao_cao.md` (→ `bao_cao.docx`).** File này giữ lại làm dàn ý và bản đồ nguồn số liệu.

> Khung chi tiết để viết báo cáo. Mỗi mục ghi **nguồn số liệu / hình / code** đã có trong repo.
> Chỗ đánh dấu ✍ là phần cần tự viết; ⚙ là phần cần số liệu phần cứng thật.

## Chương 1 — Giới thiệu
1.1 Bối cảnh: khí hậu Đà Nẵng (mùa mưa 9–12, bão, độ ẩm ~80 %; số liệu: tỉ lệ giờ có mưa theo tháng 2021–2025
    trong `ml/data/external/vku_hourly_2021_2025.csv`: tháng 10–12 ≈ 56–66 %), tai nạn cháy nổ gas gia đình ✍.
1.2 Mục tiêu (task.md §1.1) và KPI (§1.2). 1.3 Phạm vi: nguyên mẫu học thuật, 1 trạm tại VKU (15.975°N, 108.253°E).
1.4 Đóng góp: (a) AI lai edge–cloud; (b) thư viện ML tự xây dựng `mlcore`; (c) quy trình xuất model sang C kiểm chứng
    khớp 100 %; (d) đánh giá Rule / Model / Hybrid.

## Chương 2 — Cơ sở lý thuyết
2.1 IoT/AIoT, Edge vs Cloud. 2.2 MQTT: QoS 0/1/2, retain, LWT, ACL (`docs/architecture/mqtt.md`).
2.3 Cảm biến: DHT22, BMP280 (công thức quy áp mực nước biển), BH1750, YL-83, **MQ-2 (cảm biến MOS, Rs/R0, đường cong
    ppm = A·(Rs/R0)^B, ảnh hưởng nhiệt/ẩm, nhạy chéo cồn)**, LEL của LPG.
2.4 Thuật toán đã tự cài đặt — công thức lấy từ docstring:
| Thuật toán | File |
|---|---|
| Chuẩn hoá, IQR/z-score, nội suy, mã hoá chu kỳ | `ml/mlcore/preprocessing.py` |
| Linear/Ridge (nghiệm đóng + GD), Logistic (sigmoid/softmax, L2) | `ml/mlcore/linear.py` |
| Holt-Winters cộng tính, damped trend | `ml/mlcore/smoothing.py` |
| CART: histogram binning, Gini/Entropy có trọng số lớp, gain Newton | `ml/mlcore/tree.py` |
| Random Forest, Gradient Boosting (gradient/hessian, bước Newton, early stopping) | `ml/mlcore/ensemble.py` |
| Isolation Forest (c(n), anomaly score), CUSUM hai phía | `ml/mlcore/anomaly.py` |
| MLP, GRU + BPTT, gradient clipping | `ml/mlcore/nn.py` |
| SGD / Momentum / Adam | `ml/mlcore/optim.py` |
| MAE/RMSE/MAPE/R², P/R/F1, ROC-AUC Mann–Whitney, Brier | `ml/mlcore/metrics.py` |
| Permutation importance | `ml/mlcore/explain.py` |
| Zambretti | `firmware/src/nowcast.cpp` |
2.5 Công trình liên quan ✍ (TinyML, dự báo thời tiết bằng GBDT/LSTM, cảnh báo gas IoT).

## Chương 3 — Thiết kế hệ thống
3.1 Kiến trúc: `docs/architecture/system_block_diagram.drawio`, task.md §3. 3.2 Phần cứng & sơ đồ chân: task.md §2,
    `firmware/include/config.h` ⚙ ảnh lắp ráp, sơ đồ Fritzing/KiCad. 3.3 MQTT: `docs/architecture/mqtt.md`.
3.4 CSDL (ERD): `backend/app/db/models.py` (devices, telemetry-hypertable, alerts, forecasts, nowcasts, device_configs,
    commands, model_registry, notifications); continuous aggregate 1m/10m/1h, retention 90 ngày (`migrations/versions/0001_initial.py`).
3.5 Sơ đồ tuần tự cảnh báo / dự báo / cấu hình: `docs/architecture/sequences.md`.
3.6 Cấp cảnh báo, hysteresis, debounce, quy tắc fusion `level = max(rule, model)`.

## Chương 4 — Hiện thực
4.1 Firmware: FreeRTOS 3 task, WDT, đệm offline, OLED (`firmware/src/*`). Build: RAM 14.5 %, Flash 46.6 %.
4.2 Thư viện `mlcore`: giao diện chung `fit/predict/predict_proba/to_dict/from_dict`, vector hoá NumPy, histogram
    binning + trừ histogram; kiểm chứng: 41 test (dữ liệu đồ chơi, gradient check < 1e-5, round-trip).
4.3 Xuất model sang C: `ml/mlcore/export_c.py` → `firmware/include/gas_model.h`; kiểm chứng g++ và Unity (`firmware/test/test_gas_model`) 0 lệch.
4.4 Backend: ingest, alert service (leo thang, Isolation Forest, offline, nhắc lại), forecast service (bias correction), API + JWT.
4.5 Dashboard ✍ ảnh chụp 6 trang (`streamlit run dashboard/app.py`). 4.6 Triển khai Docker (`docker-compose.yml`).

## Chương 5 — Thực nghiệm và đánh giá
5.1 Dự báo thời tiết: `docs/report/results_forecast.md`, hình `figures/forecast_3h_nov2025.png`, `figures/importance_temp_1h.png`.
    Thảo luận: GBDT tốt nhất mọi cặp; GRU NumPy gần bằng GBDT; persistence độ ẩm 6h rất kém do chu kỳ ngày.
5.2 Cảnh báo khí tại edge — Rule / Model / Hybrid: `docs/report/results_gas_edge.md` (⚠ hiện là mô phỏng → ⚙ chạy lại với
    dữ liệu thật từ `tools/label_logger.py`). Thảo luận: hybrid phát hiện khói/rò rỉ chậm sớm hơn; báo động giả do cồn.
5.3 Bất thường ở cloud: `docs/report/results_anomaly.md` (Isolation Forest vs z-score theo giờ, CUSUM trôi R0).
5.4 Hiệu năng hệ thống: `docs/report/results_load_20.md`, `results_load_50.md` (mất gói 0 %, P95 broker ≈ 2 ms);
    độ trễ cảm biến → thông báo ≈ 0.45 s (simulator). ⚙ Độ trễ edge thật (xả gas → còi), end-to-end tới Telegram P50/P95.
5.5 Tài nguyên edge ⚙: flash/RAM (đã có), thời gian suy luận trên ESP32 (`pio test -e esp32dev -f test_gas_model`), công suất.
5.6 Độ bền ⚙: chạy 72 h (heap, reconnect, WDT reset từ topic status), test mất Wi-Fi / mất broker, so sánh trạm với Open-Meteo.

## Chương 6 — Kết luận và hướng phát triển
Tóm tắt KPI đạt/chưa đạt ✍. Hướng phát triển: LoRa/NB-IoT, pin mặt trời, nhiều trạm (mesh), PM2.5, MQ-135/MQ-5 giảm
nhạy chéo, federated learning, lượng tử hoá model, OTA model qua MQTT.

## Tài liệu tham khảo (gợi ý)
Datasheet MQ-2 (Hanwei), BMP280 (Bosch), DHT22, BH1750; MQTT v3.1.1 (OASIS); Breiman 2001 (RF); Friedman 2001 (GBM);
Chen & Guestrin 2016 (XGBoost — công thức Newton); Liu et al. 2008 (Isolation Forest); Page 1954 (CUSUM);
Cho et al. 2014 (GRU); Holt 1957 / Winters 1960; Open-Meteo Historical API; NIOSH/OSHA về LEL LPG.

## Slide & demo
Slide 15–20 trang theo 6 chương. Kịch bản demo trực tiếp (task.md §13): dashboard → bật lửa gas lại gần → LED/còi đổi cấp
→ Telegram → bấm ack → rút Wi-Fi chứng minh edge vẫn cảnh báo. Không có phần cứng: dùng
`python tools/simulator.py --events "10:lpg_mid,200:smoke"` + dashboard.
