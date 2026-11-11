// Edge AI cảnh báo khí/khói: chuyển đổi MQ-2, trích feature cửa sổ trượt, model cây (gas_model.h; khi
// GAS_MODEL_AVAILABLE = 0 — chưa có dữ liệu đo thật để huấn luyện — chỉ chạy rule engine),
// debounce model, hợp nhất với rule engine, phát hiện lỗi cảm biến. Thuần C++ (test được trên PC).
// Feature và công thức GIỐNG HỆT ml/src/gas_edge.py.
#pragma once
#include <stdint.h>
#include "alert.h"
#include "filters.h"

#define EDGE_N_FEATURES 10

struct Mq2Params {
  float rlKohm = 5.0f, vc = 5.0f, divider = 2.0f / 3.0f, r0Kohm = 10.0f;
  float curveA = 574.25f, curveB = -2.222f;
};

// Từ điện áp ADC (mV, sau phân áp) -> Rs/R0 và ppm LPG
struct Mq2Reading { float vout, rs, ratio, ppm; };
Mq2Reading mq2Convert(float adcMv, const Mq2Params& p);
// R0 = Rs_không_khí_sạch / 9.83
float mq2CalibrateR0(float rsCleanKohm, float cleanAirRatio = 9.83f);

class FeatureExtractor {
 public:
  // trả về con trỏ tới mảng EDGE_N_FEATURES phần tử
  const float* update(float ppm, float rsR0, float temp, float hum, float lux);
  const float* features() const { return f_; }
  float baseline() const { return baseline_; }

 private:
  RingBuffer<30> ppm_;
  RingBuffer<60> temp_, hum_;
  bool init_ = false, luxInit_ = false;
  float baseline_ = 0, luxBase_ = 0;
  float f_[EDGE_N_FEATURES] = {0};
};

class ModelLevelFilter {
 public:
  ModelLevelFilter(int nUp = 3, int nDown = 5) : nUp_(nUp), nDown_(nDown) {}
  int update(int raw);
  int level() const { return level_; }

 private:
  int nUp_, nDown_, level_ = 0, upCnt_ = 0, downCnt_ = 0, cand_ = 0;
};

// Phát hiện lỗi MQ-2: giá trị đứng yên (stuck), mất kết nối (0 mV), bão hoà ADC.
enum class SensorFault : uint8_t { NONE = 0, STUCK = 1, DISCONNECTED = 2, SATURATED = 3 };
class Mq2FaultDetector {
 public:
  SensorFault update(float adcMv);
  SensorFault fault() const { return fault_; }

 private:
  float last_ = -1;
  uint32_t same_ = 0, low_ = 0, high_ = 0;
  SensorFault fault_ = SensorFault::NONE;
};

struct EdgeInput { float ppm, rsR0, temp, hum, lux; bool gasOk; };
struct EdgeOutput {
  int level = 0, ruleLevel = 0, modelLevel = 0;
  float score = 0;      // 1 − P(Normal)
  uint32_t cause = 0;
  bool warmingUp = true;
  const float* f = nullptr;
};

enum class EdgeMode : uint8_t { RULE = 0, MODEL = 1, HYBRID = 2 };

class EdgeAI {
 public:
  EdgeOutput step(const EdgeInput& in);
  RuleEngine rules;
  EdgeMode mode = EdgeMode::HYBRID;
  uint32_t warmupSamples = 60;
  uint32_t samples() const { return t_; }
  float lastInferenceUs = 0;

 private:
  FeatureExtractor fx_;
  ModelLevelFilter mf_;
  uint32_t t_ = 0;
};
