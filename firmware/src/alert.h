// Rule engine cảnh báo khí 4 cấp + quản lý hành động (còi/LED/relay/mute). Thuần C++, test được trên PC.
// Logic GIỐNG HỆT ml/src/gas_edge.py (RuleEngine) để bản Python dùng khi huấn luyện/đánh giá phản ánh đúng thiết bị.
#pragma once
#include <stdint.h>

enum CauseBits : uint32_t {
  CAUSE_PPM_TH1 = 1u << 0,
  CAUSE_SLOPE = 1u << 1,
  CAUSE_PPM_TH2 = 1u << 2,
  CAUSE_PPM_TH3 = 1u << 3,
  CAUSE_TEMP_RISING = 1u << 4,
  CAUSE_MODEL = 1u << 5,
  CAUSE_SENSOR_FAULT = 1u << 6,
  CAUSE_CLOUD = 1u << 7,
  CAUSE_TEST = 1u << 8,
};

struct RuleConfig {
  float th1 = 300.0f, th2 = 1000.0f, th3 = 2000.0f;
  float slope1 = 15.0f;   // ppm/s
  float dtemp3 = 1.0f;    // °C/phút
  float hyst = 0.15f;
  int debounceUp = 3, debounceDown = 5;
};

class RuleEngine {
 public:
  explicit RuleEngine(const RuleConfig& c = RuleConfig()) : cfg(c) {}
  int rawLevel(float ppm, float slope, float dtemp, float scale, uint32_t* cause) const;
  int update(float ppm, float slope, float dtemp);
  int level() const { return level_; }
  uint32_t cause() const { return cause_; }
  void reset() { level_ = upCnt_ = downCnt_ = 0; cause_ = 0; }
  RuleConfig cfg;

 private:
  int level_ = 0, upCnt_ = 0, downCnt_ = 0;
  uint32_t cause_ = 0;
};

enum class LedMode : uint8_t { GREEN, YELLOW, RED_BLINK, RED_SOLID, OFF };
enum class BuzzerMode : uint8_t { OFF, INTERMITTENT, CONTINUOUS };

struct Actions {
  LedMode led = LedMode::GREEN;
  BuzzerMode buzzer = BuzzerMode::OFF;
  bool relay = false;
  bool levelChanged = false;
  int level = 0, prevLevel = 0;
  bool muted = false;
};

// Quản lý cấp cảnh báo đầu ra + nút mute (task.md 6.3): mute tắt còi 5 phút nhưng giữ cấp và LED;
// nếu cấp tăng thêm thì còi kêu lại. Cloud có thể nâng cấp (cmd escalate) — không bao giờ hạ cấp edge.
class AlertManager {
 public:
  explicit AlertManager(uint32_t muteMs = 300000) : muteMs_(muteMs) {}
  Actions update(int level, uint32_t nowMs);
  void pressMute(uint32_t nowMs);
  void cloudEscalate(int level, uint32_t nowMs, uint32_t holdMs = 60000);
  void testAlarm(uint32_t nowMs, uint32_t durMs = 3000) { testUntil_ = nowMs + durMs; }
  int level() const { return level_; }

 private:
  uint32_t muteMs_;
  int level_ = 0;
  int mutedLevel_ = -1;
  uint32_t mutedUntil_ = 0;
  int cloudLevel_ = 0;
  uint32_t cloudUntil_ = 0;
  uint32_t testUntil_ = 0;
};

static inline bool timeBefore(uint32_t now, uint32_t until) { return (int32_t)(until - now) > 0; }
