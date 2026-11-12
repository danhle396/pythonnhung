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
  const char* text = "Chua du du lieu";       // ASCII cho màn hình TFT
  const char* textVi = "Chưa đủ dữ liệu";     // UTF-8 cho MQTT
};

// Lưu tối đa 19 mẫu (3 giờ × 1 mẫu / 10 phút) kèm giờ đo (epoch, 0 = chưa có NTP).
// Có giờ đo -> xu hướng tính theo khoảng thời gian thật, nạp lại được mẫu đã lưu sau khi khởi động lại.
class NowcastEngine {
 public:
  static constexpr size_t N = 19;
  static constexpr uint32_t STEP_S = 600;                 // 1 mẫu / 10 phút
  static constexpr uint32_t WINDOW_S = 3 * 3600 + 300;    // giữ mẫu trong 3 giờ (+5 phút dung sai)
  static constexpr float TREND_THRESHOLD = 1.6f;          // hPa / 3h

  // gọi mỗi 10 phút với áp suất quy về mực nước biển (hPa) và giờ đo (0 nếu chưa có NTP)
  void addPressure(float pMsl, uint32_t ts = 0);
  Nowcast compute(int rainLevel, float hum, int month) const;
  size_t samples() const { return n_; }
  // mọi mẫu đều có giờ đo
  bool timed() const;
  // khoảng thời gian dữ liệu đang có (giờ)
  float spanHours() const;
  // Vừa có NTP: gán giờ cho các mẫu chưa có giờ (lấy đều 10 phút), mẫu mới nhất đo lúc newestTs.
  void assignTimes(uint32_t newestTs);
  // Nạp lại mẫu đã lưu từ trước khi khởi động lại: bỏ mẫu ngoài 3 giờ tính tới nowTs, gộp với mẫu hiện có theo thời gian.
  void restore(const float* p, const uint32_t* t, size_t n, uint32_t nowTs);
  // Xuất các mẫu có giờ đo (cũ -> mới) để lưu; trả về số mẫu.
  size_t exportSamples(float* p, uint32_t* t) const;

 private:
  float p_[N] = {0};
  uint32_t t_[N] = {0};
  size_t n_ = 0;  // mẫu xếp từ cũ (0) đến mới (n_-1)
  void push(float p, uint32_t t);
  void prune(uint32_t newestTs);
};

char zambrettiLetter(float pMsl, PressureTrend trend, int month, int* zOut);
