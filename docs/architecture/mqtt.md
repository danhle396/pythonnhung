# Thiết kế MQTT

Trạm ESP32 và backend không gọi trực tiếp nhau. Cả hai cùng nói chuyện qua broker **Mosquitto 2** (`broker/mosquitto/`).

| Mục              | Giá trị                                                                                                                                                    |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tiền tố topic    | `vku/aiot/{device_id}/…`, ví dụ `vku/aiot/station01/telemetry`                                                                                             |
| Cổng             | Trong Docker: 1883. Trên máy phát triển: **11883** (`MQTT_HOST_PORT` trong `.env`), vì Mosquitto cài sẵn trên Windows đã chiếm 1883. Trạm phải dùng 11883. |
| Xác thực         | Username/password. Username của trạm = `device_id`                                                                                                         |
| Phân quyền (ACL) | Mỗi trạm chỉ được ghi vào topic của chính nó                                                                                                               |

## Topic

### Trạm gửi lên cloud

| Topic       | Khi nào gửi                            | Nội dung                                                                                 | QoS     | Retain |
| ----------- | -------------------------------------- | ---------------------------------------------------------------------------------------- | ------- | ------ |
| `telemetry` | 5 s/lần; 1 s/lần khi cấp khí ≥ 1       | Số đo cảm biến và kết quả edge AI                                                        | 0*      | Không  |
| `alert`     | Khi đổi cấp cảnh báo hoặc cảm biến lỗi | Cảnh báo khí/khói hoặc `sensor_fault`                                                    | 0*      | Không  |
| `status`    | Khi kết nối và 60 s/lần                | `online` kèm RSSI, uptime, heap. Mất kết nối thì broker tự gửi LWT `{"state":"offline"}` | 1 (LWT) | Có     |
| `ack`       | Sau mỗi lệnh hoặc cấu hình nhận được   | Đã nhận / đã áp dụng chưa                                                                | 0*      | Không  |

### Cloud gửi xuống trạm

| Topic      | Khi nào gửi        | Nội dung                                                            | QoS | Retain |
| ---------- | ------------------ | ------------------------------------------------------------------- | --- | ------ |
| `forecast` | 10 phút/lần        | Dự báo 1/3/6 giờ và dòng `summary` ngắn để hiện trên màn TFT        | 1   | Có     |
| `cmd`      | Khi người dùng bấm | Lệnh `mute`, `test_alarm`, `calibrate`, `reboot`, `escalate`, `ota` | 1   | Không  |
| `config`   | Khi sửa cấu hình   | Ngưỡng, chu kỳ gửi, chế độ edge, R0, `version`                      | 1   | Có     |

Retain = broker giữ lại bản tin cuối cùng. Trạm vừa kết nối sẽ nhận ngay cấu hình và dự báo mới nhất, không phải chờ.

### \* Vì sao trạm gửi QoS 0 mà không mất dữ liệu?

Client MQTT trên trạm (`firmware/src/mqtt.py`, tự viết bằng MicroPython) chỉ gửi được QoS 0. Việc "gửi ít nhất một lần"
được làm ở tầng ứng dụng:

1. Mỗi bản ghi có số thứ tự `seq` tăng dần, lưu ở `/seq.txt` trên flash nên không reset khi khởi động lại.
2. Gửi thất bại thì bản ghi vào **đệm offline trên flash** (tối đa 2000 bản ghi). Có mạng lại thì gửi bù.
3. Backend chống trùng theo khoá `(device_id, ts, seq)`, nên một bản ghi gửi 2 lần vẫn chỉ được lưu 1 lần.

Backend và công cụ `tools/load_test.py` dùng QoS 1 thật.

## Payload

### telemetry

```json
{"device_id":"station01","ts":1762671600,"seq":10234,
 "temp_dht":29.4,"hum":78.2,"temp_bmp":29.9,"pressure":1008.6,"pressure_msl":1009.5,
 "lux":15230,"dew_point":25.1,"heat_index":34.2,"rain_raw":3810,"rain_level":0,
 "gas_raw":812,"gas_rs_r0":7.9,"gas_ppm":210,"gas_slope":0.4,
 "edge_risk":0,"edge_score":0.03,"warming_up":false,
 "sensor_ok":{"dht":true,"bmp":true,"bh":true,"rain":true,"gas":true},
 "fw":"2.0.0","model_ver":"gas-v1"}
```

| Trường                                         | Ý nghĩa                                                               |
| ---------------------------------------------- | --------------------------------------------------------------------- |
| `ts`, `seq`                                    | Thời điểm đo (Unix, giây) và số thứ tự bản ghi                        |
| `temp_dht`, `hum`                              | Nhiệt độ (°C), độ ẩm (%) từ DHT22                                     |
| `temp_bmp`, `pressure`, `pressure_msl`         | Nhiệt độ và áp suất từ BMP280; áp suất quy về mực nước biển (hPa)     |
| `lux`                                          | Ánh sáng từ BH1750                                                    |
| `dew_point`, `heat_index`                      | Điểm sương, chỉ số nhiệt (°C), tính trên trạm                         |
| `rain_raw`, `rain_level`                       | Điện áp YL-83 (mV, càng thấp càng ướt) và mức mưa 0–3                 |
| `gas_raw`, `gas_rs_r0`, `gas_ppm`, `gas_slope` | Điện áp MQ-2 (mV), tỉ số Rs/R0, nồng độ ước lượng (ppm), độ dốc ppm/s |
| `edge_risk`, `edge_score`                      | Cấp cảnh báo khí 0–3 do trạm quyết định, điểm số của mô hình          |
| `warming_up`                                   | MQ-2 đang làm nóng, số đo khí chưa tin được                           |
| `sensor_ok`                                    | Từng cảm biến còn hoạt động không                                     |

Cảm biến lỗi thì trường tương ứng gửi `null`. Backend loại các giá trị ngoài dải vật lý (nhiệt độ −10..60 °C, áp suất
900..1100 hPa, độ ẩm 0..100 %…) và ghi tên trường bị loại vào cột `extra.rejected`.

### alert

```json
{"device_id":"station01","ts":1762671620,"seq":10240,"type":"gas",
 "level":2,"prev_level":1,"level_name":"warning","cause":["gas_ppm>1000","model"],
 "gas_ppm":1350,"score":0.87,"rule_level":2,"model_level":2,
 "action":["led_red_blink","buzzer_intermittent","fan_on"],"edge_latency_ms":3}
```

- `type` có 3 giá trị: `gas`, `sensor_fault`, `test`.
  - Với `sensor_fault`, trường `fault` cho biết lỗi gì: 1 = kẹt, 2 = mất kết nối, 3 = bão hoà.
- `cause` cho biết vì sao lên cấp. `rule_level` và `model_level` là cấp do luật và do mô hình đưa ra; `level` lấy số lớn hơn.
- Backend tự tạo thêm cảnh báo `device_offline` với `source = cloud`.

### status và ack

```json
{"state":"online","device_id":"station01","rssi":-61,"uptime_s":86400,"free_heap":182000,
 "reconnects":3,"offline_pending":0,"fw":"2.0.0","model_ver":"gas-v1","inference_us":42.1}
{"device_id":"station01","ts":1762671630,"ref":"cmd","id":"<uuid>","ok":true,"msg":"mute"}
```

- `status`: `offline_pending` là số bản ghi đang nằm trong đệm offline chờ gửi bù.
- `ack`: `ref` cho biết xác nhận cho `cmd` hay `config`. `id` khớp với id của lệnh. `ok: false` nghĩa là bị từ chối.

### cmd, config, forecast

```json
{"cmd":"escalate","id":"<uuid>","level":3}
{"version":4,"th1":300,"th2":1000,"th3":2000,"slope1":15,"dtemp3":1.0,"hyst":0.15,
 "debounce_up":3,"debounce_down":5,"telemetry_ms":10000,"mode":"hybrid","r0_kohm":10.2}
{"device_id":"station01","ts":1762671600,"source":"open-meteo+ensemble","rain_source":"ensemble",
 "summary":"1h 28.8C 3h 28.0C Mua3h 45%",
 "items":[{"target":"temp","h":1,"value":28.83,"lower":27.97,"upper":29.70,"model_ver":"fc-temp_1h-..."},
          {"target":"rain_prob","h":3,"value":0.45,"lower":null,"upper":null,"model_ver":"ens-default+station"}]}
```

- **config**
  - `th1/th2/th3`: ngưỡng ppm cho cấp 1/2/3.
  - `hyst`: hysteresis. `debounce_up/down`: số lần đo liên tiếp cần có để lên/xuống cấp.
  - `mode`: `rule`, `model` hoặc `hybrid`.
  - Trạm kiểm tra cấu hình (ví dụ `th1 < th2 < th3`, giá trị trong dải) trước khi áp dụng và lưu vào `/config.json`.
    Cấu hình sai bị từ chối bằng `ack` có `ok: false`.
- **forecast**
  - `rain_source = "ensemble"`: xác suất mưa lấy từ Open-Meteo Ensemble, đã hiệu chỉnh theo số Google nhập tay và
    cảm biến mưa của trạm.
  - `rain_source = "lightgbm"`: không lấy được ensemble nên dùng mô hình dự phòng.

## Độ tin cậy

| Cơ chế            | Cách làm                                                                                                                                                                                                 |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Phát hiện offline | LWT: broker gửi `{"state":"offline"}` (QoS 1, retain) khi trạm rớt mạng → backend đánh dấu offline và tạo cảnh báo `device_offline`. Backend cũng đánh dấu offline nếu quá 60 s không nhận được dữ liệu. |
| Giữ kết nối       | Keep-alive 15 s. Rớt kết nối thì thử lại sau 2 s, mỗi lần thất bại gấp đôi thời gian chờ, tối đa 30 s.                                                                                                   |
| Mã hoá (tuỳ chọn) | TLS cổng 8883: chạy `python broker/mosquitto/gen_certs.py`, chép `ca.crt` lên board, đặt `MQTT_CA_FILE = "ca.crt"` và `MQTT_PORT = 8883` trong `firmware/src/credentials.py`.                            |

## Kết quả đo tải

Broker chạy local, 50 thiết bị giả lập gửi 1 bản tin/giây, QoS 1:

- Mất gói 0 %, 100 % bản ghi vào CSDL.
- Độ trễ broker P95 ≈ 2 ms.

Số liệu đầy đủ ở `docs/report/results_load_20.md`, `results_load_50.md` và `results_load_50_docker.md`.
