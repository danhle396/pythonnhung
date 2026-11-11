// Cấu hình trạm AIoT VKU. Thông tin Wi-Fi/MQTT nằm trong secrets.h (không đưa lên git).
#pragma once

#define FW_VERSION "1.0.0"
#define DEVICE_ID "station01"
#define TOPIC_PREFIX "vku/aiot/"

// ---- Vị trí trạm (task.md 1.3) — VKU, 470 Trần Đại Nghĩa, Ngũ Hành Sơn, Đà Nẵng
#define STATION_LAT 15.975f
#define STATION_LON 108.253f
#define STATION_ALT_M 8.0f
#define TZ_INFO "<+07>-7"  // Asia/Ho_Chi_Minh, không có giờ mùa hè
#define NTP_SERVER "pool.ntp.org"

// ---- Sơ đồ chân (task.md 2.2). Chân analog chỉ dùng ADC1 (GPIO32–39) vì ADC2 xung đột Wi-Fi.
#define PIN_I2C_SDA 21
#define PIN_I2C_SCL 22
#define PIN_DHT 4
#define PIN_RAIN_AO 34
#define PIN_RAIN_DO 35
#define PIN_RAIN_PWR 18  // cấp nguồn YL-83 chỉ khi đọc để giảm ăn mòn
#define PIN_MQ2_AO 32    // qua cầu phân áp 10k/20k (5 V -> 3.33 V)
#define PIN_MQ2_DO 33
#define PIN_BUZZER 25
#define PIN_LED_GREEN 26
#define PIN_LED_YELLOW 27
#define PIN_LED_RED 14
#define PIN_BUTTON 13    // INPUT_PULLUP, nhấn = LOW
#define PIN_RELAY 23

// ---- Phần cứng thực tế của nhóm (đổi 0/1 cho khớp linh kiện đang có)
#ifndef HAS_LED_YELLOW
#define HAS_LED_YELLOW 0     // 0: không có LED vàng -> cấp 1 "Chú ý" = LED xanh nhấp nháy chậm (1 Hz)
#endif
#ifndef HAS_RELAY
#define HAS_RELAY 0          // 0: không có module relay/quạt -> GPIO23 bỏ trống
#endif
#ifndef BUZZER_ACTIVE_LOW
#define BUZZER_ACTIVE_LOW 0  // 1: module còi 3 chân kêu khi I/O = LOW (loại "low level trigger")
#endif

// ---- Địa chỉ I2C
#define BMP280_ADDR 0x76
#define BH1750_ADDR 0x23
#define OLED_ADDR 0x3C

// ---- MQ-2
#define MQ2_RL_KOHM 5.0f         // điện trở tải trên module (đo lại: nhiều module dùng 1k hoặc 5k)
#define MQ2_VC 5.0f              // điện áp cấp cho cảm biến
#define MQ2_DIVIDER (2.0f / 3.0f) // cầu phân áp 10k/20k
#define MQ2_R0_DEFAULT_KOHM 10.0f // ghi đè bằng lệnh calibrate (lưu NVS)
#define MQ2_CLEAN_AIR_RATIO 9.83f
#define MQ2_CURVE_A 574.25f      // ppm = A·(Rs/R0)^B — đường cong LPG trong datasheet
#define MQ2_CURVE_B -2.222f
#define MQ2_WARMUP_S 60

// ---- YL-83: ADC càng thấp càng ướt. Hiệu chuẩn lại theo task.md 2.3.
#define RAIN_MV_DRY 2800
#define RAIN_MV_DRIZZLE 2200
#define RAIN_MV_MODERATE 1400

// ---- Chu kỳ
#define SENSOR_PERIOD_MS 1000
#define DHT_PERIOD_MS 2000
#define TELEMETRY_PERIOD_MS 10000
#define TELEMETRY_ALERT_PERIOD_MS 1000
#define STATUS_PERIOD_MS 60000
#define NOWCAST_SAMPLE_MS 600000  // 1 mẫu áp suất / 10 phút
#define MUTE_DURATION_MS 300000   // tắt còi 5 phút
#define WDT_TIMEOUT_S 30

// ---- Ngưỡng mặc định (ghi đè được qua topic config, lưu NVS)
#define DEF_TH1_PPM 300.0f
#define DEF_TH2_PPM 1000.0f
#define DEF_TH3_PPM 2000.0f
#define DEF_SLOPE1 15.0f
#define DEF_DTEMP3 1.0f
#define DEF_HYST 0.15f
#define DEF_DEBOUNCE_UP 3
#define DEF_DEBOUNCE_DOWN 5

// ---- Đệm offline
#define OFFLINE_MAX_RECORDS 2000
#define OFFLINE_FILE "/offline.jsonl"
