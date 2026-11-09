#include "nowcast.h"

// Bảng Zambretti (Negretti & Zambra, 1915) theo số Z:
//   giảm  : Z = 127 − 0.12·P  (1..9)
//   ổn định: Z = 144 − 0.13·P  (10..19)
//   tăng  : Z = 185 − 0.16·P  (20..32)
static const char FALLING_MAP[] = "ABDHORUVX";        // Z 1..9
static const char STEADY_MAP[] = "ABEKNPSWXZ";        // Z 10..19
static const char RISING_MAP[] = "ABCFGIJLMQTYZ";     // Z 20..32

char zambrettiLetter(float p, PressureTrend trend, int month, int* zOut) {
  int z;
  const char* map;
  int lo, n;
  if (trend == PressureTrend::Falling) { z = (int)(127.0f - 0.12f * p + 0.5f); map = FALLING_MAP; lo = 1; n = 9; }
  else if (trend == PressureTrend::Rising) { z = (int)(185.0f - 0.16f * p + 0.5f); map = RISING_MAP; lo = 20; n = 13; }
  else { z = (int)(144.0f - 0.13f * p + 0.5f); map = STEADY_MAP; lo = 10; n = 10; }
  // hiệu chỉnh mùa: Đà Nẵng mùa mưa tháng 9–12 -> nghiêng về kém ổn định
  if (month >= 9 && month <= 12 && trend != PressureTrend::Rising) z += 1;
  int idx = z - lo;
  if (idx < 0) idx = 0;
  if (idx >= n) idx = n - 1;
  if (zOut) *zOut = lo + idx;
  return map[idx];
}

Nowcast NowcastEngine::compute(int rainLevel, float hum, int month) const {
  Nowcast nc;
  if (rainLevel >= 1) {
    nc.code = NowcastCode::RAINING;
    nc.text = "Dang mua";
    nc.textVi = "Đang mưa";
  }
  if (hist_.size() < 7) return nc;  // cần ít nhất 1 giờ dữ liệu
  // quy đổi xu hướng về 3 giờ nếu chưa đủ 3 giờ
  float span_h = (hist_.size() - 1) / 6.0f;
  nc.trend3h = (hist_.last() - hist_.at(0)) * 3.0f / span_h;
  nc.trend = nc.trend3h <= -TREND_THRESHOLD ? PressureTrend::Falling
           : nc.trend3h >= TREND_THRESHOLD ? PressureTrend::Rising : PressureTrend::Steady;
  nc.zambretti = zambrettiLetter(hist_.last(), nc.trend, month, &nc.zNumber);
  char c = nc.zambretti;
  NowcastCode code = (c <= 'D' || c == 'F') ? NowcastCode::FINE : (c <= 'Q' ? NowcastCode::POSSIBLE_RAIN : NowcastCode::RAIN_SOON);
  if (hum >= 90.0f && code == NowcastCode::POSSIBLE_RAIN) code = NowcastCode::RAIN_SOON;
  if (hum >= 85.0f && nc.trend == PressureTrend::Falling && code == NowcastCode::FINE) code = NowcastCode::POSSIBLE_RAIN;
  if (rainLevel >= 1) code = NowcastCode::RAINING;
  nc.code = code;
  switch (code) {
    case NowcastCode::FINE: nc.text = "Troi dep"; nc.textVi = "Trời đẹp"; break;
    case NowcastCode::POSSIBLE_RAIN: nc.text = "Co the mua"; nc.textVi = "Có thể mưa"; break;
    case NowcastCode::RAIN_SOON: nc.text = "Mua sap toi"; nc.textVi = "Mưa sắp tới"; break;
    case NowcastCode::RAINING: nc.text = "Dang mua"; nc.textVi = "Đang mưa"; break;
    default: break;
  }
  return nc;
}
