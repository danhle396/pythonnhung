# Tiến độ thực hiện task.md

> File này ghi lại phần nào của `task.md` **đã xong / đã kiểm chứng** và phần nào **còn lại**.
> Phiên làm việc tiếp theo: đọc `task.md` (mục 0 — 3 nguyên tắc bắt buộc, trong đó **Nguyên tắc 3: luôn đồng bộ mọi thứ**)
> → file này, rồi làm tiếp mục "CÒN LẠI" theo thứ tự. Cập nhật file này và `task.md` sau mỗi hạng mục hoàn thành.

Cập nhật lần cuối: 2026-11-13 (đồng bộ task.md với code, thêm nguyên tắc đồng bộ)

## ĐÃ XONG (đã chạy và kiểm chứng)

### ML — `ml/` (task.md §8), chỉ dùng NumPy/pandas, không dùng thư viện ML
- [x] `ml/mlcore/`: preprocessing, model_selection, metrics, linear (OLS/Ridge/Logistic + GD), smoothing (Holt-Winters),
      tree (CART histogram: hồi quy MSE/Newton, phân loại Gini/Entropy có trọng số lớp), ensemble (RF, GBDT MSE/log-loss,
      early stopping), anomaly (Isolation Forest, CUSUM, z-score theo giờ), nn (MLP, GRU + BPTT), optim (SGD/Momentum/Adam),
      explain (split gain, permutation), serialize (JSON/.npz + header), export_micropython (sinh `gas_model.py` cho ESP32).
- [x] Test: `ml/tests/` **46 test pass** (dữ liệu đồ chơi có đáp án, gradient check < 1e-5 cho Logistic/MLP/GRU,
      module MicroPython sinh ra khớp mlcore 0 lệch + biên dịch được bằng mpy-cross, edge firmware ≡ `gas_edge.py`,
      round-trip serialize, feature không rò rỉ tương lai, hysteresis/debounce).
- [x] `ml/src/fetch_open_meteo.py`: đã tải `ml/data/external/vku_hourly_2021_2025.csv` (43 824 giờ).
- [x] `ml/src/train_forecast.py`: kết quả trong `docs/report/results_forecast.md`. GBDT tốt nhất mọi cặp target × horizon:
      MAE T 1h = 0.30 °C, H 1h = 1.86 %RH, F1 mưa 3h = 0.839 (đạt toàn bộ KPI §1.2, vượt persistence). Có GRU NumPy để so sánh.
- [x] Model registry + log thí nghiệm: `ml/models/registry.json`, `ml/experiments/experiments.csv` (chỉ thăng cấp khi tốt hơn).
- [x] `ml/src/train_gas_edge.py` (chọn DT/RF, so sánh Rule/Model/Hybrid, xuất `firmware/src/gas_model.py`) — **bắt buộc `--data`** (dữ liệu đo thật).
- [x] `ml/src/train_anomaly.py` (Isolation Forest + CUSUM R0) — **bắt buộc `--data`** (telemetry thật).
- [x] 2026-11-11: **bỏ toàn bộ dữ liệu mô phỏng** theo yêu cầu (chỉ dùng số liệu đo thật): xoá `gas_sim.py`,
      `gas_simulated.csv`, `tools/simulator.py`, model/kết quả khí và bất thường, hình và ảnh chụp dashboard từ dữ liệu giả lập.
      `gas_model` → không có model (`AVAILABLE = False`), firmware/`gas_edge.py` tự chạy rule khi chưa có model.
- [x] `ml/src/forecast_infer.py`: suy luận dùng chung, bias correction trạm→Open-Meteo, khoảng tin cậy, fallback.

### Firmware — `firmware/` (task.md §6) — **MicroPython** (từ 2026-11-12, xem Đợt 4)
- [x] 2 luồng (chính: cảm biến/edge/còi/TFT; mạng: `_thread`), `machine.WDT` 30 s, NTP, Wi-Fi/MQTT reconnect + LWT,
      đọc DHT22/BMP280/BH1750/YL-83/MQ-2 + lọc median/EWMA, rule engine 4 cấp (hysteresis/debounce), model cây,
      fusion hybrid, mute 5 phút, sensor_fault, đệm offline trên flash (2000 bản ghi), `/config.json` + ack,
      màn TFT 1.8" ST7735 (SPI) 3 trang, publish telemetry/alert/status, OTA qua HTTP (manifest).
- [x] Driver BMP280, BH1750, ST7735 và MQTT client tự viết bằng Python; `deploy.py` (mpy-cross + mpremote), `bench_device.py`.
- [x] `pytest firmware/tests` **33 test pass** (logic port từ bộ test C++, driver, đệm offline, toàn luồng trạm với
      schema backend, MQTT với broker tối giản + Mosquitto thật, mpy-cross biên dịch toàn bộ 20 module).

### Backend — `backend/` (task.md §7, §10)
- [x] FastAPI + SQLAlchemy 2 (Postgres/Timescale hoặc SQLite), Alembic migration (hypertable, continuous aggregate, retention 90 ngày).
- [x] MQTT ingest (validate Pydantic, loại giá trị ngoài dải vật lý, chống trùng, ghi lô, WebSocket), publisher cmd/config/forecast.
- [x] Alert service: chính sách thông báo theo cấp, cooldown, nhắc lại cấp 3 tới khi ack, leo thang cloud (xu hướng ppm 10 phút,
      Isolation Forest), offline (> 60 s / LWT), ack qua API + nút inline Telegram.
- [x] Forecast service (APScheduler 10 phút, nguồn trạm → Open-Meteo → persistence), tin 6h sáng, notifier Telegram/Email.
- [x] REST API đủ danh sách §7.5 + JWT + `/docs`; `WS /ws/live`.
- [x] `backend/tests/` 14 test pass (đợt 1; đợt 2 thêm integration test → 15).
- [x] Integration test với Mosquitto thật (ingest, chống trùng, lệnh, LWT) — `backend/tests/`.

### Broker & công cụ
- [x] `broker/mosquitto/` (mosquitto.conf, acl theo thiết bị, `make_passwd.py`, `gen_certs.py` cho TLS).
- [x] `tools/load_test.py`, `tools/label_logger.py`.
- [x] `.gitignore` (bỏ file mẫu `.env.example`, `credentials_example.py` — cấu hình ghi trong README).

### Đợt 2 (2026-11-10)
- [x] **Dashboard** `dashboard/app.py` (Streamlit): Tổng quan, Biểu đồ (1h/24h/7 ngày, tải CSV), Dự báo (thực tế vs dự báo
      + khoảng tin cậy, xác suất mưa), Cảnh báo (timeline, lọc, nút ack), Thiết bị (lệnh, form ngưỡng/chu kỳ,
      lịch sử config/lệnh), Mô hình (registry + kết quả). Kiểm thử headless bằng `streamlit.testing.AppTest` trên API giả
      (fixture): 6/6 trang không lỗi, ack và gửi config hoạt động (thiết bị ack config).
- [x] **Docker**: `docker-compose.yml` (mosquitto tự tạo passwd từ env, timescaledb, backend chạy `alembic upgrade head`,
      dashboard, grafana profile `monitoring`), `backend/Dockerfile`, `dashboard/Dockerfile`, `.dockerignore`, healthcheck.
      Đã kiểm tra cú pháp YAML và migration Alembic (upgrade/downgrade trên SQLite). ⚠ **Chưa chạy thử `docker compose up`**
      vì máy phát triển không cài Docker — cần chạy thử trên máy có Docker.
- [x] **README.md** (cài đặt ≤ 10 bước), `docs/architecture/mqtt.md`, `docs/architecture/sequences.md` (Mermaid).
- [x] **Kiểm thử**: load test 20 và 50 thiết bị × 1 msg/s × 30 s, QoS 1 → `docs/report/results_load_20.md`, `results_load_50.md`
      (mất gói 0 %, P95 broker ≈ 2 ms, 100 % vào DB, CPU backend TB ≈ 55–61 % một lõi, SQLite).
      `backend/tests/test_integration_mqtt.py`: Mosquitto thật → ingest → DB → API, chống trùng khi gửi bù, cmd xuống thiết bị,
      LWT → offline (tự bỏ qua nếu không có mosquitto). Backend tổng cộng **15 test pass** (2026-11-12: thêm 2 → **17**).
- [x] `docs/report/bao_cao_khung.md`: khung 6 chương + nguồn số liệu/hình cho từng mục, tài liệu tham khảo, kịch bản demo.
- [x] OTA firmware qua HTTP (`cmd: ota` + `url`, API `POST /api/devices/{id}/cmd {"cmd":"ota","url":...}`); TLS 8883 có sẵn
      (`gen_certs.py`, `MQTT_CA_FILE`/`MQTT_PORT = 8883` trong `credentials.py`) — chưa thử TLS trên board.

### Đợt 3 (2026-11-10) — hoàn thiện phần mềm, báo cáo, slide
- [x] **Docker chạy thật** trên Docker Desktop (Windows 11/WSL2): `docker compose up -d --build` → 4 container healthy;
      migration tạo hypertable + 3 continuous aggregate + retention trên TimescaleDB 2.17/PG16; broker → DB → API;
      forecast service chạy trong container. Đã sửa: passwd Mosquitto sinh vào `/mosquitto/auth` (chủ mosquitto, 0700) thay vì
      thư mục mount; healthcheck không dùng `$SYS` (ACL chặn); cổng host cấu hình được (`MQTT_HOST_PORT`...);
      **registry.json lưu đường dẫn Windows** (`models\forecast\…`) làm backend Linux không nạp được model → sửa
      `train_forecast` (as_posix) + `forecast_infer` (chuẩn hoá) + chuẩn hoá registry.json; `.gitattributes` (eol=lf cho sh/conf/py).
- [x] Load test 50 thiết bị trên Docker + TimescaleDB → `docs/report/results_load_50_docker.md` (0 % mất, P95 3.4 ms, CPU backend ≈ 10 %).
- [x] Bias correction: khi hệ số góc trạm→Open-Meteo ngoài [0.5, 1.5] chỉ hiệu chỉnh độ lệch (trước đây clip 0.5 làm khoảng tin cậy
      rộng gấp đôi); kẹp độ ẩm dự báo trong [0, 100]. Thêm test → **ml 42 test pass**.
- [x] Dashboard: `?page=` / `?device=` trên URL, mặc định `station01`, trục giờ 24h, điểm + thanh CI cho dự báo, giờ địa phương.
      **Smoke test** `dashboard/tests/test_app.py` (6 trang + ack + gửi config) → 7 pass. 2026-11-12: fixture chụp lại từ trạm thật (`capture_fixture.py`).
- [x] Grafana: datasource uid cố định + dashboard provision sẵn `grafana/dashboards/vku_aiot.json` (đã kiểm tra: kết nối DB OK).
- [x] Hình báo cáo: `tools/make_report_figures.py` (MAE, F1 mưa, Rule/Model/Hybrid, load, diễn biến cảnh báo),
      `tools/render_mermaid.py` (kiến trúc, ERD, 3 sơ đồ tuần tự từ `docs/architecture/*.md`), ảnh chụp 6 trang dashboard + Grafana.
- [x] **Báo cáo đầy đủ 6 chương**: `docs/report/bao_cao.md` → `bao_cao.docx` (33 trang, `tools/md_to_docx.py` qua MS Word).
- [x] **Slide 18 trang**: `docs/report/slides_bao_ve.pptx` (nay sinh bằng `tools/slides/build_slides.py` — python-pptx, 19 trang, có speaker notes, biểu đồ native).
- [x] Kịch bản demo + video 4 phút + câu hỏi bảo vệ: `docs/report/kich_ban_demo.md`.
- [x] Sơ đồ đấu dây draw.io: `docs/hardware/wiring.drawio` (2 trang: cảm biến / cảnh báo; + `wiring-1.png`, `wiring-2.png`, bảng đấu dây `docs/hardware/README.md`,
      sinh từ `gen_wiring_drawio.py`, xuất PNG bằng `tools/render_drawio.py`); đã chèn vào báo cáo mục 3.2.

### 2026-11-12 — trạm thật lên mạng, dọn sạch dữ liệu giả lập
- [x] Đổi màn hình sang **TFT 1.8" ST7735 (SPI)**: firmware, sơ đồ đấu dây, báo cáo, slide. Còi 2 chân.
- [x] Nạp firmware vào ESP32 thật (COM3, Wi-Fi = Mobile Hotspot laptop, MQTT `192.168.137.1:11883`); dữ liệu thật vào DB từ 17:02.
- [x] **Xoá dữ liệu giả lập còn trong DB Docker**: 496 bản ghi `fw=sim-1.0.0`, 50 thiết bị `loadtest*` (1 505 bản ghi),
      64 cảnh báo + 178 thông báo cũ, 4 320 dự báo cũ; xoá retained cũ trên broker; refresh continuous aggregate.
- [x] Backend: sửa bộ đếm telemetry âm (TimescaleDB trả rowcount −1 → đếm bằng RETURNING); bỏ qua bản tin rỗng
      (xoá retained) thay vì tạo thiết bị ma; thêm `DELETE /api/devices/{id}`; `tools/load_test.py` tự xoá thiết bị tạm sau khi đo.
- [x] Fixture dashboard chụp lại từ trạm thật (bỏ fixture từ thời giả lập).
- [x] YL-83: ngưỡng theo số đo thật (khô ≥ 3100 mV; vài giọt nước 2853–3074 mV) + giữ mức mưa 30 s.
- [x] YL-83 hiệu chỉnh lại theo dataset (608 mẫu khô = 3134 mV trần ADC; 54 mẫu ướt P10/P25/P50 = 2930/2997/3088 mV):
      khô ≥ 3130, mưa phùn 3000–3129, mưa vừa 2900–2999, mưa to < 2900 mV.
- [x] Sơ đồ đấu dây: sửa cầu phân áp MQ-2 (nút giữa R1/R2 ở phía GPIO32, không phải phía AO).
- [x] Giờ đo: backend thay ts < 2020 (ESP32 chưa có NTP) bằng giờ nhận; firmware gửi ts = 0 thay vì giây-từ-lúc-bật,
      khởi động lại SNTP khi Wi-Fi vừa lên (+2 máy chủ dự phòng) → có giờ sau ≈ 20 s thay vì vài phút.
- [x] **Tình trạng từng cảm biến**: API `GET /api/sensors/{id}` (ok / chập chờn / lỗi / mất dữ liệu / trạm offline, lý do,
      lần cuối còn tốt) + khung "Tình trạng cảm biến" ở trang Tổng quan; ô số liệu của cảm biến lỗi hiện "⚠ Lỗi".
- [x] Thử còi (cmd `test_alarm`): firmware gửi `type: test` (trước bị ghi nhầm cấp 3 `cloud_escalation`); backend không
      gửi Telegram/Email và không nhắc lại cảnh báo `test`; sửa 4 bản ghi thử còi 18:24–18:25 thành `test`.
- [x] **Bỏ nút tắt còi** (theo yêu cầu nhóm): xoá code đọc GPIO13, khỏi sơ đồ và tài liệu; tắt còi bằng lệnh `mute` trên dashboard.
- [x] Dashboard: banner khí chỉ hiện cấp khi đánh giá được — trạm offline / MQ-2 lỗi / đang thử còi / MQ-2 làm nóng hiện riêng.

### Đợt 4 (2026-11-12) — chuyển toàn bộ dự án sang Python (yêu cầu môn *Python cho hệ thống nhúng*)
- [x] Nguyên tắc **chỉ dùng Python** ghi vào `task.md` §0 (`CLAUDE.md` đã xoá, nội dung gộp vào `task.md`).
- [x] Firmware C++/PlatformIO → **MicroPython** (`firmware/src/`, 21 module); xoá toàn bộ `.cpp/.h`, `platformio.ini`,
      `include/`, test Unity. Cấu hình Wi-Fi/MQTT cũ chuyển sang `firmware/src/credentials.py` (gitignore).
- [x] `mlcore/export_c.py` → `mlcore/export_micropython.py` (`gas_model.py`, mảng nút đóng gói bytes, float32);
      `train_gas_edge.py` kiểm tra khớp bằng Python thay cho g++; thêm `ml/tests/test_edge_parity.py`.
- [x] Công cụ Node.js → Python: `tools/render_mermaid.py`, `tools/render_drawio.py` (Edge headless qua CDP, `browser_cdp.py`),
      `tools/slides/build_slides.py` (python-pptx, thêm slide IPO và firmware MicroPython); script shell broker →
      `make_passwd.py`, `gen_certs.py` (container mosquitto sinh passwd bằng lệnh trong docker-compose.yml).
- [x] Tài liệu (README, báo cáo, sơ đồ khối, sơ đồ đấu dây, IPO, MQTT, tuần tự) cập nhật theo firmware MicroPython.

### Đợt 5 (2026-11-13) — bỏ dự báo áp suất, vẽ lại sơ đồ khối
- [x] **Bỏ target dự báo áp suất** (`pres` 1/3/6 h): trạm đo ở mặt đất, không dự báo được trường khí áp. Áp suất BMP280
      vẫn đo và vẫn là feature đầu vào. Sửa `ml/configs/forecast.json`, `features.TARGETS`,
      `forecast_infer.persistence_fallback`, forecast service, dashboard (2 biểu đồ), xoá `models/forecast/pres_*.json`
      và mục registry; bỏ cột `pres_*` trong `results_forecast.md`/`forecast_results.json` (không train lại — số liệu
      temp/hum/mưa giữ nguyên, model GBDT khớp MAE); vẽ lại hình `forecast_mae_compare.png`, `forecast_3h_nov2025.png`.
      Còn 9 mô hình GBDT (6 hồi quy + 3 mưa). `gru_all` (chỉ để so sánh) vẫn có đầu ra `pres` từ lần train cũ.
- [x] `docs/architecture/system_block_diagram.drawio` vẽ lại kiểu khối ngang: Cảm biến → ESP32 → Mosquitto → Backend
      → Dashboard/Telegram, hàng dưới là ngoại vi (nút, còi/LED, TFT) và DB, Open-Meteo, huấn luyện offline.
- [x] **Bỏ nowcast Zambretti tại edge** (cũng là dự báo dựa trên áp suất): xoá `firmware/src/nowcast.py`, topic
      `…/nowcast` (firmware, ACL, ingest), bảng `nowcasts` (migration `0002_drop_nowcasts`), API `/api/nowcast/{id}`,
      phần nowcast trên dashboard và tin 6 h sáng; trang 3 màn TFT chỉ còn dự báo nhận từ cloud. Firmware: 20 module, 33 test.
- [x] **Dự báo luôn lấy đầu vào từ Open-Meteo** (quan trắc 4 ngày gần nhất tại toạ độ trạm): trạm ở mặt đất, chủ yếu
      trong nhà, chỉ ra ngoài trời từng đêm nên số đo trạm không dùng làm đầu vào. Bỏ `BiasCorrector`,
      `station_to_canonical`, `persistence_fallback`; không lấy được Open-Meteo → bỏ qua lượt (`source: unavailable`).
      Biến môi trường `USE_OPEN_METEO_FALLBACK` → `USE_OPEN_METEO`. Dashboard trang Dự báo thêm bảng sai số dự báo so với
      số đo trạm (MAE, lệch TB theo biến × tầm) để đánh giá đêm đặt ngoài trời. Test: ML 46, backend 21.

### Đợt 6 (2026-11-13) — đồng bộ task.md với code
- [x] **`task.md` viết lại theo code hiện tại**: đánh dấu `[x]`/`[ ]`/⚙ cho từng mục, sửa mô tả lệch code (cây thư mục,
      sơ đồ chân có GPIO18 cấp nguồn YL-83, topic/payload theo `mqtt.md`, bảng CSDL có `commands`/`notifications`,
      danh sách API đầy đủ, LittleFS thay SPIFFS, OTA manifest thay `HTTPUpdate`, xuất model sang MicroPython thay C,
      bảng KPI có cột hiện trạng, kế hoạch 10 tuần có cột trạng thái).
- [x] Thêm **Nguyên tắc 2 (chỉ số liệu đo thật)** và **Nguyên tắc 3 (luôn đồng bộ mọi thứ)** vào `task.md` §0 — bảng
      "khi đổi X phải cập nhật Y" + lệnh chạy toàn bộ test trước khi kết thúc.
- [x] Đồng bộ số test thực tế **ml 48 · backend 21 · firmware 33 · dashboard 8 = 110** vào README, báo cáo
      (chương 4, 6, phụ lục), `build_slides.py` (`TESTS`), `kich_ban_demo.md`; `mqtt.md` bỏ nhắc "Simulator", fw mẫu `2.0.0`.

### Đợt 7 (2026-11-14) — khớp kế hoạch với thực tế trạm (trong nhà + một đêm ngoài trời)
- [x] Số test thật sau khi bỏ bias correction: **ml 46 · backend 21 · firmware 33 · dashboard 8 = 108** (task.md, PROGRESS).
- [x] Sơ đồ khối (sửa tại chỗ, không sinh lại): bỏ ô "Nút nhấn" (đã bỏ trong firmware), bỏ dòng chú thích cuối,
      ô Open-Meteo ghi 2 vai trò (2021–2025 huấn luyện · 4 ngày gần nhất làm đầu vào), backend bỏ Isolation Forest.
- [x] Bỏ các mục cần trạm chạy ngoài trời nhiều tuần: thu ≥ 3–4 tuần, "thu 24/7", huấn luyện lại hằng tuần,
      so sánh độ lệch cảm biến dài ngày → thay bằng **một đêm ngoài trời** + bảng sai số trên dashboard (báo cáo 5.1).
- [x] **Isolation Forest + CUSUM: "đã cài, có test, không triển khai"** (task.md §1.1/§7.3/§8.7/§14/§16, báo cáo
      2.2/2.4.5/3.x/4/5.3/6.2/phụ lục, `ipo.md`, `sequences.md`, `bao_cao_khung.md`, kịch bản demo, README, slide).
      Code không đổi: alert service chỉ dùng Isolation Forest nếu có `gas_anomaly.json` (không có) → leo thang theo độ dốc ppm.
- [x] **Bỏ bộ slide sinh tự động**: xoá `docs/report/slides_bao_ve.pptx` và `tools/slides/build_slides.py`;
      gỡ tham chiếu trong README, task.md (§0, cây thư mục, §13, §15), báo cáo phụ lục A.
- [x] **Slide bảo vệ** trên template VKU: `docs/report/VKU-SLIDE.pptx` (8 trang — bìa, giới thiệu, thành viên Lê Thành Danh
      23CE010 · Nguyễn Bá Thiện 23CE076, sơ đồ khối, sơ đồ chân 1/2 và 2/2, bảng so sánh mô hình hồi quy và mưa).
- [x] **Chuyển mô hình học máy sang thư viện chuẩn** (yêu cầu: số liệu so sánh phải đúng đắn) — xoá `ml/mlcore` và
      `test_mlcore.py`. GBDT → **LightGBM** 4.7 (triển khai), Ridge/Logistic/Decision Tree/Random Forest/Isolation Forest/độ đo →
      **scikit-learn** 1.9.1, Holt-Winters → **statsmodels** 0.15 (công thức h bước kiểm tra trùng `forecast()`), GRU →
      **PyTorch** 2.15 CPU (chỉ so sánh, không cài trên backend). Mới: `ml/src/prep.py`, `serialize.py` (joblib + JSON),
      `export_micropython.py` (Random Forest scikit-learn → `gas_model.py`), `tests/test_library_models.py`. Huấn luyện lại
      (`--force-promote`): MAE nhiệt 1 h 0,299 · ẩm 1 h 1,870 · F1 mưa 3 h 0,833; GBDT tốt nhất 4/6 cặp + 3/3 tầm mưa, GRU
      nhỉnh hơn 0,002 ở tầm 3 h. Backend image thêm `libgomp1`; alert service dùng `decision_function` của IsolationForest.
      Test: **ml 21 · backend 21 · firmware 33 · dashboard 8 = 83**. Cập nhật README, task.md §0/§3/§5/§7/§8/§12/§13/§14/§16,
      báo cáo (tóm tắt, 1.2, 1.4, 2.4, 4.2, 4.3, 5.1, 5.3, 6.1, TLTK, phụ lục) + `.docx`, `ipo.md`, `diagrams.md`,
      `sequences.md`, sơ đồ khối (sửa tại chỗ ô Huấn luyện offline), hình kết quả, sơ đồ Mermaid, `bao_cao_khung.md`,
      kịch bản demo, slide 1/2/4/7/8 (giữ chỉnh sửa tay của nhóm).
- [x] **Slide so sánh mô hình dùng số liệu bài báo** (yêu cầu nhóm): trang 7–9 của `VKU-SLIDE.pptx` thay kết quả tự chạy
      bằng số trích nguyên văn từ Dong 2026 (arXiv:2603.23282, Bảng I–II), Darmawan 2023 (IJASEIT 13(3), Bảng V), Ke 2017
      (LightGBM, NIPS 30, Bảng 2–3), Yu 2021 (arXiv:2102.02892, Bảng 2); thêm trang 10 tài liệu tham khảo. Báo cáo §2.5 thêm
      Bảng 2.1–2.4 và TLTK [19]–[21]; chương 5 vẫn giữ kết quả thực nghiệm của trạm (`results_forecast.md`).
      Đồng bộ tên đề tài chính thức + bản tiếng Anh B1, họ tên/MSSV hai thành viên vào README, task.md, báo cáo, backend, dashboard.
- [x] Sơ đồ chân `wiring.drawio` (sửa tại chỗ): bỏ dòng chú thích ký hiệu và 2 câu ghi chú trang 2; `gen_wiring_drawio.py` bỏ theo;
      xuất lại `wiring-1/2.png` (cả `docs/report/figures/`), cập nhật slide 5–6 và `bao_cao.docx`. Slide viết gọn: bỏ câu bình
      luận, ghi chú trong ngoặc; nguồn số liệu trang 7–9 chỉ ghi tác giả — tên bài báo.

## CÒN LẠI (cần người / phần cứng — phần mềm đã xong)
- [ ] **Nguồn trạm**: board tự khởi động lại khi bật Wi-Fi (POWERON_RESET) khi cấp nguồn qua USB → dùng nguồn 5 V/2 A vào VIN.
- [ ] **YL-83**: ADC kẹt 3134 mV (trần) kể cả khi nhỏ nước → kiểm tra dây tấm cảm biến ↔ LM393, AO (không phải DO) → GPIO34.
- [ ] **MQ-2**: ADC kẹt 142 mV, `sensor_ok.gas = false` → kiểm tra VCC 5 V (VIN) và cầu phân áp 10k/20k → GPIO32.
- [ ] Điền GVHD ở đầu `docs/report/bao_cao.md` (họ tên, MSSV đã điền) rồi chạy lại `python tools/md_to_docx.py docs/report/bao_cao.md`.
- [ ] Quay video demo theo `docs/report/kich_ban_demo.md` (cần trạm thật).
- [ ] Thu dữ liệu khí thật → `python -m aiot_ml.train_gas_edge --data ...`;
      cập nhật báo cáo 5.2, chạy lại `tools/make_report_figures.py`.
- [ ] Chụp lại ảnh dashboard/Grafana khi trạm thật đã gửi dữ liệu (ảnh cũ chụp từ dữ liệu giả lập đã bị xoá).
- [ ] **Nạp firmware MicroPython lên board thật** (`firmware/README.md`): nạp MicroPython ESP32_GENERIC bằng esptool →
      `python firmware/deploy.py --port COM3` → kiểm tra log `[SENS]`, màn TFT, telemetry vào DB (`credentials.py` đã chuyển
      sẵn Wi-Fi/MQTT từ cấu hình cũ). Đo `firmware/bench_device.py` (µs/bước edge, RAM trống) để điền báo cáo 5.5.
- [ ] Đo đạc phần cứng (⚙ trong báo cáo chương 5): độ trễ edge, end-to-end Telegram P50/P95, 72 h, mất Wi-Fi, báo động giả,
      công suất; chụp ảnh lắp ráp.
- [ ] Chạy thử `docker compose up -d` sau khi đổi lệnh sinh passwd của container mosquitto (đã kiểm tra `docker compose
      config`; Docker Desktop chưa bật lúc chuyển đổi).

## VIỆC CẦN NGƯỜI LÀM (phần cứng — Claude không làm được)
- Phần cứng của nhóm: còi active 2 chân (nối thẳng GPIO25, `BUZZER_ACTIVE_LOW = False`), màn TFT 1.8" ST7735 (SPI), LED xanh/đỏ (không có LED vàng, S8050, relay — `config.py`: `HAS_LED_YELLOW = False`, `HAS_RELAY = False`).
- Mua MQ-2, điện trở phân áp 10k/20k; lắp theo `firmware/src/config.py`; đo lại `MQ2_RL_KOHM` trên module.
- `firmware/src/credentials.py` (Wi-Fi/MQTT). Nạp: `python firmware/deploy.py --port COM3` (hoặc Thonny với `--source`).
- Burn-in MQ-2 24–48 h → lệnh `calibrate` (đo R0). Hiệu chuẩn YL-83 (`RAIN_MV_*`).
- `python -m mpremote connect COM3 run firmware/bench_device.py` trên ESP32 thật để đo µs suy luận (khi đã có model).
- Thu dữ liệu khí thật bằng `tools/label_logger.py` → `python -m aiot_ml.train_gas_edge --data ml/data/raw/gas_labeled.csv`.
- Kiểm tra báo động giả do cồn (MQ-2 nhạy chéo theo datasheet) khi thí nghiệm; cân nhắc thêm MQ-135/MQ-5.
