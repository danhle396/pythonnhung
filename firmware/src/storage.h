// Đệm offline trên LittleFS (vòng đệm ~2000 bản ghi bằng 2 file luân phiên) + lưu cấu hình vào NVS.
#pragma once
#include <Arduino.h>
#include <functional>

#include "alert.h"

struct DeviceConfig {
  RuleConfig rule;
  float r0Kohm = 10.0f;
  uint32_t telemetryMs = 10000;
  uint8_t edgeMode = 2;  // 0 rule, 1 model, 2 hybrid
  uint32_t version = 0;
};

class Storage {
 public:
  bool begin();
  // ghi 1 dòng (topic \t payload) vào đệm offline
  bool append(const char* topic, const char* payload);
  // gửi bù: gọi fn cho từng bản ghi cũ -> mới; dừng nếu fn trả false. Trả về số bản ghi đã gửi.
  size_t replay(const std::function<bool(const String&, const String&)>& fn, size_t maxRecords = 200);
  size_t pending() const { return countA_ + countB_; }

  void loadConfig(DeviceConfig& c);
  void saveConfig(const DeviceConfig& c);
  uint32_t nextSeq();

 private:
  bool ok_ = false;
  size_t countA_ = 0, countB_ = 0;  // A = file cũ, B = file đang ghi
  size_t countLines(const char* path);
};
