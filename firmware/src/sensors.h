// Driver cảm biến: DHT22, BMP280, BH1750, YL-83, MQ-2 — có xử lý lỗi và cờ sensor_ok.
#pragma once
#include <Arduino.h>
#include "config.h"
#include "edge_ai.h"
#include "filters.h"

struct SensorData {
  uint32_t ts = 0;            // epoch (s), 0 nếu chưa có NTP
  float tempDht = NAN, hum = NAN, tempBmp = NAN, pressure = NAN, pressureMsl = NAN, lux = NAN;
  float temp = NAN;           // nhiệt độ dùng chung: DHT22, dự phòng BMP280
  float dew = NAN, heatIndex = NAN;
  int rainMv = -1, rainLevel = 0;
  float gasMv = NAN;
  Mq2Reading mq2 = {0, 0, 0, 0};
  bool dhtOk = false, bmpOk = false, bhOk = false, rainOk = false, gasOk = false;
  SensorFault gasFault = SensorFault::NONE;
};

class Sensors {
 public:
  bool begin();
  // gọi mỗi giây; tự đọc DHT22 mỗi 2 giây và YL-83 mỗi 10 giây
  void read(SensorData& d);
  Mq2Params mq2;
  // đo Rs trung bình trong không khí sạch để tính R0 mới (lệnh calibrate)
  float calibrateR0(uint16_t samples = 50);
  bool scanI2C(uint8_t addr);

 private:
  float readMv(int pin, int n = 16);
  int rainLevelFromMv(int mv);
  uint32_t lastDht_ = 0, lastRain_ = 0;
  SensorFilter fTemp_{0.3f}, fHum_{0.3f}, fTempBmp_{0.25f}, fPres_{0.25f}, fLux_{0.3f}, fGas_{0.3f};
  Mq2FaultDetector gasFault_;
  float lastTempDht_ = NAN, lastHum_ = NAN;
  int lastRainMv_ = -1, lastRainLevel_ = 0;
  uint8_t rainHist_[RAIN_HOLD_READS] = {0};  // mức mưa các lần đọc gần nhất (giữ trạng thái ướt)
  uint8_t rainIdx_ = 0;
  uint8_t dhtFails_ = 0;
};
