# Khung báo cáo đồ án (task.md §13)

> **Bản đầy đủ đã viết: `docs/report/bao_cao.md` (→ `bao_cao.docx`).** File này giữ lại làm dàn ý và bản đồ nguồn số liệu.

> Khung chi tiết để viết báo cáo. Mỗi mục ghi **nguồn số liệu / hình / code** đã có trong repo.
> Chỗ đánh dấu ✍ là phần cần tự viết; ⚙ là phần cần số liệu phần cứng thật.

## Chương 1 — Giới thiệu
1.1 Bối cảnh: khí hậu Đà Nẵng (mùa mưa 9–12, bão, độ ẩm ~80 %; số liệu: tỉ lệ giờ có mưa theo tháng 2021–2025
    trong `ml/data/external/vku_hourly_2021_2025.csv`: tháng 10–12 ≈ 56–66 %), tai nạn cháy nổ gas gia đình ✍.
1.2 Mục tiêu (task.md §1.1) và KPI (§1.2). 1.3 Phạm vi: nguyên mẫu học thuật, 1 trạm tại VKU (15.975°N, 108.253°E).
1.4 Đóng góp: (a) AI lai edge–cloud; (b) pipeline ML tái lập được với thư viện chuẩn (scikit-learn, LightGBM,
    statsmodels, PyTorch); (c) quy trình xuất Random Forest sang MicroPython kiểm chứng khớp 100 %; (d) đánh giá Rule / Model / Hybrid.

## Chương 2 — Cơ sở lý thuyết
2.1 IoT/AIoT, Edge vs Cloud. 2.2 MQTT: QoS 0/1/2, retain, LWT, ACL (`docs/architecture/mqtt.md`).
2.3 Cảm biến: DHT22, BMP280 (công thức quy áp mực nước biển), BH1750, YL-83, **MQ-2 (cảm biến MOS, Rs/R0, đường cong
    ppm = A·(Rs/R0)^B, ảnh hưởng nhiệt/ẩm, nhạy chéo cồn)**, LEL của LPG.
2.4 Mô hình học máy và thư viện:
| Mô hình                                                         | Thư viện                                   |
| --------------------------------------------------------------- | ------------------------------------------ |
| Ridge, Logistic (L2)                                            | scikit-learn `Ridge`, `LogisticRegression` |
| Holt-Winters cộng tính, damped trend                            | statsmodels `ExponentialSmoothing`         |
| Decision Tree, Random Forest có trọng số lớp (edge)             | scikit-learn                               |
| Gradient Boosting (gradient/hessian, leaf-wise, early stopping) | LightGBM `LGBMRegressor`, `LGBMClassifier` |
| Isolation Forest; CUSUM hai phía                                | scikit-learn; `ml/src/prep.py`             |
| GRU + Adam, gradient clipping (đối chứng)                       | PyTorch `nn.GRU`                           |
| MAE/RMSE/R², P/R/F1, ROC-AUC, Brier; permutation importance     | `sklearn.metrics`, `sklearn.inspection`    |
2.5 Công trình liên quan ✍ (TinyML, dự báo thời tiết bằng GBDT/LSTM, cảnh báo gas IoT).

## Chương 3 — Thiết kế hệ thống
3.1 Kiến trúc: sơ đồ Input – Xử lý – Output + `docs/architecture/system_block_diagram.drawio`, task.md §3.
3.2 Phân rã IPO 6 phân hệ + vòng phản hồi: `docs/architecture/ipo.md`. 3.3 Phần cứng & sơ đồ chân: task.md §2,
    `firmware/src/config.py` ⚙ ảnh lắp ráp, sơ đồ Fritzing/KiCad. 3.4 MQTT: `docs/architecture/mqtt.md`.
3.5 CSDL (ERD): `backend/app/db/models.py` (devices, telemetry-hypertable, alerts, forecasts, device_configs,
    commands, model_registry, notifications); continuous aggregate 1m/10m/1h, retention 90 ngày (`migrations/versions/0001_initial.py`).
3.6 Sơ đồ tuần tự cảnh báo / dự báo / cấu hình: `docs/architecture/sequences.md`.
3.7 Cấp cảnh báo, hysteresis, debounce, quy tắc fusion `level = max(rule, model)`.

## Chương 4 — Hiện thực
4.1 Firmware MicroPython: 2 luồng, WDT, đệm offline, driver tự viết, màn TFT ST7735 (`firmware/src/*.py`), 33 test pytest.
4.2 Pipeline học máy `ml/src/` (gói `aiot_ml`): feature, huấn luyện/so sánh mô hình, registry, lưu bằng joblib;
    kiểm chứng: 21 test (round-trip lưu/nạp, Holt-Winters ≡ statsmodels, feature không rò rỉ, edge ≡ firmware).
4.3 Xuất model sang MicroPython: `ml/src/export_micropython.py` → `firmware/src/gas_model.py`; kiểm chứng khớp scikit-learn 0 lệch + mpy-cross.
4.4 Backend: ingest, alert service (leo thang theo độ dốc ppm, offline, nhắc lại), forecast service (đầu vào Open-Meteo), API + JWT.
4.5 Dashboard ✍ ảnh chụp 6 trang (`streamlit run dashboard/app.py`). 4.6 Triển khai Docker (`docker-compose.yml`).

## Chương 5 — Thực nghiệm và đánh giá
5.1 Dự báo thời tiết: `docs/report/results_forecast.md`, hình `figures/forecast_3h_nov2025.png`, `figures/importance_temp_1h.png`.
    Thảo luận: GBDT (LightGBM) tốt nhất 4/6 cặp + cả 3 tầm mưa; GRU (PyTorch) ngang GBDT ở tầm 3 h; persistence độ ẩm 6h rất kém do chu kỳ ngày.
5.2 Cảnh báo khí tại edge — Rule / Model / Hybrid: ⚙ chờ dữ liệu đo thật từ `tools/label_logger.py`
    (`train_gas_edge --data` sinh `docs/report/results_gas_edge.md`). Hiện edge chạy rule.
5.3 Bất thường ở cloud: không triển khai (Isolation Forest/CUSUM có pipeline; không có vài tuần telemetry).
5.4 Hiệu năng hệ thống: `docs/report/results_load_20.md`, `results_load_50.md` (mất gói 0 %, P95 broker ≈ 2 ms);
    ⚙ Độ trễ cảm biến → thông báo, độ trễ edge thật (xả gas → còi), end-to-end tới Telegram P50/P95.
5.5 Tài nguyên edge ⚙: RAM trống (gc.mem_free), thời gian suy luận trên ESP32 (`firmware/bench_device.py`), công suất.
5.6 Độ bền ⚙: chạy 72 h (heap, reconnect, WDT reset từ topic status), test mất Wi-Fi / mất broker, so sánh trạm với Open-Meteo.

## Chương 6 — Kết luận và hướng phát triển
Tóm tắt KPI đạt/chưa đạt ✍. Hướng phát triển: LoRa/NB-IoT, pin mặt trời, nhiều trạm (mesh), PM2.5, MQ-135/MQ-5 giảm
nhạy chéo, federated learning, lượng tử hoá model, OTA model qua MQTT.

## Tài liệu tham khảo (gợi ý)
Datasheet MQ-2 (Hanwei), BMP280 (Bosch), DHT22, BH1750; MQTT v3.1.1 (OASIS); Breiman 2001 (RF); Friedman 2001 (GBM);
Ke et al. 2017 (LightGBM); Pedregosa et al. 2011 (scikit-learn); Liu et al. 2008 (Isolation Forest); Page 1954 (CUSUM);
Cho et al. 2014 (GRU); Holt 1957 / Winters 1960; Open-Meteo Historical API; NIOSH/OSHA về LEL LPG.

## Slide & demo
Slide 15–20 trang theo 6 chương. Kịch bản demo trực tiếp (task.md §13): dashboard → bật lửa gas lại gần → LED/còi đổi cấp
→ Telegram → bấm ack → rút Wi-Fi chứng minh edge vẫn cảnh báo (cần trạm thật).
