# Trạm AIoT VKU – Task List
## Giám sát môi trường, dự báo thời tiết ngắn hạn và cảnh báo sớm khí dễ cháy/khói theo mức nguy hiểm — AI lai Edge–Cloud trên ESP32 + MQTT, 100 % Python
### Target: Nguyên mẫu trạm chạy thật tại VKU (Đà Nẵng) + báo cáo, slide, video demo bảo vệ đồ án môn *Python cho hệ thống nhúng*

**Platform:** ESP32 DevKit V1 (MicroPython) + Docker Compose (Mosquitto, TimescaleDB, FastAPI, Streamlit) | **Tool:** Python 3.12, scikit-learn, LightGBM, statsmodels, PyTorch, mpremote
**Goal:** Trạm đo 5 loại cảm biến, cảnh báo khí 4 cấp ngay tại edge (< 1 s, chạy cả khi mất mạng), dự báo T/H 1/3/6 h (MAE T 1h < 1 °C, H 1h < 5 %RH) và xác suất mưa lệch Google ≤ 10 điểm %.

> **Đề tài:** Trạm AIoT giám sát môi trường, dự báo thời tiết ngắn hạn và cảnh báo sớm khí dễ cháy, khói theo mức nguy hiểm với AI lai Edge–Cloud trên ESP32 và MQTT.
> **Tên tiếng Anh:** An AIoT Station for Environment Monitoring, Short-Term Weather Forecasts, and Early Warnings of Flammable Gas and Smoke by Danger Level, Using Edge–Cloud AI on ESP32 and MQTT.
> **Sinh viên thực hiện:** Lê Thành Danh (23CE010), Nguyễn Bá Thiện (23CE076).

> **TRẠNG THÁI (2026-11-19): Phase 1 (phần mềm + ML) ✅ | 1.7 Mưa miễn phí ⚠️ chờ số Google nhập tay | 2.2 Phần cứng ⚠️ trạm chạy thật trong nhà | 2.5–2.6 Đo đạc hiện trường ❌ Chưa bắt đầu**
> - Dự báo: MAE T 1h **0,299 °C** (target < 1,0) | MAE H 1h **1,870 %RH** (target < 5) | F1 mưa 3h **0,833** (target > 0,75) | Mưa lệch Google: chưa đo (target ≤ 10 điểm; 5 giờ đo thử lệch TB 12)
> - Test: **97 pass** (ml 31 · backend 24 · firmware 33 · dashboard 9) | Docker: 4 container healthy (lần build gần nhất trước đợt 9) | Trạm thật: gửi dữ liệu vào DB từ 2026-11-12
> - Edge: rule 4 cấp ✅ | model khí ❌ (`gas_model.AVAILABLE = False`) | MQ-2 ✅ đo được | YL-83 ✅ ngưỡng tạm 2600/2000 mV
> - ⚠️ Chưa có dữ liệu khí đo thật → edge chạy rule, bảng rule/model/hybrid còn trống; Isolation Forest/CUSUM đã cài nhưng không triển khai
> - ⚠️ Firmware `TELEMETRY_PERIOD_MS = 5000` + ngưỡng YL-83 mới **chưa nạp** lên board; cấp nguồn USB làm board reset khi bật Wi-Fi
> - **Bước tiếp theo NGAY:** `docker compose up -d --build backend dashboard` (~5 phút) → trang Dự báo nhập số Google 2–3 lần/ngày tới ≥ 40 giờ → bấm **Học lại hiệu chỉnh**

**Cách cập nhật file này (sau MỖI lần thay đổi):** (1) sửa khối **TRẠNG THÁI** ở trên — ngày, số liệu, số test, cảnh báo, bước
tiếp theo; (2) đánh dấu `[x]` / sửa mô tả mục liên quan cho khớp code; (3) ghi một đợt mới trong `PROGRESS.md` (nhật ký + CÒN LẠI);
(4) rà bảng đồng bộ ở Nguyên tắc 3. Ký hiệu: `[x]` đã làm và đã kiểm chứng (test/chạy thật) · `[ ]` chưa làm · ⚙ cần phần
cứng/người làm · ~~gạch ngang~~ đã bỏ khỏi đề tài (có lý do) · ✅ xong · ⚠️ một phần/có vấn đề · ❌ chưa bắt đầu.

**Mục tiêu chức năng:**
1. Thu thập liên tục: nhiệt độ, độ ẩm (DHT22), áp suất và nhiệt độ phụ (BMP280), cường độ ánh sáng (BH1750), mưa (YL-83), khí dễ cháy/khói (MQ-2).
2. Truyền dữ liệu thời gian thực qua **MQTT** lên server.
3. **Dự báo thời tiết ngắn hạn** (1h / 3h / 6h): nhiệt độ, độ ẩm, xác suất mưa. Áp suất chỉ là feature đầu vào, **không dự báo** (đã bỏ target `pres` và nowcast Zambretti ngày 2026-11-13). Xác suất mưa: xem 1.7.
4. **Cảnh báo sớm đa cấp** khí dễ cháy/khói: 4 cấp (Bình thường → Chú ý → Cảnh báo → Nguy hiểm).
5. **AI lai Edge–Cloud:** Edge (ESP32) cảnh báo khí ngay tại chỗ (rule engine + cây quyết định khi có model), phát hiện lỗi cảm biến, vẫn hoạt động khi mất mạng. Cloud (Python) dự báo thời tiết, xác nhận/leo thang cảnh báo (xu hướng ppm 10 phút), huấn luyện lại và đẩy cấu hình/ngưỡng xuống thiết bị.
6. Dashboard web (Streamlit) theo dõi realtime, lịch sử, dự báo và cảnh báo; thông báo qua Telegram/Email.

**Đối tượng xử lý:**
- **Type 1** (đo tại trạm, xử lý ở edge ESP32): DHT22 (T, RH), BMP280 (P, T phụ), BH1750 (lux), YL-83 (mức mưa 0–3), MQ-2 (Rs/R0, ppm)
- **Type 2** (nguồn ngoài, xử lý ở cloud): Open-Meteo Archive 2021–2025 (huấn luyện), quan trắc Open-Meteo 4 ngày gần nhất (đầu vào dự báo), Open-Meteo Ensemble ECMWF + GFS + ICON (xác suất mưa), số Google nhập tay (hiệu chỉnh mưa)

**Pipeline:**
```
Cảm biến → Lọc median/EWMA → Feature 10 chiều → Rule engine ──┐
                                              → Cây quyết định ┘→ Fusion max(rule, model) → Còi/LED/TFT + MQTT alert
MQTT telemetry → Ingest (Pydantic) → TimescaleDB → API/WS → Dashboard, Telegram/Email
Open-Meteo 4 ngày → 56 feature → LightGBM (T, H 1/3/6 h) ─────────────────┐
Open-Meteo Ensemble → tỉ lệ phương án ≥ θ mm → hiệu chỉnh theo Google ─┐  │→ forecasts + MQTT forecast → TFT/dashboard
                                         YL-83 đang mưa → + ≤ 10 điểm ─┴──┘
```

---

## 0. NGUYÊN TẮC BẮT BUỘC

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
> | Khi thay đổi…                                   | Phải cập nhật đồng bộ                                                                                                                                                                                         |
> | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
> | Bất kỳ code nào                                 | `task.md` (**khối TRẠNG THÁI**, đánh dấu `[x]`, sửa mô tả cho khớp code), `PROGRESS.md` (nhật ký + mục CÒN LẠI), `README.md`                                                                                  |
> | Chân GPIO, linh kiện (`firmware/src/config.py`) | `task.md` §2.2.1, `docs/hardware/gen_wiring_drawio.py` → `wiring.drawio` → `wiring-*.png` (`tools/render_drawio.py`), `firmware/README.md` (checklist cấp điện), báo cáo §3.3, slide                           |
> | Topic / payload MQTT                            | firmware (`station.py`, `payloads.py`, `net.py`), `broker/mosquitto/acl`, `backend/app/mqtt/ingest.py` + `schemas/payloads.py`, `docs/architecture/mqtt.md`, `task.md` §2.2.5, `sequences.md`                 |
> | Bảng / cột CSDL (`backend/app/db/models.py`)    | migration Alembic mới trong `backend/app/db/migrations/versions/`, ERD: trang 2 của `system_block_diagram.drawio` (xuất lại PNG) + bảng trong `diagrams.md`, `task.md` §2.2.6, báo cáo chương 3                                                              |
> | API REST/WS (`backend/app/api/`)                | `dashboard/app.py` + `dashboard/tests/` (fixture), `task.md` §2.2.6, `README.md`, báo cáo chương 4                                                                                                            |
> | Target / feature / model ML                     | `ml/configs/*.json`, `ml/src/features.py`, `ml/models/registry.json`, `docs/report/results_*.md`, forecast service, dashboard, `task.md` §1.3–1.7, báo cáo chương 5, slide |
> | Kiến trúc / luồng xử lý                         | `docs/architecture/system_block_diagram.drawio`, `ipo.md`, `diagrams.md`, `sequences.md`, xuất PNG `tools/render_drawio.py` → `system_block_diagram-N.png`, `task.md` Pipeline + §2.1, báo cáo chương 3                                   |
> | Số lượng test                                   | `README.md` (mục Kiểm thử), `PROGRESS.md`, `docs/report/bao_cao.md` (chương 4, 6, phụ lục B), `task.md` TRẠNG THÁI + §2.3                                                                                     |
> | KPI / số liệu kết quả                           | `task.md` TRẠNG THÁI + Metrics Mục Tiêu, `README.md`, báo cáo chương 5–6, slide                                                                                                                               |
> | Báo cáo nguồn                                   | sinh lại `bao_cao.docx` (`tools/md_to_docx.py`, cần MS Word)                                                                                                                                                 |
> | Xoá / đổi tên tính năng, file, module           | `grep` toàn repo tìm tham chiếu cũ (code, test, tài liệu, sơ đồ, slide) và xoá hết; bảng CSDL bị bỏ phải có migration `drop`                                                                                 |
>
> Lệnh kiểm tra trước khi kết thúc (Windows: đặt `PYTHONUTF8=1`):
> ```bash
> cd ml && pytest -q && cd ..            # 31 test
> cd backend && pytest -q tests && cd .. # 24 test
> pytest -q firmware/tests               # 33 test
> pytest -q dashboard/tests              # 9 test   → tổng 97
> ```

---

## PHASE 1 – PHẦN MỀM & HỌC MÁY (CLOUD)

### 1.1 Environment Setup ✅ Hoàn tất
> **Environment:** `.venv/` ở gốc repo (Python **3.12.10**) — activate: `.venv\Scripts\activate` (Windows)
> **Note:** scikit-learn và LightGBM **ghim phiên bản** trong `ml/pyproject.toml` để file `.joblib` nạp được ở backend; backend image cần `libgomp1` cho LightGBM; PyTorch chỉ cài trên máy phát triển (GRU so sánh), không cài trên backend.

- [x] Python 3.12 + venv, `pip install -e ml` → gói `aiot_ml` (`ml/src/`)
  - ML: numpy, pandas, scikit-learn==1.9.1, lightgbm==4.7.0, statsmodels==0.15.0, joblib (+ torch 2.15 CPU tuỳ chọn)
- [x] Backend: fastapi, uvicorn, sqlalchemy 2, alembic, psycopg 3, pydantic 2 + pydantic-settings, paho-mqtt 2, apscheduler 3, httpx, python-jose
- [x] Dashboard: streamlit ≥ 1.40, altair 5; firmware: esptool, mpremote, mpy-cross, pytest
- [x] Docker Desktop (Windows 11/WSL2, Docker 29.9) — `docker compose ps` = **4 container healthy** ✅
- [x] Git + `.gitignore` (`.env`, `__pycache__`, `firmware/build`, `firmware/src/credentials.py`, `broker/mosquitto/passwd`, `certs/`, `ml/data/raw`, `ml/data/processed`, `ml/models/*.npz`, `backend/*.db`). Không có `.env.example`/`credentials_example.py` — biến và cách tạo ghi trong README và `firmware/README.md`.
- [x] `.env` tuỳ chọn (mọi biến có mặc định trong `backend/app/core/config.py`, `docker-compose.yml`); cổng host broker **11883** (`MQTT_HOST_PORT`, vì Mosquitto Windows chiếm 1883).

```bash
# Cài lại từ đầu (nếu cần):
python -m venv .venv && .venv\Scripts\activate
pip install -r backend/requirements.txt -r dashboard/requirements.txt -r firmware/requirements.txt
pip install -e ml
docker compose up -d --build
```

---

### 1.2 Chuẩn bị Dữ liệu

> **Chiến lược:** Huấn luyện và dự báo hoàn toàn từ Open-Meteo (tái phân tích thật tại toạ độ trạm). Trạm ở mặt đất, chủ yếu trong nhà, chỉ đặt ngoài trời một đêm để đối chiếu → số đo trạm **không** dùng làm đầu vào/huấn luyện dự báo. Dữ liệu khí chỉ lấy từ thí nghiệm đo thật có gán nhãn. Không dùng dữ liệu mô phỏng (Nguyên tắc 2). Mọi nguồn **miễn phí, không cần khoá API**.

> **Trạng thái (2026-11-19): ⚠️ dữ liệu thời tiết đủ, dữ liệu khí chưa có**
> - ✅ Open-Meteo Archive 2021–2025 (43 824 giờ): DONE
> - ✅ Open-Meteo quan trắc 4 ngày gần nhất + Ensemble: lấy tự động mỗi 10 phút
> - ✅ Telemetry trạm thật: vào DB từ 2026-11-12 (trong nhà, chỉ để đối chiếu)
> - ⚠️ Số Google nhập tay: 0 / 40 giờ
> - ❌ Dữ liệu khí/khói có gán nhãn: chưa thu

---

#### Nhóm A – Tự tải hoàn toàn

- [x] **Open-Meteo Historical Weather (Archive)** ⭐⭐⭐ ✅ ACTIVE (huấn luyện)
  - `python -m aiot_ml.fetch_open_meteo` → `ml/data/external/vku_hourly_2021_2025.csv`
  - 43 824 giờ, 15.975 / 108.253, `Asia/Ho_Chi_Minh`; chỉ dùng biến trạm cũng đo được
  - Bản chất: mô hình lưới (ECMWF IFS ô ≈ 9 km, tâm ô cách VKU ≈ 4 km), **không** phải số đo tại VKU — License: CC BY 4.0
- [x] **Open-Meteo quan trắc gần nhất** ⭐⭐⭐ ✅ ACTIVE (đầu vào dự báo)
  - Forecast service lấy 4 ngày gần nhất (chỉ các giờ đã qua) mỗi 10 phút; lỗi mạng → bỏ qua lượt (`source: unavailable`)
- [x] **Open-Meteo Ensemble API** ⭐⭐⭐ ✅ ACTIVE (xác suất mưa)
  - `https://ensemble-api.open-meteo.com/v1/ensemble`, `models=ecmwf_ifs025,gfs025,icon_seamless`
  - ECMWF 51 + GFS 31 + ICON 40 = 122 phương án, lượng mưa từng giờ, 3 ngày tới

#### Nhóm B – Cần người / phần cứng

- [x] **Telemetry trạm thật** — MQTT → TimescaleDB (từ 2026-11-12). Không huấn luyện dự báo; dùng cho bảng sai số đêm ngoài trời (2.5).
  ~~Thu liên tục ≥ 3–4 tuần~~ — bỏ (trạm ở mặt đất, chủ yếu trong nhà).
- [ ] ⚙ **Số Google nhập tay** — dashboard trang Dự báo → "Xác suất mưa so với Google" (5 ô/lần, 2–3 lần/ngày) → bảng `google_rain_obs`
  - **Pass criterion:** ≥ 40 giờ để học hiệu chỉnh (`MIN_FIT_ROWS`)
- [ ] ⚙ **Dữ liệu khí/khói đo thật có gán nhãn** — `tools/label_logger.py --session N` (bấm phím đánh dấu sự kiện) → `ml/data/raw/gas_labeled.csv`
  - Kịch bản: không khí sạch (0), bật lửa gas xả không đốt ở 50/20/5 cm (1/2/3), khói nhang/giấy trong hộp kín, nhiễu (hơi nước, cồn, nước hoa)
  - **Thí nghiệm nơi thoáng, lượng nhỏ, có người giám sát, xa nguồn lửa.**

---

#### ⚠️ Rủi ro Dữ liệu

| Đối tượng | Trạng thái | Ghi chú |
|-----------|-----------|---------|
| **Dữ liệu mô phỏng** (`gas_sim.py`, `gas_simulated.csv`, `tools/simulator.py`, 496 bản ghi `fw=sim-1.0.0`, 50 thiết bị `loadtest*`) | ✅ REMOVED (2026-11-11/12) | Nguyên tắc 2 |
| **Nhãn mưa Open-Meteo ≥ 0,1 mm/h** | ⚠️ Lệch thực tế | Có ở 35 % số giờ, ~80 % số ngày (mưa phùn rải khắp ô lưới) → không dùng làm xác suất mưa hiển thị (1.7) |
| **Bias correction trạm → Open-Meteo** | ✅ REMOVED (2026-11-13) | Cần ≥ 2 tuần đo ngoài trời, không có |
| **Dữ liệu khí** | ❌ Chưa có | Edge chạy rule; pipeline ML sẵn sàng, chỉ cần `--data` |

**Nguồn đang THỰC SỰ được sử dụng:**
```
Dự báo T/H (LightGBM): Open-Meteo Archive 2021–2025 (huấn luyện) + quan trắc Open-Meteo 4 ngày (suy luận)
Xác suất mưa:          Open-Meteo Ensemble 122 phương án + hiệu chỉnh (số Google nhập tay) + YL-83 của trạm
Cảnh báo khí (edge):   số đo MQ-2 trực tiếp, luật ngưỡng (chưa có model)
```

**⚠️ Nguồn đã có nhưng CHƯA tích hợp vào huấn luyện:**
```
Telemetry trạm — chủ yếu trong nhà, không đại diện thời tiết ngoài trời; chỉ đối chiếu
```

---

### 1.3 Tiền xử lý & Feature

> **Quan trọng:** feature **không rò rỉ tương lai** (có test); chia dữ liệu **theo thời gian**, không xáo trộn.

- [x] **Xử lý chuỗi** ✅ → `ml/src/prep.py`
  - Resample về 1 giờ, nội suy khoảng trống ngắn, lọc ngoại lai median/MAD, trễ, cửa sổ trượt, sin/cos; z-score theo giờ, CUSUM
- [x] **Feature dự báo** ✅ → `ml/src/features.py`
  - Thời gian (giờ, ngày trong năm, sin/cos), lag t−1..t−6, rolling mean/std (1h/3h/6h), xu hướng áp suất 3h, điểm sương, chênh T − Td — **56 feature**, target Δ, seasonal naive
  - Chia: train 2021-01-02 → 2023-12-31, val 2024, test 2025
  - StandardScaler (scikit-learn) chỉ `fit` trên train, lưu cùng model (Ridge/Logistic)
- [x] **Feature edge (khí)** ✅ → `firmware/src/edge_ai.py` ≡ `ml/src/gas_edge.EDGE_FEATURES` (10): `gas_ppm`, `rs_r0`, `slope10` (d(ppm)/dt 10 s), `std30`, `dev_base` (lệch baseline động), `temp`, `dtemp_min`, `hum`, `dhum_min`, `lux_rel`
- [x] Cố định `seed` (42) cho mọi thành phần ngẫu nhiên (`random_state`, `torch.manual_seed`).

> **Trạng thái 1.3 (2026-11-19):** xong, có test không rò rỉ tương lai.

---

### 1.4 Thiết kế Mô hình

> **Quyết định (2026-11-14):** dùng thư viện học máy chuẩn để bảo đảm tính đúng đắn của dự báo và để số liệu so sánh mô
> hình đáng tin: **scikit-learn** 1.9.1 (Ridge, Logistic, Decision Tree, Random Forest, Isolation Forest, StandardScaler,
> độ đo, permutation importance), **LightGBM** 4.7.0 (GBDT — mô hình triển khai), **statsmodels** 0.15.0 (Holt-Winters),
> **PyTorch** 2.15 CPU (GRU, chỉ để so sánh). ~~Thư viện `ml/mlcore` tự viết~~ — đã xoá.

| Module `ml/src/` (gói `aiot_ml`)             | Nội dung                                                                                                                 |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `train_forecast.py`                          | So sánh Persistence, Seasonal naive, Holt-Winters, Ridge, GBDT, GRU (+ Logistic/GBDT cho mưa)                            |
| `forecast_infer.py`                          | Nạp model active trong registry cho forecast service                                                                     |
| `rain_ensemble.py`                           | Xác suất mưa từ Open-Meteo Ensemble; học θ + trọng số mô hình + IsotonicRegression bắt chước số Google; điều chỉnh YL-83 |
| `train_gas_edge.py`, `export_micropython.py` | Decision Tree / Random Forest (scikit-learn) → `firmware/src/gas_model.py` (bytes + `predict_proba()`)                   |
| `train_anomaly.py`                           | Isolation Forest (scikit-learn), z-score theo giờ, CUSUM                                                                 |
| `serialize.py`, `tracking.py`, `mdtable.py`  | joblib + JSON đầu mục (`model_ver`, hash dữ liệu, phiên bản thư viện); registry, log thí nghiệm; bảng Markdown           |

- [x] **Dự báo thời tiết (cloud)** — cấu hình `ml/configs/forecast.json`

  | Mô hình (thư viện)                                                | Vai trò                                                        | Trạng thái     |
  | ----------------------------------------------------------------- | -------------------------------------------------------------- | -------------- |
  | Persistence / Seasonal naive                                      | Baseline bắt buộc                                              | [x]            |
  | Holt-Winters (statsmodels)                                        | Baseline thống kê                                              | [x]            |
  | Ridge Regression trên lag features (scikit-learn)                 | Baseline tuyến tính                                            | [x]            |
  | **GBDT LightGBM (loss MSE)**                                      | **Mô hình chính** cho T/H, mỗi cặp target × horizon một model  | [x] triển khai |
  | **GBDT LightGBM (log-loss)**, so sánh với Logistic (scikit-learn) | Xác suất mưa 1h / 3h / 6h — **dự phòng** khi không có ensemble | [x] triển khai |
  | **Open-Meteo Ensemble + hiệu chỉnh theo Google + trạm**           | Xác suất mưa hiển thị từng giờ +1/+3/+6, miễn phí (1.7)        | [x] triển khai |
  | GRU (PyTorch)                                                     | So sánh với deep learning (không lưu, không triển khai)        | [x]            |

  - GBDT: `learning_rate = 0.05`, `max_depth = 6/5`, `num_leaves = 63/31`, `min_child_samples = 30/40`, subsample 0.8, colsample 0.8, `max_bin = 63`, early stopping 50 vòng trên val
  - Targets: `temp`, `hum` 1/3/6 h + mưa 1/3/6 h. ~~`pres_1/3/6h`~~ — bỏ (2026-11-13): trạm mặt đất không dự báo được trường khí áp
  - Re-train: `python -m aiot_ml.train_forecast` (`--force-promote` khi đổi định dạng)

- [x] **Cảnh báo khí (edge)** — ⚠️ pipeline xong, chưa có model
  - Decision Tree (Gini, `max_depth ≤ 6`) hoặc RF nhỏ (≤ 10 cây) trên 10 feature, **trọng số lớp** ưu tiên Recall cấp 2–3
  - Output = 4 cấp: 0 Normal, 1 Advisory, 2 Warning, 3 Danger
  - Metric Precision/Recall/F1 theo cấp, ma trận nhầm lẫn; so sánh rule / model / hybrid
  - Re-train: `python -m aiot_ml.train_gas_edge --data ml/data/raw/gas_labeled.csv` (`--data` bắt buộc)

- [x] **Phát hiện bất thường (cloud)** — đã cài, **không triển khai**
  - Isolation Forest (gas ppm + T/H) phát hiện rò rỉ chậm; z-score theo giờ để so sánh; CUSUM trên baseline `R0` phát hiện drift MQ-2 → đề xuất hiệu chuẩn lại
  - ~~Huấn luyện trên ≥ 3 tuần telemetry trạm~~ — bỏ: không có dữ liệu dài ngày. Alert service chỉ dùng Isolation Forest nếu có `gas_anomaly.json/.joblib` (không có) → leo thang chỉ theo xu hướng ppm

---

### 1.5 Huấn luyện Dự báo

- [x] `train_forecast.py` ✅ | `forecast_infer.py` ✅ | `registry.json` ✅ — **9 mô hình GBDT** active (`temp_*`, `hum_*`, `rain_*`) trong `ml/models/forecast/`

**Kết quả (tập test 2025, `docs/report/results_forecast.md`):**

| Đối tượng | Persistence | Holt-Winters | Ridge / Logistic | GBDT (triển khai) | GRU | Target | Status |
|-----------|-------------|--------------|------------------|-------------------|-----|--------|--------|
| MAE temp 1h (°C) | 0.593 | 0.369 | 0.348 | **0.299** | 0.306 | < 1.0 | ✅ |
| MAE temp 3h (°C) | 1.559 | 0.796 | 0.690 | 0.538 | **0.536** | — | ✅ |
| MAE temp 6h (°C) | 2.759 | 1.221 | 0.837 | **0.688** | 0.697 | — | ✅ |
| MAE hum 1h (%RH) | 2.968 | 2.206 | 2.045 | **1.870** | 1.894 | < 5 | ✅ |
| MAE hum 3h (%RH) | 7.541 | 4.547 | 3.822 | 3.242 | **3.240** | — | ✅ |
| MAE hum 6h (%RH) | 13.210 | 6.682 | 4.515 | **3.954** | 4.075 | — | ✅ |
| F1 mưa 1h / 3h / 6h | 0.826 / 0.783 / 0.723 | — | 0.828 / 0.827 / 0.839 | **0.830 / 0.833 / 0.851** | — | 3h > 0.75 | ✅ |

- GBDT tốt nhất 4/6 cặp T/H và 3/3 tầm mưa; GRU nhỉnh hơn 0.002 ở tầm 3h; mọi mô hình học vượt persistence.
- Thời gian: temp_1h 0.4 s, 261 cây, suy luận 1.7 µs/mẫu; GRU (6 đầu ra chung) 24 s.

**Vấn đề đã chẩn đoán (2026-11-19):** F1 mưa cao nhưng xác suất mưa lệch thực tế. Nhãn ≥ 0,1 mm/h có ở 35 % số giờ; GBDT mưa chủ yếu học persistence (`is_rain` + `hours_since_rain` = 52 % gain; F1 1h 0,830 so với 0,826). Đo thật 15:00 19/11: LightGBM 72/65/93 %, Open-Meteo 51/51/74 %; giờ 17–21 h 20/11 Open-Meteo 100 % so với Google 70/70/60/40/50 % (lệch 30–60 điểm) ⇒ không mô hình nào học từ Open-Meteo bám được Google ±10.

**Fix:** xác suất mưa hiển thị chuyển sang Open-Meteo Ensemble hiệu chỉnh theo Google (1.7); LightGBM mưa giữ làm dự phòng, lưu `rain_ml` để so sánh.

```bash
python -m aiot_ml.train_forecast    # ghi registry + experiments.csv, chỉ thăng cấp khi tốt hơn
```

---

### 1.6 Đánh giá & Phân tích

- [x] Metric MAE/RMSE (hồi quy), F1/ROC-AUC/Brier (mưa) → `docs/report/results_forecast.md`, `ml/experiments/forecast_results.json` ✅
- [x] Gain importance (LightGBM) + permutation importance (scikit-learn) → bảng trong `docs/report/results_forecast.md` ✅
- ~~Hình biểu đồ kết quả (matplotlib)~~ — bỏ 2026-11-19: báo cáo chỉ dùng bảng số liệu; hình chỉ còn sơ đồ draw.io
- [x] Log thí nghiệm `ml/experiments/experiments.csv` (tham số, metric, thời gian, `seed`) ✅
- [x] Bảng sai số dự báo so với số đo trạm (MAE, lệch TB theo biến × tầm) trên dashboard trang Dự báo ✅ — [ ] ⚙ chạy đêm ngoài trời (2.5)
- [ ] ⚙ Bảng metric cảnh báo rule / model / hybrid — chờ dữ liệu khí thật → báo cáo §5.2
- [ ] ⚙ Bảng xác suất mưa so với Google (số giờ, lệch TB, % giờ lệch ≤ 10 trước/sau khi học) — chờ ≥ 40 giờ số Google → báo cáo §5.1

---

### 1.7 Xác suất mưa miễn phí (Type 2) ⚠️ Chờ số Google

> **Yêu cầu (2026-11-19):** xác suất mưa hiển thị **không lệch quá 10 điểm %** so với Google Search ("dự báo thời tiết tại VKU", cùng giờ); **không tốn tiền**. ~~Google Maps Platform Weather API~~ — bỏ (cần bật billing), đã xoá `google_weather.py` và `GOOGLE_WEATHER_API_KEY`. Không scrape Google.

- [x] **`ml/src/rain_ensemble.py`** ✅
  - Xác suất mưa của một mô hình ở ngưỡng θ = tỉ lệ phương án có lượng mưa giờ đó ≥ θ (bỏ thành viên thiếu số liệu)
  - Đặc trưng: tỉ lệ ≥ 0,1 / 0,25 / 0,5 / 1 / 2 / 3 mm của từng mô hình (ECMWF, GFS, ICON)
  - Mặc định (chưa học): gộp 3 mô hình, θ = 1 mm
  - `fit_calibration`: tìm kiếm lưới θ + trọng số {0; 0,5; 1} từng mô hình (chấm MAE sau khớp tuyến tính) + `IsotonicRegression` chỉ giữ nếu giảm MAE trên 30 % dữ liệu mới nhất; cần ≥ 40 giờ → `rain_calib.json`
  - Điều chỉnh trạm: YL-83 đang báo mưa (số đo ≤ 15 phút) → +10 / +5 / 0 điểm ở +1/+3/+6 h, tối đa 10
- [x] **So nguồn miễn phí với 5 giờ Google (20/11, 17–21 h, Google 70/70/60/40/50):**

  | Cách tính | Lệch TB (điểm) |
  |-----------|----------------|
  | Open-Meteo ≥ 0,1 mm (cách cũ) | 42 |
  | Ensemble ICON ≥ 0,5 mm | 15 |
  | **Gộp 3 mô hình ≥ 1 mm (mặc định)** | **12** |
  | Ensemble ECMWF ≥ 2 mm | 9 |

  MET Norway và các mô hình JMA/KMA/CMA không có xác suất mưa ở VKU. Chạy thật: lấy được 51 + 31 + 40 phương án; mặc định 65/64/63/65/70 %.
- [x] Backend: bảng `google_rain_obs`, `POST/GET /api/rain/google`, `POST /api/rain/calibrate`; forecast lưu `rain_prob` (hiển thị), `rain_ens`, `rain_ml`; MQTT `forecast` có `rain_source` (`ensemble`/`lightgbm`); không có ensemble → LightGBM; không có cả hai → bỏ lượt
- [x] Cấu hình: `USE_RAIN_ENSEMBLE` (mặc định bật), `RAIN_CALIB_PATH` (Docker: volume `backend-data` → `/app/data/rain_calib.json`, không mất khi build lại), `RAIN_MAX_DEV_PCT = 10`, `STATION_FRESH_MIN = 15`
- [ ] ⚙ Nhập số Google ≥ 40 giờ (2–3 lần/ngày × 5 ô) → bấm **Học lại hiệu chỉnh** → ghi kết quả vào báo cáo §5.1
  - **Pass criterion:** % số giờ lệch ≤ 10 điểm trên số Google đã nhập (đo trung thực, **không bảo đảm 100 %**); học lại khi chuyển mùa

---

### 1.8 Fusion — Edge AI Cảnh báo Khí/Khói

- [x] **Rule engine** `firmware/src/alert.py` ✅ — 4 cấp (ngưỡng mặc định trong `config.py`, chỉnh qua topic `config`):

  | Cấp | Tên                | Điều kiện (LPG, ppm)                                                                 | Hành động tại edge                                       |
  | --- | ------------------ | ------------------------------------------------------------------------------------ | -------------------------------------------------------- |
  | 0   | Normal             | ppm < 300 và slope thấp                                                              | LED xanh sáng                                            |
  | 1   | Advisory (Chú ý)   | 300–1000 ppm **hoặc** slope ≥ `slope1` (15) **hoặc** model score > 0.5               | LED xanh nhấp nháy (không có LED vàng), gửi alert        |
  | 2   | Warning (Cảnh báo) | 1000–2000 ppm **hoặc** score > 0.75 kéo dài                                          | LED đỏ nhấp nháy, còi ngắt quãng (relay/quạt: không lắp) |
  | 3   | Danger (Nguy hiểm) | > 2000 ppm (≈ 10 % LEL của LPG) **hoặc** cấp 2 kèm nhiệt độ tăng nhanh (> 1 °C/phút) | LED đỏ sáng liên tục, còi liên tục                       |

  - **Hysteresis** 15 %, **debounce** lên 3 / xuống 5 mẫu (cấp 3 lên ngay)
  - **Fusion:** `level = max(rule_level, model_level)`; model không được hạ cấp do rule đưa ra. Chế độ `rule`/`model`/`hybrid` chọn qua `config`
  - **Priority (fixed): Danger > Warning > Advisory > Normal**; cấp ≥ 2 luôn chiếm màn TFT
- [x] Phát hiện **lỗi cảm biến** MQ-2: đứng yên (stuck), mất kết nối, ADC bão hoà → alert `sensor_fault` ✅
- [x] Tắt còi 5 phút bằng lệnh `mute` (không có nút vật lý), vẫn giữ cấp và LED; cấp tăng thêm thì còi kêu lại ✅
- [x] Publish `alert` mỗi khi đổi cấp, kèm `cause`, `rule_level`, `model_level`, `edge_latency_ms`; `test_alarm` gửi `type: test` (không Telegram/Email); `escalate` từ cloud nâng cấp ✅
- [x] Kiểm chứng trên trạm thật (2026-11-16): xịt gas bật lửa 2868 mV (Rs/R0 0,37 ≈ 5170 ppm) → cấp 3 (đèn đỏ + còi), hạ dần về 0 khi gas tan ✅
- [ ] ⚙ Model cây: chưa có (`AVAILABLE = False`) → edge tự chạy rule

---

### 1.9 Tối ưu Model Edge

- [x] Model edge float32, mảng node đóng gói `bytes`, `predict_proba()` duyệt cây thuần Python ✅
  - Giới hạn: Decision Tree `max_depth ≤ 6` hoặc RF ≤ 10 cây → vừa RAM ESP32
- [x] Firmware biên dịch `.mpy` (mpy-cross) để giảm RAM/thời gian nạp ✅
- [ ] ⚙ Đo kích thước model (kB), RAM và µs suy luận trên ESP32: `python -m mpremote connect COM3 run firmware/bench_device.py` (khi đã có model) → báo cáo §5.5

---

### 1.10 Export & Vòng đời Mô hình (MLOps tối giản)

- [x] Script `train_*.py` chạy bằng CLI (`python -m aiot_ml.train_forecast`…), cấu hình JSON ✅
- [x] Model cloud: `ml/models/forecast/*.joblib` + `*.json` (model card), `ml/models/registry.json` (đường dẫn POSIX để backend Linux nạp được) ✅
- [x] Chỉ thăng cấp model mới khi tốt hơn trên tập test (`tracking.py`). ~~Lịch huấn luyện lại hằng tuần~~ — bỏ (không thu dữ liệu dài ngày) ✅
- [x] Model edge: `ml/src/export_micropython.py` → `firmware/src/gas_model.py` (bytes + `predict_proba()`) ✅
- [x] Đẩy ngưỡng qua MQTT `config`, model edge qua OTA, ghi `model_ver` ✅
- [x] Hiệu chỉnh mưa: `rain_calib.json` (`version` = `ens-YYYYmmddHHMM`, θ, trọng số, isotonic, metrics) ✅

---

### 1.11 Golden Reference / Kiểm chứng tương đương

- [x] `gas_model.py` sinh ra (mô phỏng float32) khớp `predict_proba()` của scikit-learn **100 %** và biên dịch được bằng mpy-cross (`ml/tests/test_export_micropython.py`) ✅
- [x] Logic edge firmware ≡ `ml/src/gas_edge.py` (`ml/tests/test_edge_parity.py`) ✅
- [x] Công thức Holt-Winters h bước trùng `forecast()` của statsmodels; tốt hơn persistence trên chuỗi mùa ✅
- [x] Lưu/nạp joblib giữ nguyên dự đoán (LightGBM, Ridge) ✅
- [x] Ensemble mưa: học hiệu chỉnh tìm lại đúng nguồn + ngưỡng của bài toán có đáp án (`ml/tests/test_rain_ensemble.py`) ✅
- [ ] ⚙ Sau khi có dữ liệu khí: chạy lại `train_gas_edge` → kiểm tra khớp → nạp `gas_model.py` lên board

---

## PHASE 2 – PHẦN CỨNG, FIRMWARE, CLOUD & TRIỂN KHAI

### 2.1 Kiến trúc Hệ thống

Sơ đồ khối chính thức: `docs/architecture/system_block_diagram.drawio`; Input – Xử lý – Output: `docs/architecture/ipo.md`;
các trang 2–3 của sơ đồ khối là ERD và luồng cảnh báo (giải thích: `docs/architecture/diagrams.md`, `sequences.md`).

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
│   ├─► Forecast service: LightGBM + Ensemble, 10 phút/lần      │
│   └─► Publisher: cmd / config / forecast xuống edge, OTA      │
│ REST API (FastAPI, JWT) + WebSocket ─► Dashboard (Streamlit)  │
│                                     └► Grafana (tuỳ chọn)     │
└───────────────────────────────────────────────────────────────┘
```

| Chức năng                  | Edge (ESP32)          | Cloud (Python)                 |
| -------------------------- | --------------------- | ------------------------------ |
| Lọc nhiễu, tính feature    | ✅                    | —                              |
| Cảnh báo khí/khói tức thì  | ✅ (quyết định chính) | Xác nhận, leo thang, thông báo |
| Hoạt động khi mất mạng     | ✅ (đệm offline)      | —                              |
| Dự báo 1h/3h/6h            | —                     | ✅ (ML + ensemble)             |
| Huấn luyện mô hình         | —                     | ✅                             |
| Lưu trữ dài hạn, dashboard | —                     | ✅                             |
| Cập nhật ngưỡng / model    | Nhận                  | Gửi (MQTT `config`, OTA)       |

**Địa điểm triển khai:**

| Thông số | Giá trị                                                                                                                                                 | Dùng cho                                                       |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| Vị trí   | Trường ĐH CNTT & TT Việt – Hàn (VKU), 470 Trần Đại Nghĩa, P. Hoà Quý, Q. Ngũ Hành Sơn, Đà Nẵng                                                          | —                                                              |
| Toạ độ   | ≈ **15.975°N, 108.253°E** (xác nhận lại trên Google Maps tại đúng chỗ đặt trạm)                                                                         | Tải Open-Meteo, tính góc mặt trời và lux khi trời quang        |
| Độ cao   | ≈ 5–10 m so với mực nước biển (đang dùng **8 m**)                                                                                                       | Quy áp suất về mực nước biển                                   |
| Múi giờ  | `Asia/Ho_Chi_Minh` (UTC+7)                                                                                                                              | NTP, Open-Meteo, feature giờ trong ngày                        |
| Khí hậu  | Nhiệt đới gió mùa. **Mùa mưa tháng 9–12** (cao điểm tháng 10–11, có bão và áp thấp nhiệt đới), mùa khô tháng 1–8. Gần biển, độ ẩm trung bình khoảng 80% | Tập test phải bao trọn mùa mưa. Nhãn mưa mất cân bằng theo mùa |

- [x] Giá trị đã đặt trong `firmware/src/config.py` (`STATION_LAT = 15.975`, `STATION_LON = 108.253`, `STATION_ALT_M = 8.0`, `TZ_HOURS = 7`) và backend (`STATION_LAT/LON/ALT_M/TZ` trong `backend/app/core/config.py`, ghi đè được bằng `.env`).

**Cấu trúc repo:**
```
final/
├── task.md                     # kế hoạch + trạng thái (file này)
├── PROGRESS.md                 # nhật ký tiến độ, mục CÒN LẠI
├── README.md                   # cài đặt ≤ 10 bước, kiểm thử, kết quả chính
├── docker-compose.yml          # mosquitto, db (TimescaleDB), backend, dashboard, grafana (profile monitoring)
├── .env                        # tuỳ chọn, gitignore — ghi đè mặc định (mọi biến có mặc định)
├── .gitignore, .gitattributes, .dockerignore, .streamlit/config.toml
├── docs/
│   ├── hardware/               # gen_wiring_drawio.py → wiring.drawio, wiring-1/2.png
│   ├── architecture/           # mqtt.md, ipo.md, diagrams.md, sequences.md; system_block_diagram.drawio (3 trang) → -1/2/3.png
│   └── report/                 # bao_cao.md/.docx (phụ lục B = kịch bản demo), results_*.md, VKU-SLIDE.pptx
├── firmware/                   # MicroPython cho ESP32 (chỉ Python)
│   ├── README.md               # nạp MicroPython, credentials.py, deploy, checklist trước khi cấp điện
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
│   │   ├── db/ (models.py, session.py, migrations/versions/0001_initial.py, 0002_drop_nowcasts.py, 0003_google_rain_obs.py)
│   │   ├── mqtt/ (ingest.py, publisher.py)
│   │   ├── services/ (alert_service.py, forecast_service.py, notifier.py, hub.py)  # hub = WebSocket broadcast
│   │   ├── api/ (routes.py, ws.py)
│   │   └── schemas/payloads.py
│   └── tests/                  # 24 test (gồm integration với Mosquitto thật)
├── ml/                         # package cài bằng `pip install -e ml` → `aiot_ml`
│   ├── pyproject.toml, requirements.txt   # numpy, pandas, scikit-learn, lightgbm, statsmodels, joblib (+ torch tuỳ chọn)
│   ├── configs/forecast.json
│   ├── data/ (external/vku_hourly_2021_2025.csv, raw/, processed/)   # raw/processed gitignore
│   ├── src/ (= aiot_ml)
│   │   ├── config.py, fetch_open_meteo.py, prep.py, features.py, forecast_infer.py
│   │   ├── train_forecast.py, train_gas_edge.py, train_anomaly.py, gas_edge.py, export_micropython.py
│   │   ├── rain_ensemble.py    # xác suất mưa từ Open-Meteo Ensemble (miễn phí) + hiệu chỉnh theo số Google + trạm
│   │   └── serialize.py (joblib + JSON), tracking.py (registry + log thí nghiệm), mdtable.py (bảng Markdown)
│   ├── models/ (forecast/*.joblib + *.json, registry.json)
│   ├── experiments/ (experiments.csv, forecast_results.json, train_forecast.log)
│   └── tests/                  # 31 test (lưu/nạp, Holt-Winters ≡ statsmodels, khớp MicroPython ↔ scikit-learn, ensemble mưa)
├── dashboard/                  # Streamlit: app.py (6 trang), theme.py (CSS/HTML), Dockerfile, tests/ (9 test, fixture từ trạm thật)
├── grafana/                    # datasource + dashboard provision sẵn (vku_aiot.json)
└── tools/
    ├── label_logger.py         # ghi dữ liệu khí đo thật có nhãn
    ├── load_test.py            # kiểm thử tải N thiết bị (tự xoá thiết bị tạm)
    ├── render_drawio.py, browser_cdp.py   # draw.io → PNG (Edge/Chrome headless)
    └── md_to_docx.py           # bao_cao.md → .docx (MS Word)
```
(Không có `ml/notebooks/`, `ml/src/export_edge_model.py`, `evaluate.py` như kế hoạch ban đầu: xuất model nằm trong `train_gas_edge.py`, đánh giá nằm trong các script `train_*.py`.)

---

### 2.2 Hiện thực

#### 2.2.1 Phần cứng
> ⚠️ **Ghi chú phần cứng:** danh sách ban đầu (YL-83, BH1750, DHT22, BMP280) không có cảm biến khí → thêm **MQ-2** (LPG, propane, H₂, CH₄, khói; tuỳ chọn MQ-5/MQ-135 là hướng phát triển). Mọi chân analog nằm trên **ADC1** (GPIO32–39) vì ADC2 không dùng được khi Wi-Fi bật. Chỉ dùng **một** BH1750 (`0x23`; module thứ hai đổi ADDR → `0x5C` hoặc để dự phòng). Hệ thống chỉ là **nguyên mẫu học thuật**, không thay thế thiết bị báo cháy/báo gas đã chứng nhận (ghi trong README và báo cáo).

**BOM:**

| #   | Linh kiện                         | Chức năng                                                        | Giao tiếp           | Ghi chú                                                                                       |
| --- | --------------------------------- | ---------------------------------------------------------------- | ------------------- | --------------------------------------------------------------------------------------------- |
| 1   | ESP32 DevKit V1 (ESP-WROOM-32)    | Vi điều khiển, Wi-Fi, Edge AI                                    | —                   | Có sẵn                                                                                        |
| 2   | DHT22 (AM2302)                    | Nhiệt độ, độ ẩm                                                  | 1-Wire (GPIO)       | Có sẵn. Đọc tối đa 1 lần / 2 giây                                                             |
| 3   | BMP280                            | Áp suất, nhiệt độ                                                | I2C `0x76`          | Có sẵn                                                                                        |
| 4   | BH1750                            | Cường độ ánh sáng (lux)                                          | I2C `0x23`          | Có sẵn                                                                                        |
| 5   | YL-83 (+ module LM393)            | Phát hiện / mức độ mưa                                           | Analog + Digital    | Có sẵn. Cấp nguồn từ GPIO18 chỉ khi đọc                                                       |
| 6   | **MQ-2**                          | Khí dễ cháy, khói                                                | Analog + Digital    | Đã đo thật: sạch ≈ 400 mV, gas bật lửa tới 2868 mV                                            |
| 7   | Buzzer active 2 chân              | Còi cảnh báo (nối thẳng GPIO, `BUZZER_ACTIVE_LOW = False`)       | GPIO                | Có sẵn                                                                                        |
| 8   | LED xanh / đỏ (+ điện trở 220Ω)   | Đèn báo cấp cảnh báo (không có LED vàng: cấp 1 = xanh nhấp nháy) | GPIO                | `HAS_LED_YELLOW = False`                                                                      |
| 9   | Màn hình TFT 1.8" ST7735S 128×160 | Hiển thị tại chỗ (màu)                                           | SPI (CS/A0/SDA/SCK) | Có sẵn. Driver tự viết `st7735.py`                                                            |
| 10  | ~~Relay 5V hoặc quạt nhỏ~~        | Không dùng (nhóm không có) — hướng phát triển                    | GPIO                | `HAS_RELAY = False` (code vẫn giữ `PIN_RELAY = 23`)                                           |
| 11  | ~~Nút nhấn~~                      | Không dùng — tắt còi bằng lệnh `mute` trên dashboard             | —                   | Đã xoá code đọc GPIO13                                                                        |
| 12  | ~~Điện trở 10kΩ + 20kΩ~~          | Bỏ (2026-11-16) — MQ-2 AO nối thẳng GPIO32                       | —                   | `MQ2_DIVIDER = 1.0`                                                                           |
| 13  | Nguồn 5V/2A, breadboard, dây      | Cấp nguồn                                                        | —                   | MQ-2 tiêu thụ ≈ 150 mA. ⚙ Cấp qua USB làm board tự reset khi bật Wi-Fi → dùng 5 V/2 A vào VIN |
| 14  | Hộp nhựa có khe thông gió         | Đóng gói trạm                                                    | —                   | YL-83 đặt ngoài trời, DHT22 đặt trong vỏ che nắng                                             |

**Sơ đồ chân** (theo `firmware/src/config.py`; checklist cấp điện ở `firmware/README.md`):

| Thiết bị                 | Chân thiết bị               | Chân ESP32                                        |
| ------------------------ | --------------------------- | ------------------------------------------------- |
| I2C bus (BMP280, BH1750) | SDA / SCL                   | GPIO21 / GPIO22                                   |
| DHT22                    | DATA                        | GPIO4 (pull-up 10kΩ)                              |
| YL-83                    | VCC / AO / DO               | GPIO18 (cấp nguồn khi đọc) / GPIO34 / GPIO35      |
| MQ-2                     | AO (nối thẳng) / DO         | GPIO32 / GPIO33                                   |
| Buzzer                   | +                           | GPIO25                                            |
| LED xanh / đỏ            | Anode                       | GPIO26 / GPIO14                                   |
| TFT ST7735S              | CS / A0 / SDA / SCK / RESET | GPIO5 / GPIO16 (RX2) / GPIO17 (TX2) / GPIO19 / EN |

- [x] Sơ đồ đấu dây draw.io (thay Fritzing/KiCad): `docs/hardware/wiring.drawio` (2 trang: cảm biến / cảnh báo), sinh bằng `docs/hardware/gen_wiring_drawio.py` (sau đó sửa tay tại chỗ, không sinh lại đè), xuất `wiring-1.png`, `wiring-2.png`; checklist trước khi cấp điện ở `firmware/README.md`.
- [x] MQ-2 AO **nối thẳng GPIO32**, bỏ cầu phân áp 10 kΩ/20 kΩ (2026-11-16, `MQ2_DIVIDER = 1.0`). ADC 11 dB bão hoà ≈ 3,3 V; AO > 3,3 V khi nồng độ rất cao → `FAULT_SATURATED`. Đã đo (sau khi sửa dây AO → GPIO32): sạch ≈ 360–440 mV, gas bật lửa 2868 mV (≈ 5170 ppm) → cấp 3.
- [x] Quét I2C tự động lúc khởi động (log `[SENS] I2C [...] BMP280:1 BH1750:1`). [ ] ⚙ Chụp ảnh màn TFT hiển thị đúng màu/hướng.
- [x] Hiệu chuẩn MQ-2 có sẵn trong firmware: lệnh `calibrate` đo `R0` trong không khí sạch (`Rs/R0 ≈ 9.83`), `ppm = 574.25 · (Rs/R0)^−2.222`. [ ] ⚙ Chạy sau burn-in, đo lại `MQ2_RL_KOHM` trên module.
- [x] Hiệu chuẩn YL-83 theo số đo thật (2026-11-16, sau khi sửa dây module LM393 — trước đó cắm sai → AO kẹt ≈ 1,2 V cả khô lẫn ướt): tấm khô 3134 mV (trần ADC), vài giọt nước 2761–2964 mV → khô ≥ 3130, mưa phùn 2600–3129, mưa vừa 2000–2599, mưa to < 2000 mV; giữ mức mưa 3 lần đọc. [ ] ⚙ Thử ướt nửa tấm / cả tấm để chốt mưa vừa/to, ghi bảng hiệu chuẩn vào báo cáo §3.3.
- [ ] ⚙ Test riêng từng cảm biến và ghi kết quả vào báo cáo.
- [ ] ⚙ **Burn-in MQ-2 24–48 giờ** trước khi hiệu chuẩn.
- [ ] ⚙ So sánh nhiệt độ DHT22 và BMP280 (dashboard có cả hai trường), đối chiếu nhiệt kế tham chiếu nếu có.
- [ ] ⚙ Nguồn 5 V/2 A vào VIN (cấp USB làm board reset khi bật Wi-Fi và mất MQTT ≈ 15–20 s sau mỗi lần báo động cấp 3).
- [ ] ⚙ Lắp ráp vào hộp, chụp ảnh thực tế cho báo cáo.

#### 2.2.2 Firmware — Nền tảng & Truyền thông
**Nền tảng:** **MicroPython** (bản ESP32_GENERIC chính thức, nạp bằng `esptool`). Chỉ dùng module có sẵn của MicroPython (`machine`,
`network`, `dht`, `framebuf`, `ntptime`, `_thread`, `json`, `socket`); driver BMP280, BH1750, ST7735 và MQTT client **tự viết bằng
Python**. Nạp code bằng `python firmware/deploy.py --port COM3` (mpremote) hoặc Thonny.

- [x] `deploy.py`: biên dịch `.mpy` (mpy-cross) + chép `firmware/src/` lên board; xem log bằng `python -m mpremote connect COM3 repl`.
- [x] `config.py` (pin, ngưỡng, chu kỳ) tách khỏi `credentials.py` (Wi-Fi/MQTT, gitignore).
- [x] Wi-Fi tự kết nối lại; MQTT keep-alive 15 s, backoff 2 → 30 s. ~~WiFiManager/captive portal~~ không làm (tuỳ chọn).
- [x] NTP (`pool.ntp.org`, `time.google.com`, `vn.pool.ntp.org`, GMT+7), khởi động lại SNTP khi Wi-Fi vừa lên (có giờ sau ≈ 20 s).
- [x] Watchdog `machine.WDT` 30 s; luồng mạng không báo nhịp > 60 s (`NET_STALL_MS`) thì ngừng feed WDT → board tự reset.
- [x] Hai luồng: **luồng chính** đọc cảm biến 1 s (DHT22 2 s, YL-83 10 s), feature, rule + model, còi/LED, màn hình — không phụ thuộc mạng; **luồng mạng** (`_thread`, `net.py`): Wi-Fi, NTP, MQTT, đệm offline, OTA. Giao tiếp qua hàng đợi có khoá (`_thread.allocate_lock`, `OUTBOX_MAX = 20`).
  - ⚠️ **Rủi ro heap IDF:** heap GC lớn làm Wi-Fi thiếu bộ nhớ → giữ `GC_THRESHOLD` / stack luồng 8 KB, theo dõi `idf_free_heap`
- [x] Telemetry 5 s (`TELEMETRY_PERIOD_MS = 5000`, cấu hình được qua `telemetry_ms`), 1 s khi đang có cảnh báo.
- [x] Đệm offline: file trên flash (LittleFS), vòng đệm 2000 bản ghi, gửi bù khi kết nối lại (tối đa 200 bản/lượt); `seq` lưu `/seq.txt` để chống trùng.
- [x] Subscribe `cmd`, `config`, `forecast`; kiểm tra hợp lệ (th1 < th2 < th3, dải giá trị), lưu `/config.json`, gửi `ack` (`ok:false` khi từ chối).
- [x] `status` mỗi 60 s: RSSI, uptime, free heap, số lần reconnect, bản ghi chờ gửi, fw, model_ver, `inference_us`.
- [x] OTA qua HTTP: `cmd: ota` + `url` manifest (`ota.py`, gói tạo bằng `deploy.py`); API `POST /api/devices/{id}/cmd {"cmd":"ota","url":...}`. [ ] ⚙ Thử OTA trên board.

#### 2.2.3 Firmware — Đọc & Tiền xử lý Cảm biến
- [x] Driver từng cảm biến, xử lý lỗi (NaN, timeout I2C) và cờ `sensor_ok` (dht/bmp/bh/rain/gas).
- [x] Lọc median (cửa sổ 5) rồi EWMA.
- [x] ADC: `ADC.read_uv()` (hiệu chỉnh eFuse), suy giảm 11 dB, trung bình 16 mẫu.
- [x] MQ-2: `Rs = RL·(Vc − Vout)/Vout`, `Rs/R0`, ppm; warm-up 60 s (`warming_up`, chưa cảnh báo).
- [x] YL-83: ADC → `rain_level` 0–3, cấp nguồn qua GPIO18 chỉ khi đọc.
- [x] Áp suất quy về mực nước biển (`pressure_msl`, độ cao 8 m), so được với `pressure_msl` của Open-Meteo.
- [x] Đại lượng dẫn xuất: điểm sương, heat index.

#### 2.2.4 Firmware — Hiển thị cục bộ (TFT 1.8" ST7735, `display.py`)
- [x] Trang 1: T / H / P / Lux / Rain. Trang 2: Gas ppm, cấp cảnh báo. Trang 3: dự báo nhận từ cloud (`summary` của topic `forecast`).
- [x] Trạng thái Wi-Fi/MQTT ở dòng tiêu đề, đồng hồ + fw + số trang ở dòng cuối; cấp ≥ 2 luôn ưu tiên trang cảnh báo.

#### 2.2.5 MQTT (chi tiết và payload chuẩn: `docs/architecture/mqtt.md`)
Tiền tố: `vku/aiot/{device_id}/...` (`device_id = station01`). Broker trên máy phát triển: cổng host `11883`
(`MQTT_HOST_PORT` trong `.env`, vì Mosquitto Windows chiếm 1883); trong Docker vẫn là 1883.

| Topic           | Chiều        | QoS     | Retain | Nội dung                                                       |
| --------------- | ------------ | ------- | ------ | -------------------------------------------------------------- |
| `.../telemetry` | Edge → Cloud | 0*      | ❌     | Dữ liệu cảm biến + kết quả edge AI, 5 s (1 s khi cấp ≥ 1)      |
| `.../alert`     | Edge → Cloud | 0*      | ❌     | Sự kiện khí/khói (khi đổi cấp), `sensor_fault`, `test`         |
| `.../status`    | Edge → Cloud | 1 (LWT) | ✅     | `online` + RSSI, uptime, heap; LWT `{"state":"offline"}`       |
| `.../forecast`  | Cloud → Edge | 1       | ✅     | Dự báo 1h/3h/6h + `summary` cho màn TFT + `rain_source`        |
| `.../cmd`       | Cloud → Edge | 1       | ❌     | `mute`, `test_alarm`, `calibrate`, `reboot`, `escalate`, `ota` |
| `.../config`    | Cloud → Edge | 1       | ✅     | Ngưỡng, chu kỳ gửi, chế độ edge, R0, `version`                 |
| `.../ack`       | Edge → Cloud | 0*      | ❌     | Xác nhận đã nhận/áp dụng cmd/config                            |

\* MQTT client tự viết trên ESP32 chỉ publish QoS 0; "ít nhất một lần" bảo đảm ở tầng ứng dụng bằng `seq` + đệm offline +
gửi bù, backend chống trùng theo `(device_id, ts, seq)`. Backend và `tools/load_test.py` dùng QoS 1 thật.
~~`.../nowcast`~~ đã bỏ (2026-11-13).

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

- [x] Mosquitto (Docker, `eclipse-mosquitto:2.0.20`), xác thực username/password, ACL theo thiết bị (thiết bị chỉ ghi topic của chính nó).
- [x] LWT: topic `.../status`, payload `{"state":"offline"}`, retain.
- [x] TLS cổng 8883: `broker/mosquitto/gen_certs.py`, firmware đặt `MQTT_CA_FILE`/`MQTT_PORT = 8883` trong `credentials.py`. [ ] ⚙ Chạy thử TLS trên board.
- [x] ~~`tools/simulator.py`~~ — đã bỏ (2026-11-11): đề tài chỉ dùng số liệu đo thật.

#### 2.2.6 Backend Cloud (`backend/`)
**Stack:** Python 3.11+, FastAPI, paho-mqtt, SQLAlchemy 2 + Alembic, PostgreSQL 16 + TimescaleDB 2.17 (Docker) hoặc SQLite (dev), Pydantic v2, APScheduler, gọi trực tiếp HTTP API của Telegram, SMTP, Docker Compose.

**Cơ sở dữ liệu** (`app/db/models.py`):
- [x] `devices` (id, name, location, lat, lon, altitude, fw, last_seen, status…).
- [x] `telemetry` (hypertable theo `ts`): toàn bộ trường payload + `extra` (giá trị bị loại).
- [x] `alerts` (id, device_id, ts, type, level, prev_level, cause, source = edge/cloud, acknowledged_by, ack_ts…).
- [x] `forecasts` (device_id, created_at, horizon, target, value, lower, upper, model_ver, source); target mưa: `rain_prob` (hiển thị), `rain_ens`, `rain_ml` (so sánh).
- [x] `google_rain_obs` (entered_at, valid_at, google_pct, features, entered_by): số Google nhập tay + đặc trưng ensemble chụp lúc nhập.
- [x] `device_configs`, `commands`, `model_registry`, `notifications`.
- [x] Alembic: `0001_initial` (bảng + hypertable + continuous aggregate 1 phút / 10 phút / 1 giờ + retention dữ liệu thô 90 ngày trên TimescaleDB), `0002_drop_nowcasts` (bỏ bảng `nowcasts`), `0003_google_rain_obs`.

**Ingestion** (`app/mqtt/ingest.py`):
- [x] Subscribe `vku/aiot/+/telemetry|alert|status|ack`.
- [x] Validate Pydantic, loại giá trị ngoài dải vật lý (T −10..60 °C, P 900..1100 hPa, RH 0..100 %…) → lưu vào `extra.rejected`.
- [x] Chống trùng theo `(device_id, ts, seq)`; bỏ qua bản tin rỗng (xoá retained) thay vì tạo thiết bị ma.
- [x] Ghi DB theo lô, đẩy WebSocket (`services/hub.py`).
- [x] Cập nhật `last_seen`; > 60 s không có dữ liệu hoặc nhận LWT → offline + alert `device_offline`.

**Alert service** (`app/services/alert_service.py`):
- [x] Lưu alert từ edge + **xác nhận/leo thang** ở cloud (chạy mỗi 30 s): xu hướng ppm 10 phút so với 60 phút trước; cloud leo thang thì gửi `cmd: escalate` xuống edge.
- [x] Thông báo theo cấp: cấp 1 chỉ ghi log + dashboard; cấp 2 Telegram; cấp 3 Telegram + Email, nhắc lại tới khi ack (`test` không gửi, không nhắc).
- [x] Cooldown chống spam, bảng `notifications` lưu lịch sử gửi.
- [x] Ack từ dashboard (`POST /api/alerts/{id}/ack`) và nút inline "Đã xử lý" trên Telegram.

**Forecast service** (`app/services/forecast_service.py` + `ml/src/forecast_infer.py`):
- [x] APScheduler mỗi 10 phút (`FORECAST_EVERY_MIN`): lấy dữ liệu, tạo feature, gọi model, lưu `forecasts`, publish `.../forecast`.
- [x] Nạp model active từ `ml/models/registry.json` (joblib + JSON), suy luận bằng LightGBM; backend cài `pip install -e ml` (image có `libgomp1`).
- [x] Đầu vào dự báo: **luôn là quan trắc Open-Meteo** gần nhất tại toạ độ trạm; số đo trạm chỉ để đối chiếu. Khoảng tin cậy; kẹp độ ẩm [0, 100].
- [x] Targets: `temp`, `hum` (1/3/6 h) + xác suất mưa 1/3/6 h — **không** dự báo áp suất. Mưa: 1.7.
- [x] Tin tóm tắt thời tiết 6h sáng (cron).

**REST API & WebSocket** (`app/api/routes.py`, `app/api/ws.py`, tiền tố `/api`):
- [x] `POST /api/auth/token` (JWT), `GET /api/health`
- [x] `GET /api/devices`, `GET /api/devices/{id}`, `DELETE /api/devices/{id}`
- [x] `PUT /api/devices/{id}/config` (publish `config`), `GET /api/devices/{id}/configs`
- [x] `POST /api/devices/{id}/cmd` (`mute`, `test_alarm`, `calibrate`, `reboot`, `escalate`, `ota`), `GET /api/devices/{id}/commands`
- [x] `GET /api/sensors/{id}` — tình trạng từng cảm biến (ok / chập chờn / lỗi / mất dữ liệu / trạm offline)
- [x] `GET /api/telemetry?device_id&from&to&resolution`, `GET /api/telemetry/latest`, `GET /api/export.csv`
- [x] `GET /api/alerts?level&from&to`, `POST /api/alerts/{id}/ack`
- [x] `GET /api/forecast/{device_id}`, `POST /api/forecast/{device_id}/run`
- [x] `POST /api/rain/google` (nhập số Google), `GET /api/rain/google` (so sánh + % giờ lệch ≤ 10), `POST /api/rain/calibrate` (học lại hiệu chỉnh)
- [x] `GET /api/models`
- [x] `WS /ws/live` đẩy telemetry và alert realtime.
- [x] JWT cho các API ghi; Swagger tại `/docs`.

#### 2.2.7 Dashboard & Thông báo
**Dashboard** (Streamlit, `dashboard/app.py`):
- [x] **Tổng quan:** thẻ giá trị hiện tại (T, H, P, Lux, Rain, Gas), banner cấp cảnh báo (riêng trạng thái offline / MQ-2 lỗi / thử còi / làm nóng), online/offline, RSSI, khung **Tình trạng cảm biến**; làm mới 2 s.
- [x] **Biểu đồ** từng đại lượng (1h / 24h / 7 ngày), tải CSV.
- [x] **Dự báo:** thực tế vs dự báo, khoảng tin cậy, xác suất mưa từng giờ +1/+3/+6 (thẻ ghi số ensemble và phần điều chỉnh của trạm), bảng sai số so với số đo trạm, khung **"Xác suất mưa so với Google"**: form nhập 5 ô Google, bảng Google vs hệ thống, % số giờ lệch ≤ 10, nút **Học lại hiệu chỉnh** (≥ 40 giờ).
- [x] **Cảnh báo:** timeline, lọc theo cấp, nút ack, nguồn edge/cloud.
- [x] **Thiết bị:** form ngưỡng/chu kỳ/chế độ, nút `test_alarm`, `mute`, `calibrate`, `reboot`; lịch sử config/lệnh.
- [x] **Mô hình:** registry (phiên bản, metric, ngày train) + kết quả.
- [x] URL `?page=` / `?device=`, giờ địa phương, trục 24h; dùng được trên điện thoại (layout Streamlit).
- [x] Giao diện theo phong cách dashboard bản giữa kỳ: thanh trên cùng, nút phân đoạn, thẻ số đo viền màu, panel bo góc, sáng/tối (`.streamlit/config.toml`, `dashboard/theme.py`).

**Thông báo** (`backend/app/services/notifier.py`):
- [x] Telegram bot: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` trong `.env`. [ ] ⚙ Tạo bot thật (BotFather) và điền `chat_id`.
- [x] Mẫu tin theo cấp (emoji, giá trị, thời gian, vị trí, link dashboard); nút inline "Đã xử lý" gọi ack; tin tóm tắt thời tiết 6h sáng.
- [x] Email SMTP cho cấp 3 (`SMTP_*`, `ALERT_EMAIL_TO`).

#### 2.2.8 Top-level — Docker Compose
- [x] `docker-compose.yml`: `mosquitto` (tự sinh passwd từ env), `db` (TimescaleDB 2.17 / PG16), `backend` (API + ingest + scheduler, chạy `alembic upgrade head`; volume `backend-data` giữ hiệu chỉnh mưa), `dashboard`, `grafana` (profile `monitoring`); healthcheck; cổng host đổi được (`MQTT_HOST_PORT`, `API_HOST_PORT`, `DASHBOARD_HOST_PORT`, `DB_HOST_PORT`, `GRAFANA_HOST_PORT`).
- [x] README liệt kê biến môi trường (`.env` tuỳ chọn, mặc định trong `backend/app/core/config.py`, `docker-compose.yml`); cài đặt từ đầu ≤ 10 bước (Docker hoặc chạy trực tiếp với SQLite).

---

### 2.3 Kiểm thử Chức năng — tổng **97 test pass** (2026-11-19)

#### Unit Tests (pytest)
- [x] `ml/tests/` — **31 test**: lưu/nạp joblib, Holt-Winters ≡ statsmodels, khớp MicroPython ↔ scikit-learn, feature không rò rỉ, hysteresis/debounce, edge ≡ firmware, chọn ngưỡng F1, bảng Markdown, ensemble mưa (tách mô hình, tỉ lệ phương án bỏ thành viên thiếu số liệu, cấu hình mặc định, điều chỉnh trạm ≤ 10, học hiệu chỉnh theo Google, ánh xạ đẳng biến khi phi tuyến, cần ≥ 40 giờ).
- [x] `firmware/tests/` — **33 test**: filter, rule engine, alert manager, driver BMP280, đệm offline, toàn luồng trạm với schema backend, MQTT client với broker tối giản + Mosquitto thật, mpy-cross biên dịch mọi module, không còn file C/C++.
- [x] `dashboard/tests/` — **9 test**: 6 trang + ack + gửi config + khung mưa so với Google trên API giả (`streamlit.testing.AppTest`, fixture chụp từ trạm thật bằng `capture_fixture.py`).

#### Integration Tests
- [x] `backend/tests/` — **24 test**: schema, ingest, chống trùng, cảnh báo (cấp, cooldown, leo thang, `test`), forecast (mưa từ ensemble, YL-83 ướt cộng điểm, dự phòng LightGBM khi ensemble lỗi, nhập số Google → học lại hiệu chỉnh), API, integration Mosquitto thật → ingest → DB → API (gửi bù, cmd, LWT).
- [x] Load test (`tools/load_test.py`): 20 và 50 thiết bị × 1 msg/s, QoS 1 → mất gói **0 %**, P95 broker ≈ 2 ms (local) / 3.4 ms (Docker + TimescaleDB), CPU backend ≈ 10 % (Docker). Kết quả: `docs/report/results_load_*.md`.
- [x] Độ trễ đo thật trạm → server: trung vị 1,47 s, P95 2,33 s (86 bản tin).

#### Coverage Targets
- [x] Mọi thay đổi code chạy lại đủ 4 bộ test (lệnh ở Nguyên tắc 3) — 0 fail.
- [x] Corner cases: mất ensemble/Open-Meteo, YL-83 ướt, giá trị ngoài dải, bản tin trùng/rỗng, `ts = 0`, cấu hình không hợp lệ, không có model edge.

---

### 2.4 Build & Nạp

- [x] Cloud: `docker compose up -d --build` → 4 container healthy (Docker Desktop, Windows 11/WSL2).
- [ ] Build lại backend + dashboard sau đợt 9 (bảng `google_rain_obs`, volume `backend-data`):
  ```bash
  docker compose up -d --build backend dashboard
  ```
- [ ] Chạy lại `docker compose up -d --build` sau khi đổi lệnh sinh passwd của container mosquitto sang Python.
- [x] Firmware — giá trị hiện tại trong `firmware/src/config.py`:
  ```python
  TELEMETRY_PERIOD_MS = 5000
  RAIN_MV_DRY, RAIN_MV_DRIZZLE, RAIN_MV_MODERATE = 3130, 2600, 2000
  MQ2_DIVIDER = 1.0
  ```
- [ ] ⚙ Nạp firmware: `python firmware/deploy.py --port COM3` (lỗi truyền → chép từng file bằng `mpremote fs cp`; hoặc đặt `telemetry_ms = 5000` ở trang Thiết bị khi trạm online).
- [ ] ⚙ Kiểm tra sau khi nạp:
  - [ ] Log `[SENS]` đủ 5 cảm biến, `sensor_ok` toàn `true`
  - [ ] Màn TFT đúng màu/hướng, 3 trang
  - [ ] Telemetry vào DB mỗi 5 s, `idf_free_heap` ổn định

---

### 2.5 Triển khai Hiện trường

- [x] Trạm thật chạy trong nhà, gửi dữ liệu vào DB (Wi-Fi = Mobile Hotspot laptop, MQTT `192.168.137.1:11883`).
- [ ] ⚙ Vị trí đặt: nơi thoáng, không bị mái che chắn mưa, tránh phản xạ nhiệt từ tường bê tông và máy lạnh. Tấm YL-83 nghiêng 30–45°.
- [ ] ⚙ Sau khi làm hộp bảo vệ mạch, đặt ngoài trời **một đêm** → ghi bảng sai số dự báo so với số đo (trang Dự báo) vào báo cáo §5.1. Không thu dữ liệu ngoài trời dài ngày.
- [ ] ⚙ Burn-in MQ-2 24–48 h → lệnh `calibrate` (đo R0).
- [ ] ⚙ Kiểm tra kết quả:
  - [ ] Chạy liên tục ≥ 72 giờ: heap, số lần reconnect, watchdog reset
  - [ ] 0 lần reset do nguồn (5 V/2 A vào VIN)

---

### 2.6 Sign-off — Kiểm thử Hệ thống (⚙ cần trạm thật)

- [ ] **Độ trễ cảnh báo** tại edge (xả gas → còi) và end-to-end (→ Telegram), P50/P95
  - [ ] Target: edge **< 1 s**, end-to-end **< 5 s**
- [ ] **Mất Wi-Fi**: edge vẫn cảnh báo, đệm offline, gửi bù đúng
  - [ ] Target: **0** bản ghi mất / trùng
- [ ] **Mất broker**: LWT và trạng thái offline trên dashboard.
- [ ] **Báo động giả**: hơi nước, cồn (MQ-2 nhạy chéo), nước hoa → tỉ lệ false positive.
- [ ] Bảng kết quả trong báo cáo:
  - [x] Bảng metric dự báo (các mô hình × các horizon)
  - [ ] Bảng metric cảnh báo (rule / model / hybrid) — chờ dữ liệu khí thật
  - [ ] Bảng độ trễ (edge, end-to-end, P50/P95) — có sẵn độ trễ broker từ load test
  - [ ] Tài nguyên edge: flash, RAM, thời gian suy luận, công suất
  - [ ] Xác suất mưa so với Google (1.7)

**Definition of Done:**
- [ ] ⚙ Trạm đọc đủ 5 loại cảm biến, gửi MQTT ổn định ≥ 72 giờ (còn vấn đề nguồn USB).
- [x] Cảnh báo khí/khói 4 cấp chạy **tại edge kể cả khi mất mạng**, có hysteresis/debounce, tắt còi từ xa (mute) — kiểm chứng bằng pytest và gas bật lửa trên trạm thật.
- [x] Cloud lưu dữ liệu, xác nhận/leo thang cảnh báo, gửi Telegram/Email.
- [x] Dự báo 1h/3h/6h chạy tự động, có bảng so sánh, vượt baseline persistence.
- [x] Dashboard hiển thị realtime, lịch sử, dự báo, cảnh báo, chỉnh cấu hình thiết bị.
- [ ] ⚙ Số liệu chứng minh lợi ích hybrid edge–cloud (độ trễ, chạy offline, độ chính xác rule/model/hybrid).
- [x] Mô hình dùng thư viện chuẩn (scikit-learn, LightGBM, statsmodels, PyTorch), phiên bản ghim; số liệu so sánh chạy lại được bằng `python -m aiot_ml.train_forecast`.
- [x] Toàn bộ mã nguồn bằng Python (firmware MicroPython), 0 file C/C++/JS/shell (có test kiểm tra).
- [x] `docker compose up` dựng lại toàn bộ backend; README đầy đủ.
- [ ] ⚙ Báo cáo (GVHD), slide và video demo hoàn chỉnh.
- [x] Mọi tài liệu, sơ đồ, báo cáo, slide đồng bộ với code (Nguyên tắc 3).

---

### 2.7 Tích hợp Mở rộng

- [x] Grafana (profile `monitoring`): datasource TimescaleDB + dashboard `grafana/dashboards/vku_aiot.json` (đã kiểm tra kết nối DB).
- [ ] ⚙ Bot Telegram thật (BotFather) + `chat_id`.
- [ ] (Tuỳ chọn) VPS / Oracle Cloud / Raspberry Pi; HiveMQ/EMQX Cloud để demo từ xa.
- [ ] (Hướng phát triển) MQ-5/MQ-135, relay/quạt hút.

---

### 2.8 Báo cáo, Slide & Bảo vệ (`docs/report/`)

- [x] `bao_cao.md` → `bao_cao.docx` đủ 6 chương (`tools/md_to_docx.py`):
  - **Ch.1** Giới thiệu · **Ch.2** Cơ sở lý thuyết (IoT/AIoT, MQTT, edge/cloud, cảm biến MOS, CART, RF, GBDT/LightGBM, Logistic, Holt-Winters, Isolation Forest, CUSUM, GRU — kèm thư viện cài đặt) · **Ch.3** Thiết kế (kiến trúc, sơ đồ khối, IPO, phần cứng + sơ đồ đấu dây, MQTT, ERD, sơ đồ tuần tự) · **Ch.4** Hiện thực (firmware MicroPython, backend, pipeline ML, xuất model sang MicroPython, dashboard) · **Ch.5** Thực nghiệm (dự báo, tải MQTT; [ ] ⚙ khí, độ trễ, 72 h, tài nguyên edge, mưa so với Google) · **Ch.6** Kết luận và hướng phát triển · Tài liệu tham khảo · Phụ lục A (chạy lại kết quả), B (kịch bản demo)
- [x] Họ tên, MSSV hai thành viên ở đầu `bao_cao.md`, README, slide. [ ] ⚙ Điền GVHD vào `bao_cao.md` rồi sinh lại `.docx`.
- [x] Slide bảo vệ `docs/report/VKU-SLIDE.pptx` (template VKU, 10 trang: bìa, giới thiệu, thành viên, sơ đồ hệ thống, 2 trang sơ đồ chân, 3 trang so sánh mô hình theo số liệu **bài báo đã công bố**, tài liệu tham khảo); số liệu trang 7–9 trích nguyên văn từ Dong 2026, Darmawan 2023, Ke 2017 (LightGBM), Yu 2021 — cũng ở báo cáo §2.5 (Bảng 2.1–2.4).
- [x] Kịch bản demo: phụ lục B `docs/report/bao_cao.md`.
- [ ] ⚙ Chụp lại ảnh 6 trang dashboard + Grafana từ dữ liệu trạm thật cho báo cáo.
- [ ] ⚙ Quay video demo trên trạm thật: dashboard đang chạy → đưa bật lửa gas lại gần → LED/còi đổi cấp → Telegram nhận tin → bấm ack → rút Wi-Fi để chứng minh edge vẫn cảnh báo.
- [ ] **Bảo vệ đồ án!** 🎯

---

## Timeline Ước Tính (10 tuần)

| Tuần | Phase | Công việc | Trạng thái (2026-11-19) | Rủi ro kiểm soát |
|------|-------|-----------|-------------------------|------------------|
| 1 | 1.1, 2.2.1 | Mua MQ-2 và linh kiện phụ, test từng cảm biến, I2C scan, dựng repo, Docker Mosquitto | ✅ Repo + broker; ⚙ test cảm biến | Thấp |
| 2 | 2.2.2–2.2.5 | Firmware: đọc + lọc + MQTT telemetry + NTP + LWT. Burn-in MQ-2 | ✅ Trạm gửi dữ liệu thật; ⚙ burn-in | Trung bình (heap IDF) |
| 3 | 1.2, 2.2.6 | Backend: ingest + DB + API. Open-Meteo. Pipeline ML nền tảng + unit test | ✅ | Thấp |
| 4 | 1.8, 2.2.1 | Hiệu chuẩn MQ-2 và YL-83. Rule engine đa cấp + còi/LED. Đệm offline. CART/RF, `export_micropython.py` | ✅ Phần mềm + dây đã sửa | Cao (cắm sai dây — đã gặp) |
| 5 | 1.4, 1.10–1.11 | Thu dữ liệu khí có gán nhãn. Huấn luyện model edge, xuất MicroPython, nạp ESP32, kiểm tra khớp | ⚠️ Pipeline xong; ⚙ dữ liệu khí thật | Cao (thí nghiệm gas cần an toàn) |
| 6 | 1.3–1.5 | EDA và feature. Holt-Winters, GBDT (MSE, log-loss). Baseline + GBDT trên Open-Meteo | ✅ | Thấp |
| 7 | 1.4, 2.2.6 | Isolation Forest + CUSUM. GRU (PyTorch) đối chứng. Forecast service + publish `forecast` | ✅ (IF/CUSUM không triển khai) | Thấp |
| 8 | 2.2.7 | Dashboard + Telegram + alert service (leo thang, ack). Màn TFT | ✅; ⚙ bot Telegram thật | Thấp |
| 9 | 1.7, 2.3, 2.6 | Kiểm thử (unit, integration, load, 72 h, mất mạng, báo động giả). Xác suất mưa theo Google | ✅ Unit/integration/load; ⚠️ mưa chờ số Google; ⚙ phần cứng | Cao (phụ thuộc trạm thật) |
| 10 | 2.8 | Báo cáo, slide, video demo, đóng hộp hoàn thiện | ⚠️ Báo cáo + slide xong; ⚙ video, đóng hộp, GVHD | Trung bình |
| **Buffer** | — | Dự phòng sửa phần cứng (nguồn, dây), thu dữ liệu khí | — | Bắt buộc |

> ⚠️ Phần mềm vượt tiến độ; phần còn lại phụ thuộc phần cứng và người làm (dữ liệu khí, nguồn 5 V/2 A, đêm ngoài trời, số Google, video).

---

## Metrics Mục Tiêu

> **Cập nhật 2026-11-19:** thêm chỉ tiêu xác suất mưa lệch Google ≤ 10 điểm; dự báo T/H và F1 mưa đã đạt trên tập test 2025.

### KPI Đề tài

| Hạng mục | Config | Current (đã đo) | Target | Pass Criterion trung gian |
|----------|--------|-----------------|--------|---------------------------|
| **Độ trễ cảnh báo tại edge** (vượt ngưỡng → còi) | rule, debounce 3 | ⚙ chờ đo (trường `edge_latency_ms`) | < 1 s | — |
| **Độ trễ end-to-end** (cảm biến → Telegram) | QoS 1, cấp 2–3 | ⚙ chờ đo (trạm → server: P95 2,33 s) | < 5 s | — |
| **Tỉ lệ mất gói MQTT** | QoS 1, 50 thiết bị × 1 msg/s | **0 %** | < 1 % | — |
| **MAE nhiệt độ 1h** | GBDT, test 2025 | **0,299 °C** | < 1,0 °C | — |
| **MAE độ ẩm 1h** | GBDT, test 2025 | **1,870 %RH** | < 5 %RH | — |
| **F1 mưa / không mưa 3h** | GBDT, test 2025 | **0,833** | > 0,75 | — |
| **Xác suất mưa lệch Google** (cùng giờ) | Ensemble ≥ 1 mm + hiệu chỉnh | ⚙ chờ số Google (5 giờ đo thử: lệch TB 12) | ≤ 10 điểm % | ≥ 40 giờ nhập → % giờ đạt trước/sau khi học |
| **Recall cảnh báo khí cấp ≥ 2** | hybrid | ⚙ chờ dữ liệu khí thật | ≥ 0,95 (ưu tiên không bỏ sót) | — |
| **Chạy liên tục không treo** | WDT 30 s | ⚙ chờ chạy trạm | ≥ 72 giờ | — |

> ⚠️ Chỉ tiêu mưa ±10 **không bảo đảm** cho mọi giờ vì không có số Google tự động (không trả phí, không scrape); dashboard đo và hiển thị trung thực % số giờ đạt.

### Hệ thống & Edge Targets

| Metric | Target |
|--------|--------|
| Chu kỳ telemetry | 5 s (1 s khi cấp ≥ 1) |
| Dashboard Tổng quan làm mới | 2 s |
| Chu kỳ dự báo | 10 phút |
| P95 độ trễ broker (50 thiết bị) | đo: 2 ms local / 3,4 ms Docker |
| CPU backend (50 thiết bị, Docker) | đo: ≈ 10 % |
| Đệm offline | 2000 bản ghi, gửi bù ≤ 200 bản/lượt |
| RAM / µs suy luận model edge | ⚙ đo bằng `bench_device.py` |
| Bản ghi trùng sau gửi bù | 0 |
| File C/C++/JS/shell trong repo | 0 |

---

## Rủi ro và Phương án Dự phòng

| Rủi ro                                          | Phương án                                                                                                                      |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Dữ liệu tự thu quá ít để huấn luyện dự báo      | Huấn luyện, dự báo từ Open-Meteo; trạm chỉ để đối chiếu                                                                        |
| Xác suất mưa lệch Google                        | Ensemble miễn phí + học hiệu chỉnh từ số Google nhập tay; LightGBM dự phòng; đo trung thực % giờ đạt                            |
| Chưa có dữ liệu khí đo thật                     | Edge chạy rule (`AVAILABLE = False`); pipeline ML sẵn sàng, chỉ cần `--data`                                                   |
| MQ-2 trôi giá trị, nhạy với nhiệt độ/độ ẩm      | Burn-in, đưa T/H vào feature, hiệu chuẩn R0 bằng lệnh `calibrate` (CUSUM đã cài nhưng không triển khai)                        |
| YL-83 bị ăn mòn khi để ngoài trời lâu           | Chỉ cấp nguồn khi đọc (GPIO18), phủ lớp bảo vệ, có module dự phòng                                                             |
| DHT22 đọc lỗi hoặc NaN                          | Retry, dùng nhiệt độ BMP280 làm dự phòng, cờ `sensor_ok`                                                                       |
| Wi-Fi không ổn định / board reset khi bật Wi-Fi | Đệm offline, tự kết nối lại, cảnh báo edge độc lập với mạng; cấp nguồn 5 V/2 A vào VIN thay vì USB                             |
| Heap IDF cạn làm Wi-Fi treo                     | Giữ `GC_THRESHOLD`, stack luồng 8 KB, theo dõi `idf_free_heap`                                                                 |
| Trùng cổng broker 1883 với Mosquitto Windows    | Docker map ra cổng host 11883 (`MQTT_HOST_PORT`), board dùng 11883                                                             |
| Không có phần cứng khi phát triển backend       | Integration test MQTT (`backend/tests/`); dữ liệu thật chờ phần cứng                                                           |
| Báo động giả gây phiền                          | Hysteresis, debounce, model hybrid, cooldown thông báo                                                                         |
| Sai số do cài đặt mô hình                       | Dùng thư viện chuẩn (scikit-learn, LightGBM, statsmodels, PyTorch); so khớp `gas_model.py` (MicroPython) ↔ scikit-learn        |
| Phiên bản thư viện lệch khi nạp model           | Ghim scikit-learn/LightGBM trong `ml/pyproject.toml`; file JSON đầu mục ghi phiên bản thư viện lúc huấn luyện                  |
| Tài liệu lệch với code                          | Nguyên tắc 3: sửa code là sửa luôn tài liệu/sơ đồ/báo cáo/slide và khối TRẠNG THÁI, grep tham chiếu cũ, chạy lại toàn bộ test |
| An toàn khi thí nghiệm gas                      | Lượng nhỏ, nơi thoáng, không có nguồn lửa, có người giám sát                                                                   |

---

## Tài Liệu Tham Khảo

| Tài liệu | Nội dung | Link |
|----------|----------|------|
| Ke et al. 2017 | LightGBM — GBDT dùng cho mô hình dự báo triển khai | NIPS 30, pp. 3146–3154 |
| Friedman 2001 | Gradient Boosting Machine | Annals of Statistics 29(5) |
| Breiman 2001 | Random Forests — model edge khí | Machine Learning 45(1) |
| Liu, Ting, Zhou 2008 | Isolation Forest — phát hiện bất thường ở cloud | ICDM 2008 |
| Page 1954 | CUSUM — drift baseline R0 của MQ-2 | Biometrika 41 |
| Holt 1957; Winters 1960 | Holt-Winters — baseline thống kê | Management Science 6 |
| Cho et al. 2014 | GRU — đối chứng deep learning | EMNLP 2014 |
| Pedregosa et al. 2011 | scikit-learn | JMLR 12 |
| Seabold, Perktold 2010 | statsmodels | SciPy 2010 |
| Paszke et al. 2019 | PyTorch | NeurIPS 2019 |
| Dong 2026 | So sánh mô hình ML dự báo nhiệt độ/độ ẩm theo giờ (slide 7–9, báo cáo Bảng 2.1–2.4) | arXiv:2603.23282 |
| Darmawan et al. 2023 | GRU và XGBoost cho hệ thống dự báo thời tiết IoT | IJASEIT 13(3), pp. 851–862 |
| Yu et al. 2021 | LSTM + IoT dự báo nhiệt độ bề mặt đô thị | arXiv:2102.02892 |
| Open-Meteo | Historical Weather API (ERA5 / ECMWF IFS) — dữ liệu huấn luyện | https://open-meteo.com |
| Open-Meteo | Ensemble API (ECMWF IFS 0,25° ENS, NCEP GEFS 0,25°, DWD ICON EPS) — xác suất mưa | https://open-meteo.com/en/docs/ensemble-api |
| OASIS 2014 | MQTT Version 3.1.1 | https://mqtt.org |
| Hanwei; Bosch; Aosong; ROHM | Datasheet MQ-2, BMP280, DHT22, BH1750 | — |
| NIOSH / OSHA | LPG — LEL 2,0 % (ngưỡng cấp 3 ≈ 10 % LEL) | NIOSH Pocket Guide |
