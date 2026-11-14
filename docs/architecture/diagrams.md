# Sơ đồ kiến trúc và CSDL

Ảnh PNG sinh bằng `python tools/render_mermaid.py` → `docs/report/figures/diagrams/`.

## Sơ đồ hệ thống Input – Xử lý – Output

```mermaid
flowchart TB
    subgraph IN["① INPUT — ĐẦU VÀO"]
        direction LR
        I1["<b>DHT22</b><br/>nhiệt độ, độ ẩm"]
        I2["<b>BMP280</b><br/>áp suất"]
        I3["<b>BH1750</b><br/>ánh sáng (lux)"]
        I4["<b>YL-83</b><br/>mưa (AO + DO)"]
        I5["<b>MQ-2</b><br/>khí gas / khói"]
        I6["<b>Open-Meteo API</b><br/>lịch sử · 4 ngày gần nhất"]
        I7["<b>Người dùng</b><br/>lệnh · cấu hình · ack"]
        I1 ~~~ I2 ~~~ I3 ~~~ I4 ~~~ I5 ~~~ I6 ~~~ I7
    end

    subgraph PROC["② XỬ LÝ"]
        direction LR
        subgraph EDGE["Edge — ESP32 · MicroPython (1 Hz, cả khi mất mạng)"]
            direction TB
            P1["Tiền xử lý<br/>median-5 + EWMA<br/>Rs/R0 → ppm · kiểm tra lỗi"]
            P2["Trích 10 feature<br/>cửa sổ 10–60 s"]
            P3["Phân cấp khí/khói 0–3<br/>rule + hysteresis + debounce<br/>max(rule, model cây)"]
            P1 --> P2 --> P3
        end
        MQ(["MQTT · Mosquitto<br/>seq + đệm offline"])
        subgraph CLOUD["Cloud — Docker Compose"]
            direction TB
            C1["Ingest<br/>validate · chống trùng<br/>lưu TimescaleDB"]
            C2["Alert service<br/>xác nhận · leo thang<br/>offline/LWT · nhắc lại"]
            C3["Forecast service<br/>Open-Meteo → GBDT<br/>1/3/6 h · KTC 95 %"]
            C4["REST API + JWT<br/>WebSocket"]
            C1 --> C2
            C1 --> C3
            C1 --> C4
        end
        EDGE <== "→ telemetry · alert · status<br/>← cmd · config · forecast" ==> MQ
        MQ <==> CLOUD
    end

    subgraph OUT["③ OUTPUT — ĐẦU RA"]
        direction LR
        O1["<b>LED xanh/đỏ · còi</b><br/>cảnh báo tại chỗ < 1 s"]
        O2["<b>Màn TFT 1.8&quot;</b><br/>số đo · cấp · dự báo"]
        O3["<b>Dashboard · Grafana</b><br/>biểu đồ · dự báo · cảnh báo"]
        O4["<b>Telegram · Email</b><br/>thông báo theo cấp"]
        O5["<b>Dữ liệu</b><br/>CSDL · CSV · REST API"]
        O1 ~~~ O2 ~~~ O3 ~~~ O4 ~~~ O5
    end

    IN ==> PROC ==> OUT

    classDef inp fill:#FFF4E0,stroke:#D79B00,color:#222
    classDef edge fill:#E8F5E1,stroke:#5C9E45,color:#222
    classDef cloud fill:#E3EEFB,stroke:#4F7FBF,color:#222
    classDef out fill:#F1E8F6,stroke:#8E63A8,color:#222
    classDef bus fill:#FFFFFF,stroke:#D79B00,stroke-width:2px,color:#222
    class I1,I2,I3,I4,I5,I6,I7 inp
    class P1,P2,P3,P4 edge
    class C1,C2,C3,C4 cloud
    class O1,O2,O3,O4,O5 out
    class MQ bus
    style IN fill:#FFFBF3,stroke:#D79B00,stroke-width:2px
    style PROC fill:#FAFAFA,stroke:#666,stroke-width:2px
    style EDGE fill:#F6FBF4,stroke:#82B366
    style CLOUD fill:#F5F9FF,stroke:#6C8EBF
    style OUT fill:#FCF8FD,stroke:#9673A6,stroke-width:2px
```

## Kiến trúc tổng thể (AI lai edge–cloud)

```mermaid
flowchart TB
    subgraph EDGE["Trạm ESP32 + MicroPython (edge, chạy cả khi mất mạng)"]
        direction LR
        SEN["DHT22 · BMP280 · BH1750<br/>YL-83 · MQ-2"] --> FIL["Lọc median-5 + EWMA<br/>Rs/R0 → ppm"]
        FIL --> FEAT["10 feature<br/>cửa sổ 10–60 s"]
        FEAT --> RULE["Rule 4 cấp<br/>hysteresis + debounce"]
        FEAT --> TREE["Model cây gas_model.py<br/>(khi có dữ liệu đo thật)"]
        RULE --> FUS{"max(rule, model)"}
        TREE --> FUS
        FUS --> ACT["LED xanh/đỏ · còi · TFT"]
        FUS --> TX["MQTT client tự viết<br/>seq + đệm offline trên flash"]
    end
    TX <== "telemetry · alert · status ⇅ cmd · config · forecast" ==> MQ(["Mosquitto 2<br/>auth + ACL · LWT · retain"])
    subgraph CLOUD["Cloud — Docker Compose"]
        direction LR
        ING["Ingest<br/>validate · chống trùng · ghi lô"] --> DB[("TimescaleDB<br/>hypertable + aggregate")]
        ING --> ALS["Alert service<br/>leo thang (độ dốc 10 phút)<br/>offline/LWT · nhắc lại · ack"]
        OM["Open-Meteo API"] --> FCS["Forecast service 10 phút<br/>GBDT (LightGBM)"]
        FCS --> DB
        DB --> API["REST API + JWT<br/>WebSocket"] --> DASH["Dashboard Streamlit<br/>Grafana"]
        ALS <--> TG["Telegram · Email<br/>(ack inline)"]
    end
    MQ --> ING
    ALS -- escalate --> MQ
    FCS -- forecast --> MQ
```

## Lược đồ CSDL (ERD)

```mermaid
erDiagram
    devices ||--o{ telemetry : "gửi"
    devices ||--o{ alerts : "phát"
    devices ||--o{ forecasts : "được dự báo"
    devices ||--o{ device_configs : "có phiên bản"
    devices ||--o{ commands : "nhận"
    alerts ||--o{ notifications : "được thông báo"
    devices {
        string id PK
        string name
        float lat
        float lon
        string fw
        string model_ver
        datetime last_seen
        string status
        json last_status
    }
    telemetry {
        string device_id PK
        datetime ts PK "hypertable theo ts"
        bigint seq PK "chống trùng"
        float temp_dht
        float hum
        float pressure_msl
        float lux
        int rain_level
        float gas_ppm
        float gas_rs_r0
        int edge_risk
        float edge_score
        json extra
    }
    alerts {
        int id PK
        string device_id
        datetime ts
        string type "gas, sensor_fault, device_offline, anomaly"
        int level "0..3"
        json cause
        string source "edge, cloud"
        datetime ack_ts
        int notify_count
    }
    forecasts {
        int id PK
        string device_id
        datetime issued_for
        int horizon "1, 3, 6 h"
        string target "temp, hum, rain_prob"
        float value
        float lower
        float upper
        string model_ver
        string source "open-meteo"
    }
    device_configs {
        int id PK
        string device_id
        int version
        json config
        bool acked
    }
    commands {
        string id PK
        string device_id
        string cmd
        json payload
        bool acked
    }
    model_registry {
        int id PK
        string name
        string model_ver
        string metric_name
        float metric_value
        bool active
    }
    notifications {
        int id PK
        int alert_id FK
        string channel
        float latency_ms
        bool ok
    }
```
