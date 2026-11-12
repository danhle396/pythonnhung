# Cấu hình trạm AIoT VKU (MicroPython). Thông tin Wi-Fi/MQTT nằm trong credentials.py (không đưa lên git).
FW_VERSION = "2.0.0"
DEVICE_ID = "station01"
TOPIC_PREFIX = "vku/aiot/"

# ---- Vị trí trạm (task.md 1.3) — VKU, 470 Trần Đại Nghĩa, Ngũ Hành Sơn, Đà Nẵng
STATION_LAT = 15.975
STATION_LON = 108.253
STATION_ALT_M = 8.0
TZ_HOURS = 7  # Asia/Ho_Chi_Minh, không có giờ mùa hè
NTP_SERVERS = ("pool.ntp.org", "time.google.com", "vn.pool.ntp.org")

# ---- Sơ đồ chân (task.md 2.2). Chân analog chỉ dùng ADC1 (GPIO32–39) vì ADC2 xung đột Wi-Fi.
PIN_I2C_SDA = 21
PIN_I2C_SCL = 22
PIN_DHT = 4
PIN_RAIN_AO = 34
PIN_RAIN_DO = 35
PIN_RAIN_PWR = 18  # cấp nguồn YL-83 chỉ khi đọc để giảm ăn mòn
PIN_MQ2_AO = 32    # qua cầu phân áp 10k/20k (5 V -> 3.33 V)
PIN_MQ2_DO = 33
PIN_BUZZER = 25
PIN_LED_GREEN = 26
PIN_LED_YELLOW = 27
PIN_LED_RED = 14
PIN_RELAY = 23
# GPIO13: để trống (không dùng nút tắt còi — tắt còi bằng lệnh mute trên dashboard)

# ---- Màn hình TFT 1.8" ST7735S 128x160, SPI chỉ ghi (bus HSPI = SPI(1)). Khe thẻ SD không dùng.
# Chân module: VCC GND CS RESET A0 SDA SCK LED. RESET nối EN của ESP32; VCC và LED nối 3V3.
PIN_TFT_CS = 5
PIN_TFT_DC = 16    # A0 — trên DevKit V1 in là RX2
PIN_TFT_MOSI = 17  # SDA — trên DevKit V1 in là TX2
PIN_TFT_SCK = 19
TFT_SPI_ID = 1     # HSPI
TFT_SPI_HZ = 20000000
# Màn trắng/sai màu/lệch viền -> đổi "black" thành "green" hoặc "red" (loại tab của module).
TFT_TAB = "black"
TFT_ROTATION = 1   # nằm ngang 160x128; ảnh bị ngược -> đặt 3

# ---- Phần cứng thực tế của nhóm (đổi True/False cho khớp linh kiện đang có)
HAS_LED_YELLOW = False    # không có LED vàng -> cấp 1 "Chú ý" = LED xanh nhấp nháy 1 Hz
HAS_RELAY = False         # không có module relay/quạt -> GPIO23 bỏ trống
BUZZER_ACTIVE_LOW = False # True: module còi 3 chân kêu khi I/O = LOW

# ---- Địa chỉ I2C
BMP280_ADDR = 0x76
BH1750_ADDR = 0x23

# ---- MQ-2
MQ2_RL_KOHM = 5.0           # điện trở tải trên module (đo lại: nhiều module dùng 1k hoặc 5k)
MQ2_VC = 5.0                # điện áp cấp cho cảm biến
MQ2_DIVIDER = 2.0 / 3.0     # cầu phân áp 10k/20k
MQ2_R0_DEFAULT_KOHM = 10.0  # ghi đè bằng lệnh calibrate (lưu /config.json)
MQ2_CLEAN_AIR_RATIO = 9.83
MQ2_CURVE_A = 574.25        # ppm = A·(Rs/R0)^B — đường cong LPG trong datasheet
MQ2_CURVE_B = -2.222
MQ2_WARMUP_S = 60

# ---- YL-83: ADC càng thấp càng ướt. Theo số đo cảm biến của nhóm (12/11/2026, nguồn 3,3 V):
#   khô: 3126–3134 mV (trần ADC) · vài giọt nước: 2853–3074 mV  => chỉ cần dính nước là < 3100 mV.
#   Mức 2/3 tạm đặt, chỉnh lại sau khi đo lúc tấm ướt đẫm (task.md 2.3).
RAIN_MV_DRY = 3100       # >= ngưỡng này mới là "Khô"
RAIN_MV_DRIZZLE = 2600   # [2600, 3100) mưa phùn
RAIN_MV_MODERATE = 1800  # [1800, 2600) mưa vừa; < 1800 mưa to
RAIN_HOLD_READS = 3      # giữ mức mưa cao nhất trong 3 lần đọc gần nhất (30 s)

# ---- Chu kỳ (ms)
SENSOR_PERIOD_MS = 1000
DHT_PERIOD_MS = 2000
RAIN_PERIOD_MS = 10000
TELEMETRY_PERIOD_MS = 10000
TELEMETRY_ALERT_PERIOD_MS = 1000
STATUS_PERIOD_MS = 60000
NOWCAST_SAMPLE_MS = 600000  # 1 mẫu áp suất / 10 phút
MUTE_DURATION_MS = 300000   # tắt còi 5 phút
DISPLAY_PERIOD_MS = 500
WDT_TIMEOUT_MS = 30000
NET_STALL_MS = 60000        # luồng mạng im lặng quá lâu -> không cho chó canh -> khởi động lại

# ---- Ngưỡng mặc định (ghi đè được qua topic config, lưu /config.json)
DEF_TH1_PPM = 300.0
DEF_TH2_PPM = 1000.0
DEF_TH3_PPM = 2000.0
DEF_SLOPE1 = 15.0
DEF_DTEMP3 = 1.0
DEF_HYST = 0.15
DEF_DEBOUNCE_UP = 3
DEF_DEBOUNCE_DOWN = 5

# ---- Đệm offline
OFFLINE_MAX_RECORDS = 2000
OUTBOX_MAX = 20  # hàng đợi giữa luồng chính và luồng mạng
