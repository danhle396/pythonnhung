# Thiết kế MQTT

Broker: Mosquitto 2.x (`broker/mosquitto/`). Xác thực username/password, ACL theo thiết bị
(username = `device_id`; thiết bị chỉ ghi topic của chính nó). Tiền tố topic: `vku/aiot/{device_id}/`.

## Topic

| Topic | Chiều | QoS | Retain | Tần suất | Nội dung |
|---|---|---|---|---|---|
| `…/telemetry` | Edge → Cloud | 0* | ❌ | 10 s (1 s khi cấp ≥ 1) | Dữ liệu cảm biến + kết quả edge AI |
| `…/alert` | Edge → Cloud | 0* | ❌ | khi đổi cấp / lỗi cảm biến | Sự kiện cảnh báo khí/khói, `sensor_fault` |
| `…/nowcast` | Edge → Cloud | 0 | ✅ | 10 phút | Nowcast Zambretti tại edge |
| `…/status` | Edge → Cloud | 1 (LWT) | ✅ | 60 s + khi kết nối | `online` + RSSI, uptime, heap; LWT `{"state":"offline"}` |
| `…/forecast` | Cloud → Edge | 1 | ✅ | 10 phút | Dự báo 1h/3h/6h + `summary` ASCII cho màn TFT |
| `…/cmd` | Cloud → Edge | 1 | ❌ | theo yêu cầu | `mute`, `test_alarm`, `calibrate`, `reboot`, `escalate` |
| `…/config` | Cloud → Edge | 1 | ✅ | khi đổi | Ngưỡng, chu kỳ, chế độ edge, R0, `version` |
| `…/ack` | Edge → Cloud | 0* | ❌ | sau cmd/config | Xác nhận đã nhận/áp dụng |

\* PubSubClient trên ESP32 chỉ publish được QoS 0. Độ tin cậy "ít nhất một lần" được bảo đảm ở tầng ứng dụng:
mỗi bản ghi có `seq` tăng dần (lưu NVS), khi publish thất bại bản ghi vào đệm offline LittleFS (2000 bản ghi) và
được gửi bù khi kết nối lại; backend chống trùng theo `(device_id, ts, seq)`. Simulator và backend dùng QoS 1 thật.

## Payload

### telemetry
```json
{"device_id":"station01","ts":1762671600,"seq":10234,
 "temp_dht":29.4,"hum":78.2,"temp_bmp":29.9,"pressure":1008.6,"pressure_msl":1009.5,
 "lux":15230,"dew_point":25.1,"heat_index":34.2,"rain_raw":3810,"rain_level":0,
 "gas_raw":812,"gas_rs_r0":7.9,"gas_ppm":210,"gas_slope":0.4,
 "edge_risk":0,"edge_score":0.03,"warming_up":false,
 "sensor_ok":{"dht":true,"bmp":true,"bh":true,"rain":true,"gas":true},
 "fw":"1.0.0","model_ver":"gas-v1"}
```
Giá trị lỗi gửi `null`. Backend loại giá trị ngoài dải vật lý (T −10..60 °C, P 900..1100 hPa, RH 0..100 %…) và lưu
danh sách bị loại vào cột `extra.rejected`.

### alert
```json
{"device_id":"station01","ts":1762671620,"seq":10240,"type":"gas",
 "level":2,"prev_level":1,"level_name":"warning","cause":["gas_ppm>1000","model"],
 "gas_ppm":1350,"score":0.87,"rule_level":2,"model_level":2,
 "action":["led_red_blink","buzzer_intermittent","fan_on"],"edge_latency_ms":3}
```
`type`: `gas` | `sensor_fault` (`fault`: 1 stuck, 2 mất kết nối, 3 bão hoà) | `test`.
Backend tự tạo thêm `device_offline` và `anomaly` (source = `cloud`).

### status / nowcast / ack
```json
{"state":"online","device_id":"station01","rssi":-61,"uptime_s":86400,"free_heap":182000,
 "reconnects":3,"offline_pending":0,"fw":"1.0.0","model_ver":"gas-v1","inference_us":42.1}
{"device_id":"station01","ts":1762671600,"code":1,"text":"Có thể mưa","trend":-1,"trend_3h":-2.1,"zambretti":"R"}
{"device_id":"station01","ts":1762671630,"ref":"cmd","id":"<uuid>","ok":true,"msg":"mute"}
```

### cmd / config / forecast
```json
{"cmd":"escalate","id":"<uuid>","level":3}
{"version":4,"th1":300,"th2":1000,"th3":2000,"slope1":15,"dtemp3":1.0,"hyst":0.15,
 "debounce_up":3,"debounce_down":5,"telemetry_ms":10000,"mode":"hybrid","r0_kohm":10.2}
{"device_id":"station01","ts":1762671600,"source":"station","summary":"1h 28.8C 3h 28.0C Mua3h 11%",
 "items":[{"target":"temp","h":1,"value":28.83,"lower":27.97,"upper":29.70,"model_ver":"fc-temp_1h-..."}]}
```
Thiết bị kiểm tra hợp lệ config (th1 < th2 < th3, dải giá trị) trước khi áp dụng và lưu NVS; config không hợp lệ
bị từ chối bằng `ack` với `ok:false`.

## Độ tin cậy
- **LWT**: `…/status` = `{"state":"offline"}`, QoS 1, retain — backend đánh dấu offline + tạo alert `device_offline`.
- Backend còn đánh dấu offline nếu > 60 s không nhận dữ liệu.
- Keep-alive 15 s, kết nối lại với exponential backoff 2 → 30 s.
- (Nâng cao) TLS cổng 8883: `broker/mosquitto/gen_certs.sh`, bật `MQTT_USE_TLS` + `MQTT_CA_CERT` trong `secrets.h`.

## Kết quả đo (load test, broker local)
Xem `docs/report/results_load_20.md`, `results_load_50.md`: 50 thiết bị × 1 msg/s, QoS 1 — mất gói 0 %,
độ trễ broker P95 ≈ 2 ms, 100 % bản ghi vào DB.
