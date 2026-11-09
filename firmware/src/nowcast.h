// Nowcast thời tiết tại edge kiểu Zambretti: xu hướng áp suất 3h + mưa + độ ẩm. Thuần C++.
#pragma once
#include <stdint.h>
#include "filters.h"

enum class PressureTrend : int8_t { Falling = -1, Steady = 0, Rising = 1, Unknown = 2 };
enum class NowcastCode : uint8_t { FINE = 0, POSSIBLE_RAIN = 1, RAIN_SOON = 2, RAINING = 3, UNKNOWN = 4 };

struct Nowcast {
  PressureTrend trend = PressureTrend::Unknown;
  float trend3h = 0;       // hPa / 3h
  char zambretti = '?';    // A..Z
  int zNumber = 0;
  NowcastCode code = NowcastCode::UNKNOWN;
  const char* text = "Chua du du lieu";       // ASCII cho OLED
  const char* textVi = "Chưa đủ dữ liệu";     // UTF-8 cho MQTT
};

class NowcastEngine {
 public:
  // gọi mỗi 10 phút với áp suất quy về mực nước biển (hPa)
  void addPressure(float pMsl) { hist_.push(pMsl); }
  Nowcast compute(int rainLevel, float hum, int month) const;
  size_t samples() const { return hist_.size(); }
  static constexpr float TREND_THRESHOLD = 1.6f;  // hPa / 3h

 private:
  RingBuffer<19> hist_;  // 19 mẫu × 10 phút = 3 giờ
};

char zambrettiLetter(float pMsl, PressureTrend trend, int month, int* zOut);
