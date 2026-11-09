// OLED SSD1306 128x64: 3 trang luân phiên, trang cảnh báo luôn ưu tiên khi cấp ≥ 2.
#pragma once
#include <Arduino.h>
#include "nowcast.h"
#include "sensors.h"

struct DisplayState {
  SensorData s;
  int level = 0;
  bool muted = false, wifi = false, mqtt = false, warmingUp = true;
  float score = 0;
  Nowcast nc;
  char cloudForecast[64] = "";
};

class Display {
 public:
  bool begin();
  void render(const DisplayState& st);

 private:
  bool ok_ = false;
  uint8_t page_ = 0;
  uint32_t lastFlip_ = 0;
};
