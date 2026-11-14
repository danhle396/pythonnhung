# Dự án theo mô hình Input – Xử lý – Output (IPO)

Toàn bộ dự án được phân rã theo **mô hình IPO** ở hai mức:

- **Mức 0 — toàn hệ thống:** ảnh `so_do_he_thong_input_xu_ly_output.png` (nguồn trong `diagrams.md`).
- **Mức 1 — 6 phân hệ:** mỗi phân hệ có một sơ đồ IPO và một bảng IPO ở dưới. Output của phân hệ này là Input của phân hệ
  kế tiếp, nối thành chuỗi: **cảm biến → edge → MQTT → ingest → cảnh báo / dự báo → dashboard, thông báo**, cộng
  thêm vòng phản hồi (lệnh, cấu hình, bản tin dự báo trả về trạm) và vòng huấn luyện offline (mô hình nạp vào backend/firmware).

Ảnh PNG sinh bằng `python tools/render_mermaid.py` → `docs/report/figures/diagrams/ipo_*.png`.

## Bảng tổng hợp

| #   | Phân hệ                     | Input                                                       | Xử lý                                                                                     | Output                                                     | Nơi chạy                               |
| --- | --------------------------- | ----------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ---------------------------------------------------------- | -------------------------------------- |
| 1   | Firmware edge (MicroPython) | Tín hiệu 5 cảm biến; lệnh/cấu hình/bản tin dự báo qua MQTT  | Lọc, tính ppm, 10 feature, phân cấp 0–3, đệm offline                                      | LED, còi, màn TFT; bản tin telemetry/alert/status          | ESP32 + MicroPython (`firmware/src/`)  |
| 2   | Truyền thông MQTT           | Bản tin từ trạm và từ backend                               | Xác thực + ACL, LWT, retain, QoS 0/1                                                      | Bản tin chuyển đến đúng bên nhận                           | Mosquitto (`broker/`)                  |
| 3   | Thu nhận và lưu trữ         | telemetry, alert, status, ack                               | Validate, loại giá trị ngoài dải, chống trùng, ghi lô, gộp theo thời gian                 | Bảng CSDL, luồng WebSocket, sự kiện cho dịch vụ cảnh báo   | Backend (`backend/app/mqtt/ingest.py`) |
| 4   | Cảnh báo cloud              | Alert edge, telemetry 10–60 phút, LWT, ack                  | Chính sách kênh theo cấp, cooldown, leo thang, phát hiện offline, nhắc lại                | Telegram/Email, lệnh `escalate`, bảng alerts/notifications | Backend (`alert_service.py`)           |
| 5   | Dự báo cloud                | Open-Meteo 4 ngày gần nhất, mô hình GBDT                    | Làm sạch, 56 feature, GBDT, khoảng tin cậy                                                | Dự báo 1/3/6 h, bản tin TFT, tin 6 giờ sáng                | Backend (`forecast_service.py`)        |
| 6   | Dashboard và API            | Thao tác người dùng, dữ liệu CSDL                           | JWT, REST, WebSocket, cấu hình có phiên bản                                               | 6 trang Streamlit, Grafana, CSV, lệnh/cấu hình xuống trạm  | `backend/app/api/`, `dashboard/`       |
| 7   | Huấn luyện offline          | Open-Meteo 2021–2025; dữ liệu MQ-2 gán nhãn; telemetry trạm | scikit-learn, LightGBM, statsmodels, PyTorch: feature, huấn luyện, chọn mô hình, đánh giá | File mô hình + registry, `gas_model.py`, bảng kết quả      | Laptop (`ml/`)                         |

## IPO-1 Firmware ESP32 (edge)

```mermaid
flowchart LR
    subgraph I["INPUT"]
        direction TB
        i1["DHT22 · 2 s<br/>nhiệt độ, độ ẩm"]
        i2["BMP280 · BH1750 (I²C)<br/>áp suất, lux"]
        i3["YL-83 (ADC + DO)<br/>mức ướt tấm mưa"]
        i4["MQ-2 (ADC, phân áp)<br/>điện áp → Rs"]
        i5["MQTT xuống<br/>cmd · config · forecast"]
        i6["Flash · NTP<br/>config.json, R0, giờ"]
        i1 ~~~ i2 ~~~ i3 ~~~ i5 ~~~ i6
    end
    subgraph P["XỬ LÝ — 2 luồng"]
        direction TB
        p1["<b>Luồng chính · đọc 1 Hz</b><br/>median-5 + EWMA · Rs/R0 → ppm<br/>điểm sương · chỉ số nhiệt · áp suất mực biển<br/>mức mưa · phát hiện lỗi cảm biến"]
        p2["<b>Luồng chính · Edge AI</b><br/>10 feature (cửa sổ 10–60 s)<br/>rule 4 cấp · hysteresis 15 % · debounce 3/5<br/>max(rule, model, cloud) · mute 5 phút"]
        p3["<b>Luồng mạng (_thread)</b><br/>Wi-Fi/MQTT tự nối lại · LWT<br/>đệm flash 2 000 bản ghi, gửi bù<br/>ack lệnh · OTA"]
        p1 --> p2 --> p3
    end
    subgraph O["OUTPUT"]
        direction TB
        o1["LED xanh/đỏ · còi<br/>theo cấp 0–3"]
        o2["Màn TFT 3 trang<br/>môi trường · khí · dự báo"]
        o3["telemetry<br/>10 s (1 s khi cấp ≥ 1)"]
        o4["alert khi đổi cấp<br/>status 60 s"]
        o5["ack lệnh / cấu hình"]
        o1 ~~~ o2 ~~~ o3 ~~~ o4 ~~~ o5
    end
    I ==> P ==> O
    classDef inp fill:#FFF4E0,stroke:#D79B00,color:#222
    classDef prc fill:#E8F5E1,stroke:#5C9E45,color:#222
    classDef out fill:#F1E8F6,stroke:#8E63A8,color:#222
    class i1,i2,i3,i4,i5,i6 inp
    class p1,p2,p3 prc
    class o1,o2,o3,o4,o5 out
    style I fill:#FFFBF3,stroke:#D79B00,stroke-width:2px
    style P fill:#F6FBF4,stroke:#82B366,stroke-width:2px
    style O fill:#FCF8FD,stroke:#9673A6,stroke-width:2px
```

|            | Nội dung                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Input**  | DHT22 (nhiệt độ, độ ẩm, 2 s/lần); BMP280 (áp suất), BH1750 (lux) qua I²C; YL-83 (điện áp AO + DO, chỉ cấp nguồn khi đọc); MQ-2 (điện áp AO qua cầu phân áp 10k/20k); MQTT xuống: `cmd` (mute, test_alarm, calibrate, reboot, escalate, ota), `config` (ngưỡng, hysteresis, debounce, chu kỳ, chế độ rule/model/hybrid), `forecast`; `/config.json` trên flash (cấu hình, R0); NTP (giờ).                                                                                                                                                                                                                                                                                                                                                                                                              |
| **Xử lý**  | Luồng chính, đọc 1 Hz (`sensors.py`, `readings.py`): lọc median-5 + EWMA, Rs = RL·(Vc − Vout)/Vout, ppm = 574,25·(Rs/R0)^−2,222, điểm sương, chỉ số nhiệt, quy áp suất về mực biển, phân mức mưa (giữ mức cao nhất trong 3 lần đọc), phát hiện lỗi MQ-2 (kẹt, mất kết nối, bão hoà). Edge AI (`edge_ai.py`, `alert.py`): 10 feature (ppm, Rs/R0, độ dốc 10 s, độ lệch chuẩn 30 s, độ lệch so với nền, nhiệt độ, độ dốc nhiệt độ, độ ẩm, độ dốc độ ẩm, lux tương đối) → rule 4 cấp (300/1 000/2 000 ppm, độ dốc ≥ 15 ppm/s, nhiệt tăng ≥ 1 °C/phút) → `max(rule, model, cloud)`; mute 5 phút. Luồng mạng `_thread` (`net.py`, `mqtt.py` tự viết): kết nối lại, publish, đệm offline trên flash, gửi bù 20 bản ghi/lượt, ack, OTA. Watchdog `machine.WDT` 30 s chỉ được cho ăn khi luồng mạng còn sống. |
| **Output** | Tại chỗ: LED xanh (cấp 0; nháy 1 Hz ở cấp 1), LED đỏ nháy + còi ngắt quãng (cấp 2), LED đỏ + còi liên tục (cấp 3); màn TFT 3 trang luân phiên 4 s (cấp ≥ 2 luôn hiện trang khí). Lên cloud: `telemetry`, `alert` (level, prev_level, cause, score), `status` (retain, LWT), `ack`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |

## IPO-2 Thu nhận và lưu trữ (ingest)

```mermaid
flowchart LR
    subgraph I["INPUT"]
        direction TB
        i1["telemetry<br/>(device_id, ts, seq)"]
        i2["alert · status (LWT)"]
        i3["ack (lệnh, cấu hình)"]
        i1 ~~~ i2 ~~~ i3
    end
    subgraph P["XỬ LÝ"]
        direction TB
        p1["Subscribe vku/aiot/+/…<br/>(thread paho → hàng đợi)"]
        p2["Validate Pydantic<br/>loại giá trị ngoài dải vật lý"]
        p3["Chống trùng (device_id, ts, seq)<br/>ghi lô ≤ 200 bản ghi / 0,5 s"]
        p4["TimescaleDB: hypertable<br/>aggregate 1m · 10m · 1h<br/>giữ dữ liệu thô 90 ngày"]
        p1 --> p2 --> p3 --> p4
    end
    subgraph O["OUTPUT"]
        direction TB
        o1["Bảng telemetry · alerts<br/>devices"]
        o2["WebSocket /ws/live<br/>(realtime)"]
        o3["Sự kiện cho<br/>dịch vụ cảnh báo"]
        o4["Trạng thái thiết bị<br/>online/offline · cấu hình đã ack"]
        o1 ~~~ o2 ~~~ o3 ~~~ o4
    end
    I ==> P ==> O
    classDef inp fill:#FFF4E0,stroke:#D79B00,color:#222
    classDef prc fill:#E3EEFB,stroke:#4F7FBF,color:#222
    classDef out fill:#F1E8F6,stroke:#8E63A8,color:#222
    class i1,i2,i3 inp
    class p1,p2,p3,p4 prc
    class o1,o2,o3,o4 out
    style I fill:#FFFBF3,stroke:#D79B00,stroke-width:2px
    style P fill:#F5F9FF,stroke:#6C8EBF,stroke-width:2px
    style O fill:#FCF8FD,stroke:#9673A6,stroke-width:2px
```

|            | Nội dung                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Input**  | Bản tin MQTT `telemetry`, `alert`, `status` (gồm LWT offline), `ack` từ mọi trạm.                                                                                                                                                                                                                                                                                                                                                     |
| **Xử lý**  | Thread paho đưa bản tin vào hàng đợi; worker validate bằng Pydantic; giá trị ngoài dải vật lý bị loại và ghi vào `extra.rejected`; bản tin trước khi có giờ NTP bị bỏ; telemetry gom lô (≤ 200 bản ghi hoặc 0,5 s) rồi `INSERT … ON CONFLICT DO NOTHING` theo khoá (device_id, ts, seq), nhờ đó gửi bù không bị trùng; alert xử lý ngay để giảm độ trễ. TimescaleDB tự làm mới 3 continuous aggregate và xoá dữ liệu thô sau 90 ngày. |
| **Output** | Bản ghi trong các bảng `telemetry`, `alerts`, `devices` (last_seen, status), `device_configs`/`commands` (đánh dấu đã ack); đẩy realtime qua WebSocket `/ws/live`; chuyển alert edge sang dịch vụ cảnh báo.                                                                                                                                                                                                                           |

## IPO-3 Dịch vụ cảnh báo (cloud)

```mermaid
flowchart LR
    subgraph I["INPUT"]
        direction TB
        i1["Alert từ edge<br/>level · cause · score"]
        i2["Telemetry ppm<br/>10–60 phút gần nhất"]
        i3["LWT / last_seen"]
        i4["Ack từ dashboard<br/>hoặc nút Telegram"]
        i1 ~~~ i2 ~~~ i3
    end
    subgraph P["XỬ LÝ"]
        direction TB
        p1["Chính sách kênh theo cấp<br/>cấp 2 → Telegram<br/>cấp 3 → Telegram + Email<br/>cooldown theo (thiết bị, loại, cấp)"]
        p2["Leo thang · 30 s/lần<br/>ppm tăng đều 10 phút"]
        p3["Offline · 15 s/lần<br/>im lặng > 60 s hoặc LWT"]
        p4["Nhắc lại cấp 3 · 20 s/lần<br/>tới khi được ack"]
        p1 ~~~ p2 ~~~ p3 ~~~ p4
    end
    subgraph O["OUTPUT"]
        direction TB
        o1["Tin Telegram (nút &quot;Đã xử lý&quot;)<br/>Email"]
        o2["cmd escalate<br/>xuống trạm"]
        o3["Bảng alerts<br/>notifications (latency_ms)"]
        o4["Sự kiện WebSocket<br/>cho dashboard"]
        o1 ~~~ o2 ~~~ o3 ~~~ o4
    end
    I ==> P ==> O
    classDef inp fill:#FFF4E0,stroke:#D79B00,color:#222
    classDef prc fill:#E3EEFB,stroke:#4F7FBF,color:#222
    classDef out fill:#F1E8F6,stroke:#8E63A8,color:#222
    class i1,i2,i3,i4,i5 inp
    class p1,p2,p3,p4 prc
    class o1,o2,o3,o4 out
    style I fill:#FFFBF3,stroke:#D79B00,stroke-width:2px
    style P fill:#F5F9FF,stroke:#6C8EBF,stroke-width:2px
    style O fill:#FCF8FD,stroke:#9673A6,stroke-width:2px
```

|            | Nội dung                                                                                                                                                                                                                                                                                                                                                                |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Input**  | Alert edge (cấp, cấp trước, nguyên nhân, điểm số); telemetry ppm trong cửa sổ 10–60 phút; LWT và thời điểm nhận bản tin cuối; ack từ API/dashboard hoặc nút inline Telegram.                                                                                                                                                                                            |
| **Xử lý**  | Chọn kênh theo loại và cấp (cấp 2 → Telegram; cấp 3 → Telegram + Email; về bình thường sau cấp ≥ 2 → Telegram; lỗi cảm biến/offline → Telegram; thử còi → không gửi) và cooldown; mỗi 30 s đánh giá leo thang (độ dốc ppm dương ở cả hai nửa cửa sổ 10 phút) → nâng 1 cấp; mỗi 15 s kiểm tra offline (> 60 s hoặc LWT); mỗi 20 s nhắc lại cảnh báo cấp 3 chưa được ack. |
| **Output** | Tin Telegram/Email; lệnh `cmd escalate` xuống trạm (edge nâng cấp theo); bản ghi `alerts` (source = edge/cloud, ack_ts, notify_count) và `notifications` (kênh, độ trễ, thành công); sự kiện realtime cho dashboard.                                                                                                                                                    |

## IPO-4 Dịch vụ dự báo (cloud)

```mermaid
flowchart LR
    subgraph I["INPUT"]
        direction TB
        i2["Open-Meteo<br/>4 ngày gần nhất"]
        i3["Mô hình GBDT<br/>(model registry)"]
        i2 ~~~ i3
    end
    subgraph P["XỬ LÝ"]
        direction TB
        p1["10 phút/lần: lấy Open-Meteo<br/>làm sạch chuỗi giờ"]
        p3["56 feature: lag, rolling<br/>xu hướng áp suất, chu kỳ ngày/năm"]
        p4["GBDT nhiệt độ, độ ẩm + xác suất mưa<br/>1/3/6 h · KTC ŷ ± 1,96·RMSE"]
        p5["Không có Open-Meteo<br/>→ bỏ qua lượt đó"]
        p1 --> p3 --> p4 --> p5
    end
    subgraph O["OUTPUT"]
        direction TB
        o1["Bảng forecasts<br/>(value, lower, upper, source)"]
        o2["MQTT forecast (retain)<br/>→ trang Dự báo trên TFT"]
        o3["Tin tóm tắt<br/>6 giờ sáng (Telegram)"]
        o4["Trang Dự báo<br/>trên dashboard"]
        o1 ~~~ o2 ~~~ o3 ~~~ o4
    end
    I ==> P ==> O
    classDef inp fill:#FFF4E0,stroke:#D79B00,color:#222
    classDef prc fill:#E3EEFB,stroke:#4F7FBF,color:#222
    classDef out fill:#F1E8F6,stroke:#8E63A8,color:#222
    class i1,i2,i3,i4 inp
    class p1,p2,p3,p4,p5 prc
    class o1,o2,o3,o4 out
    style I fill:#FFFBF3,stroke:#D79B00,stroke-width:2px
    style P fill:#F5F9FF,stroke:#6C8EBF,stroke-width:2px
    style O fill:#FCF8FD,stroke:#9673A6,stroke-width:2px
```

|            | Nội dung                                                                                                                                                                                                                                                                         |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Input**  | Quan trắc Open-Meteo 4 ngày gần nhất (chỉ các giờ đã qua) tại toạ độ trạm; các mô hình GBDT đang hoạt động trong `ml/models/registry.json`. Số đo của trạm không dùng làm đầu vào.                                                                                               |
| **Xử lý**  | APScheduler chạy 10 phút/lần: làm sạch chuỗi giờ; tạo 56 feature; GBDT dự báo thay đổi Δ của nhiệt độ/độ ẩm và xác suất mưa ở 1/3/6 giờ; khoảng tin cậy 95 % = ŷ ± 1,96·RMSE_test; độ ẩm kẹp trong [0, 100]. Không lấy được Open-Meteo → bỏ qua lượt đó, không phát bản tin mới. |
| **Output** | Bảng `forecasts` (giá trị, cận dưới/trên, phiên bản mô hình, nguồn); bản tin `forecast` retain gửi về trạm, hiện trên trang "Du bao" của TFT; tin tóm tắt thời tiết lúc 6 giờ sáng; dữ liệu cho trang Dự báo của dashboard.                                                      |

## IPO-5 Dashboard và REST API

```mermaid
flowchart LR
    subgraph I["INPUT"]
        direction TB
        i1["Người dùng<br/>đăng nhập · chọn trang"]
        i2["Thao tác<br/>ack · lệnh · form ngưỡng"]
        i3["CSDL<br/>telemetry · alerts · forecasts"]
        i4["WebSocket /ws/live"]
        i1 ~~~ i2 ~~~ i3
    end
    subgraph P["XỬ LÝ"]
        direction TB
        p1["FastAPI · JWT<br/>(Swagger /docs)"]
        p2["Truy vấn raw / 1m / 10m / 1h / 1d<br/>tình trạng cảm biến"]
        p3["Cấu hình có phiên bản<br/>lệnh có id → chờ ack"]
        p4["Streamlit render 6 trang<br/>Grafana đọc thẳng TimescaleDB"]
        p1 --> p2 --> p3 --> p4
    end
    subgraph O["OUTPUT"]
        direction TB
        o1["6 trang: Tổng quan · Biểu đồ<br/>Dự báo · Cảnh báo · Thiết bị · Mô hình"]
        o2["Grafana<br/>panel ngưỡng ppm"]
        o3["File CSV"]
        o4["MQTT cmd · config<br/>xuống trạm"]
        o1 ~~~ o2 ~~~ o3 ~~~ o4
    end
    I ==> P ==> O
    classDef inp fill:#FFF4E0,stroke:#D79B00,color:#222
    classDef prc fill:#E3EEFB,stroke:#4F7FBF,color:#222
    classDef out fill:#F1E8F6,stroke:#8E63A8,color:#222
    class i1,i2,i3,i4 inp
    class p1,p2,p3,p4 prc
    class o1,o2,o3,o4 out
    style I fill:#FFFBF3,stroke:#D79B00,stroke-width:2px
    style P fill:#F5F9FF,stroke:#6C8EBF,stroke-width:2px
    style O fill:#FCF8FD,stroke:#9673A6,stroke-width:2px
```

|            | Nội dung                                                                                                                                                                                                                                                                              |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Input**  | Thao tác người dùng: đăng nhập, chọn trang (hoặc mở thẳng bằng `?page=` từ link Telegram), xác nhận cảnh báo, gửi lệnh (thử còi, tắt còi, hiệu chuẩn R0, khởi động lại), sửa ngưỡng/chu kỳ; dữ liệu trong CSDL; luồng realtime từ WebSocket.                                          |
| **Xử lý**  | FastAPI kiểm tra JWT; truy vấn telemetry theo độ phân giải raw/1m/10m/1h/1d; tính tình trạng từng cảm biến; lưu cấu hình thành phiên bản mới và publish `config` (retain), lệnh có id và chờ `ack`; Streamlit vẽ biểu đồ theo giờ địa phương; Grafana truy vấn TimescaleDB trực tiếp. |
| **Output** | 6 trang Streamlit (Tổng quan, Biểu đồ, Dự báo, Cảnh báo, Thiết bị, Mô hình); dashboard Grafana; file CSV; bản tin `cmd`/`config` gửi xuống trạm.                                                                                                                                      |

## IPO-6 Huấn luyện mô hình offline (thư viện chuẩn)

```mermaid
flowchart LR
    subgraph I["INPUT"]
        direction TB
        i1["Open-Meteo 2021–2025<br/>43 824 giờ tại VKU"]
        i2["MQ-2 đo thật có nhãn 0–3<br/>(label_logger.py) — chờ thu"]
        i3["Telemetry trạm vài tuần<br/>— không có"]
        i1 ~~~ i2 ~~~ i3
    end
    subgraph P["XỬ LÝ — thư viện ML"]
        direction TB
        p1["<b>Dự báo:</b> làm sạch · 56 feature · Δ target<br/>train 2021–23 / val 2024 / test 2025<br/>Persistence · HW · Ridge · GBDT · GRU<br/>mưa: Logistic · GBDT (LightGBM)"]
        p2["<b>Khí edge:</b> 10 feature như firmware<br/>Decision Tree / Random Forest<br/>so sánh Rule · Model · Hybrid<br/>chia theo buổi thí nghiệm"]
        p3["<b>Bất thường (không triển khai):</b><br/>Isolation Forest · z-score theo giờ<br/>CUSUM trên R0"]
        p1 ~~~ p2 ~~~ p3
    end
    subgraph O["OUTPUT"]
        direction TB
        o1["models/forecast/*.joblib + .json<br/>registry.json → backend"]
        o2["gas_model.py<br/>→ firmware ESP32"]
        o3["gas_anomaly.joblib<br/>(không tạo)"]
        o4["Bảng kết quả · hình<br/>experiments.csv"]
        o1 ~~~ o2 ~~~ o3 ~~~ o4
    end
    I ==> P ==> O
    classDef inp fill:#FFF4E0,stroke:#D79B00,color:#222
    classDef prc fill:#F3ECF8,stroke:#9673A6,color:#222
    classDef out fill:#F1E8F6,stroke:#8E63A8,color:#222
    class i1,i2,i3 inp
    class p1,p2,p3 prc
    class o1,o2,o3,o4 out
    style I fill:#FFFBF3,stroke:#D79B00,stroke-width:2px
    style P fill:#FBF8FC,stroke:#9673A6,stroke-width:2px
    style O fill:#FCF8FD,stroke:#9673A6,stroke-width:2px
```

| Pipeline                             | Input                                                                    | Xử lý                                                                                                                                                                                         | Output                                                                                                                                | Trạng thái                                |
| ------------------------------------ | ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| Dự báo thời tiết (`train_forecast`)  | Open-Meteo theo giờ 2021–2025 tại 15,975°N 108,253°E (43 824 giờ)        | Làm sạch (z-score cuộn, nội suy ≤ 3 giờ); 56 feature không rò rỉ tương lai; target Δ = x(t+h) − x(t); chia theo thời gian; so sánh 6 mô hình hồi quy + 3 mô hình mưa; early stopping trên val | 9 mô hình GBDT (6 hồi quy + 3 mưa) + `registry.json`; `results_forecast.md`; hình. **MAE nhiệt độ 1 h = 0,30 °C, F1 mưa 3 h = 0,833** | Đã xong                                   |
| Cảnh báo khí edge (`train_gas_edge`) | CSV 1 Hz đo thật, nhãn 0–3 theo kịch bản (gas ở 50/20/5 cm, khói, nhiễu) | Cùng 10 feature với firmware (`gas_edge.py` ≡ `edge_ai.py`, có test); DT/RF có trọng số lớp; chia theo buổi; so khớp `gas_model.py` (float32) với scikit-learn                                | `firmware/src/gas_model.py`, `gas_edge.joblib`, `results_gas_edge.md`                                                                 | Chờ dữ liệu MQ-2 đo thật; edge chạy rule  |
| Bất thường cloud (`train_anomaly`)   | Cần vài tuần telemetry trạm — **không có**                               | 8 feature cửa sổ 10 phút; Isolation Forest; z-score theo giờ; CUSUM trên R0 hằng ngày                                                                                                         | `gas_anomaly.joblib` cho alert service; đề xuất hiệu chuẩn lại MQ-2                                                                   | Không triển khai; backend bỏ qua bước này |

## Vòng phản hồi

| Vòng               | Output của                 | trở thành Input của        | Đường đi                                                                       |
| ------------------ | -------------------------- | -------------------------- | ------------------------------------------------------------------------------ |
| Lệnh và cấu hình   | Dashboard (IPO-5)          | Firmware (IPO-1)           | API → MQTT `cmd`/`config` → ESP32 → `ack` → ingest                             |
| Leo thang          | Dịch vụ cảnh báo (IPO-3)   | Firmware (IPO-1)           | `cmd escalate` → `max(rule, model, cloud)` → còi/LED                           |
| Bản tin dự báo     | Dịch vụ dự báo (IPO-4)     | Firmware (IPO-1)           | MQTT `forecast` retain → trang Dự báo trên TFT                                 |
| Mô hình            | Huấn luyện offline (IPO-6) | Dự báo, cảnh báo, firmware | `registry.json`, `gas_anomaly.json`, `gas_model.py` (nạp bằng `deploy.py`/OTA) |
| Dữ liệu huấn luyện | Ingest (IPO-2)             | Huấn luyện offline (IPO-6) | Xuất CSV telemetry → `train_anomaly`; `label_logger.py` → `train_gas_edge`     |
