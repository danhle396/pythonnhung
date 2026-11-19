# Dự án theo mô hình Input – Xử lý – Output (IPO)

Mỗi phần của hệ thống được mô tả theo 3 câu hỏi: **nhận gì (Input) → làm gì (Xử lý) → đưa ra gì (Output)**.
Output của phần này là Input của phần sau, nên đọc theo thứ tự IPO-1 → IPO-6 là đi hết đường đi của dữ liệu:

```
cảm biến → [IPO-1 trạm ESP32] → MQTT → [IPO-2 thu nhận] → [IPO-3 cảnh báo] → Telegram/Email
                                                         → [IPO-4 dự báo]  → TFT, dashboard
                                                         → [IPO-5 dashboard/API] → người dùng
[IPO-6 huấn luyện offline] → file mô hình cho IPO-1 và IPO-4
```

Sơ đồ khối toàn hệ thống: `system_block_diagram.drawio`, trang 1 (xem `diagrams.md`).

## Bảng tổng hợp

| Sơ đồ | Phần                  | Input chính                                 | Xử lý chính                                      | Output chính                                     | Code                                       |
| ----- | --------------------- | ------------------------------------------- | ------------------------------------------------ | ------------------------------------------------ | ------------------------------------------ |
| IPO-1 | Firmware trạm (edge)  | 5 cảm biến; lệnh, cấu hình, dự báo từ cloud | Lọc nhiễu, tính ppm, phân cấp khí 0–3            | LED, còi, màn TFT; bản tin lên cloud             | `firmware/src/`                            |
| —     | Truyền tin MQTT       | Bản tin của trạm và backend                 | Xác thực, phân quyền topic, LWT, retain          | Bản tin tới đúng nơi nhận                        | `broker/` (chi tiết ở `mqtt.md`)           |
| IPO-2 | Thu nhận và lưu trữ   | telemetry, alert, status, ack               | Kiểm tra dữ liệu, chống trùng, ghi lô            | Dữ liệu trong CSDL, luồng realtime               | `backend/app/mqtt/ingest.py`               |
| IPO-3 | Cảnh báo (cloud)      | Cảnh báo từ trạm, ppm 10 phút gần nhất, LWT | Chọn kênh theo cấp, leo thang, phát hiện offline | Telegram/Email, lệnh `escalate`                  | `backend/app/services/alert_service.py`    |
| IPO-4 | Dự báo (cloud)        | Open-Meteo, Ensemble, số Google nhập tay    | GBDT nhiệt độ/độ ẩm, xác suất mưa từ ensemble    | Dự báo 1/3/6 giờ, bản tin cho TFT                | `backend/app/services/forecast_service.py` |
| IPO-5 | Dashboard và REST API | Thao tác người dùng, dữ liệu CSDL           | JWT, truy vấn, cấu hình có phiên bản             | 6 trang Streamlit, Grafana, CSV, lệnh xuống trạm | `backend/app/api/`, `dashboard/`           |
| IPO-6 | Huấn luyện mô hình    | Open-Meteo 2021–2025, dữ liệu MQ-2 có nhãn  | scikit-learn, LightGBM: huấn luyện, chọn mô hình | File mô hình, `gas_model.py`, bảng kết quả       | `ml/` (chạy trên laptop)                   |

## IPO-1 Firmware ESP32 (edge)

**Vai trò:** đọc cảm biến và tự quyết định cảnh báo khí ngay trên trạm, kể cả khi mất mạng.

**Input**
- DHT22: nhiệt độ, độ ẩm (2 s/lần).
- BMP280 (áp suất) và BH1750 (lux), cùng nối bus I²C.
- YL-83: điện áp AO và chân DO. Cảm biến chỉ được cấp nguồn lúc đọc để tấm mưa đỡ bị ăn mòn.
- MQ-2: điện áp AO nối thẳng GPIO32.
- Từ cloud qua MQTT:
  - `cmd`: `mute`, `test_alarm`, `calibrate`, `reboot`, `escalate`, `ota`.
  - `config`: ngưỡng, hysteresis, debounce, chu kỳ gửi, chế độ rule/model/hybrid.
  - `forecast`: bản tin dự báo.
- Trên flash: `/config.json` (cấu hình, R0). Giờ lấy qua NTP.

**Xử lý:** chạy 2 luồng song song.
1. **Luồng chính, 1 lần/giây** (`sensors.py`, `readings.py`)
   - Lọc nhiễu: median-5 rồi EWMA.
   - Tính khí từ MQ-2: Rs = RL·(Vc − Vout)/Vout, ppm = 574,25·(Rs/R0)^−2,222.
   - Tính điểm sương, chỉ số nhiệt, áp suất quy về mực biển.
   - Phân mức mưa: lấy mức cao nhất trong 3 lần đọc.
   - Phát hiện MQ-2 lỗi: kẹt, mất kết nối hoặc bão hoà.
2. **Edge AI** (`edge_ai.py`, `alert.py`)
   - Tính 10 feature: ppm, Rs/R0, độ dốc 10 s, độ lệch chuẩn 30 s, độ lệch so với nền, nhiệt độ, độ dốc nhiệt độ,
     độ ẩm, độ dốc độ ẩm, lux tương đối.
   - Luật 4 cấp: ngưỡng 300 / 1 000 / 2 000 ppm; độ dốc ≥ 15 ppm/s; nhiệt tăng ≥ 1 °C/phút.
   - Cấp cuối = `max(luật, mô hình, lệnh cloud)`. Lệnh `mute` tắt còi 5 phút.
3. **Luồng mạng** (`_thread`, `net.py`, `mqtt.py` tự viết)
   - Tự nối lại Wi-Fi/MQTT và gửi bản tin.
   - Mất mạng thì đệm bản tin trên flash, có mạng lại thì gửi bù 20 bản ghi mỗi lượt.
   - Gửi `ack` cho lệnh và cấu hình; cập nhật firmware qua OTA.
   - Watchdog 30 s chỉ được "cho ăn" khi luồng mạng còn sống. Luồng mạng treo thì trạm tự khởi động lại.

**Output**

| Cấp | Đèn            | Còi            |
| --- | -------------- | -------------- |
| 0   | Xanh sáng      | Tắt            |
| 1   | Xanh nháy 1 Hz | Tắt            |
| 2   | Đỏ nháy        | Kêu ngắt quãng |
| 3   | Đỏ sáng        | Kêu liên tục   |

- Màn TFT: 3 trang luân phiên 4 s (môi trường, khí, dự báo). Từ cấp 2 trở lên luôn hiện trang khí.
- Lên cloud:
  - `telemetry`: 5 s/lần, 1 s/lần khi cấp ≥ 1.
  - `alert`: khi đổi cấp.
  - `status`: 60 s/lần, kèm LWT.
  - `ack`: sau mỗi lệnh hoặc cấu hình.

## IPO-2 Thu nhận và lưu trữ (ingest)

**Vai trò:** nhận bản tin MQTT, loại dữ liệu sai, ghi vào CSDL không trùng lặp.

**Input:** bản tin `telemetry`, `alert`, `status` (gồm LWT báo offline), `ack` từ mọi trạm.

**Xử lý**
- Thread paho nhận bản tin, đưa vào hàng đợi. Worker kiểm tra bản tin bằng Pydantic.
- Giá trị ngoài dải vật lý (ví dụ nhiệt độ ngoài −10..60 °C) bị loại và ghi vào `extra.rejected`.
- Bản tin gửi trước khi trạm có giờ NTP bị bỏ.
- Telemetry được gom lô (tối đa 200 bản ghi hoặc 0,5 s) rồi ghi bằng `INSERT … ON CONFLICT DO NOTHING` theo khoá
  `(device_id, ts, seq)`. Nhờ vậy dữ liệu trạm gửi bù không bị trùng.
- Alert được xử lý ngay, không chờ lô, để giảm độ trễ.
- TimescaleDB tự gộp dữ liệu theo 1 phút / 10 phút / 1 giờ và xoá dữ liệu thô sau 90 ngày.

**Output**
- Bảng `telemetry`, `alerts` và `devices` (lần cuối thấy, online/offline).
- `device_configs` và `commands` được đánh dấu đã ack.
- Dữ liệu realtime qua WebSocket `/ws/live`.
- Cảnh báo từ trạm được chuyển sang dịch vụ cảnh báo (IPO-3).

## IPO-3 Dịch vụ cảnh báo (cloud)

**Vai trò:** báo cho người dùng đúng kênh, nhắc lại tới khi có người xử lý, phát hiện trạm mất kết nối.

**Input**
- Cảnh báo từ trạm: cấp, cấp trước đó, nguyên nhân, điểm số.
- ppm trong 10–60 phút gần nhất.
- LWT và thời điểm nhận bản tin cuối của trạm.
- Lệnh xác nhận (ack) từ dashboard hoặc nút trên Telegram.

**Xử lý:** chọn kênh gửi theo loại và cấp cảnh báo, rồi chạy 3 việc định kỳ.

| Trường hợp                     | Gửi tới          |
| ------------------------------ | ---------------- |
| Cấp 2                          | Telegram         |
| Cấp 3                          | Telegram + Email |
| Trở về bình thường sau cấp ≥ 2 | Telegram         |
| Cảm biến lỗi, trạm offline     | Telegram         |
| Thử còi (`test_alarm`)         | Không gửi        |

Cùng một (trạm, loại, cấp) không gửi lại trong 120 s (cooldown).

| Việc định kỳ | Chu kỳ                              | Làm gì                                                                           |
| ------------ | ----------------------------------- | -------------------------------------------------------------------------------- |
| Leo thang    | 30 s                                | ppm tăng ở cả hai nửa cửa sổ 10 phút thì nâng 1 cấp và gửi `escalate` xuống trạm |
| Offline      | 15 s                                | Trạm im lặng quá 60 s hoặc có LWT thì tạo cảnh báo `device_offline`              |
| Nhắc lại     | Kiểm tra 20 s, gửi lại sau mỗi 60 s | Cảnh báo cấp 3 chưa ai xác nhận thì gửi lại kèm "[NHẮC LẠI]"                     |

**Output**
- Tin Telegram (có nút "Đã xử lý") và Email.
- Lệnh `escalate` xuống trạm; trạm nâng cấp theo.
- Bảng `alerts` (nguồn edge/cloud, thời điểm ack, số lần đã gửi) và `notifications` (kênh, độ trễ, thành công).
- Sự kiện realtime cho dashboard.

## IPO-4 Dịch vụ dự báo (cloud)

**Vai trò:** cứ 10 phút dự báo nhiệt độ, độ ẩm và xác suất mưa cho 1/3/6 giờ tới, rồi gửi về trạm và dashboard.

**Input**
- Quan trắc Open-Meteo 4 ngày gần nhất tại toạ độ trạm (chỉ các giờ đã qua).
- Open-Meteo Ensemble cho các giờ tới: ECMWF 51 + GFS 31 + ICON 40 phương án, miễn phí.
- Hiệu chỉnh mưa học từ số Google nhập tay (`ml/models/rain_calib.json`).
- Mức mưa YL-83 mới nhất của trạm (trong 15 phút gần nhất).
- Các mô hình GBDT đang dùng (`ml/models/registry.json`).
- Nhiệt độ và độ ẩm của trạm **không** dùng làm đầu vào, vì trạm đặt trong nhà.

**Xử lý** (APScheduler, 10 phút/lần)
1. Làm sạch chuỗi giờ, tạo 56 feature.
2. **Nhiệt độ, độ ẩm:** GBDT dự báo mức thay đổi so với hiện tại ở 1/3/6 giờ.
   - Khoảng tin cậy 95 % = ŷ ± 1,96·RMSE.
   - Độ ẩm được kẹp trong 0–100 %.
3. **Xác suất mưa** ở +1/+3/+6 giờ:
   - Lấy tỉ lệ phương án ensemble có mưa ≥ θ mm. θ và trọng số từng mô hình học từ số Google; mặc định gộp 3 mô hình,
     θ = 1 mm.
   - Ánh xạ đẳng biến (isotonic) nếu đã học.
   - Trạm đang báo mưa thì cộng +10 / +5 / 0 điểm (tối đa 10).
   - Không lấy được ensemble thì dùng GBDT mưa.
4. Không có cả Open-Meteo lẫn ensemble thì bỏ qua lượt đó.

**Output**
- Bảng `forecasts`: giá trị, cận dưới/trên, phiên bản mô hình, nguồn. Mưa lưu cả 3 số `rain_prob` (hiển thị),
  `rain_ens`, `rain_ml` để so sánh.
- Bảng `google_rain_obs`: số Google nhập tay và đặc trưng ensemble tại thời điểm nhập.
- Bản tin `forecast` (retain) gửi về trạm, hiện ở trang "Du bao" trên TFT.
- Tin tóm tắt thời tiết lúc 6 giờ sáng qua Telegram.
- Dữ liệu cho trang Dự báo trên dashboard.

## IPO-5 Dashboard và REST API

**Vai trò:** cho người dùng xem dữ liệu, xác nhận cảnh báo và điều khiển trạm.

**Input**
- Đăng nhập, chọn trang (hoặc mở thẳng bằng `?page=` từ link Telegram).
- Xác nhận cảnh báo; gửi lệnh: thử còi, tắt còi, hiệu chuẩn R0, khởi động lại; sửa ngưỡng và chu kỳ.
- Dữ liệu trong CSDL và luồng realtime qua WebSocket.

**Xử lý**
- FastAPI kiểm tra JWT (tài liệu API ở `/docs`).
- Truy vấn telemetry theo độ phân giải raw / 1 phút / 10 phút / 1 giờ / 1 ngày; tính tình trạng từng cảm biến.
- Sửa cấu hình thì lưu thành phiên bản mới và gửi `config` (retain). Lệnh có id riêng và chờ trạm `ack`.
- Streamlit vẽ biểu đồ theo giờ địa phương. Grafana đọc thẳng TimescaleDB.

**Output**
- 6 trang Streamlit: Tổng quan, Biểu đồ, Dự báo, Cảnh báo, Thiết bị, Mô hình.
- Dashboard Grafana, file CSV.
- Bản tin `cmd` và `config` gửi xuống trạm.

## IPO-6 Huấn luyện mô hình offline (thư viện chuẩn)

**Vai trò:** huấn luyện mô hình trên laptop bằng scikit-learn, LightGBM, statsmodels, PyTorch rồi xuất file cho
backend và firmware.

| Pipeline                            | Dùng dữ liệu                                                    | Kết quả                                                                                  | Trạng thái                                    |
| ----------------------------------- | --------------------------------------------------------------- | ---------------------------------------------------------------------------------------- | --------------------------------------------- |
| Dự báo thời tiết (`train_forecast`) | Open-Meteo theo giờ 2021–2025 tại VKU (43 824 giờ)              | 9 mô hình GBDT + `registry.json`. **MAE nhiệt độ 1 giờ = 0,30 °C, F1 mưa 3 giờ = 0,833** | Đã xong                                       |
| Cảnh báo khí (`train_gas_edge`)     | MQ-2 đo thật 1 Hz, gán nhãn 0–3 (gas ở 50/20/5 cm, khói, nhiễu) | `firmware/src/gas_model.py`, `gas_edge.joblib`                                           | Chờ dữ liệu MQ-2 đo thật; trạm chạy theo luật |
| Bất thường (`train_anomaly`)        | Cần vài tuần telemetry của trạm                                 | `gas_anomaly.joblib`                                                                     | Không triển khai                              |

Chi tiết cách làm:
- **Dự báo thời tiết**
  - Làm sạch dữ liệu: z-score cuộn, nội suy chỗ trống ≤ 3 giờ.
  - 56 feature, không dùng thông tin tương lai. Target là mức thay đổi Δ = x(t+h) − x(t).
  - Chia theo thời gian: train 2021–2023, val 2024, test 2025.
  - So sánh Persistence, Holt-Winters, Ridge, GBDT, GRU; với mưa so sánh Logistic và GBDT. Có early stopping trên val.
  - Kết quả ghi ở `docs/report/results_forecast.md`.
- **Cảnh báo khí**
  - Dùng đúng 10 feature như firmware: `gas_edge.py` khớp `edge_ai.py`, có test kiểm tra.
  - Decision Tree / Random Forest có trọng số lớp; chia dữ liệu theo buổi thí nghiệm.
  - Kiểm tra `gas_model.py` (float32) cho ra kết quả khớp scikit-learn.
- **Bất thường**
  - Isolation Forest trên 8 feature cửa sổ 10 phút; z-score theo giờ; CUSUM trên R0 hằng ngày.
  - Backend bỏ qua bước này.

## Vòng phản hồi

Ngoài chiều đi chính (trạm → cloud → người dùng), có 5 vòng dữ liệu đi ngược lại:

| Vòng               | Từ    | Tới                 | Đường đi                                                                       |
| ------------------ | ----- | ------------------- | ------------------------------------------------------------------------------ |
| Lệnh và cấu hình   | IPO-5 | IPO-1               | API → MQTT `cmd`/`config` → ESP32 → `ack` → ingest                             |
| Leo thang          | IPO-3 | IPO-1               | `cmd escalate` → `max(luật, mô hình, cloud)` → còi/đèn                         |
| Bản tin dự báo     | IPO-4 | IPO-1               | MQTT `forecast` (retain) → trang Dự báo trên TFT                               |
| Mô hình            | IPO-6 | IPO-1, IPO-3, IPO-4 | `registry.json`, `gas_anomaly.json`, `gas_model.py` (nạp bằng `deploy.py`/OTA) |
| Dữ liệu huấn luyện | IPO-2 | IPO-6               | Xuất CSV telemetry → `train_anomaly`; `label_logger.py` → `train_gas_edge`     |
