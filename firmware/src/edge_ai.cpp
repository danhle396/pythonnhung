#include "edge_ai.h"

#include <math.h>

#include "gas_model.h"

#if defined(ARDUINO)
#include <Arduino.h>
static inline uint32_t nowUs() { return micros(); }
#else
#include <chrono>
static inline uint32_t nowUs() {
  return (uint32_t)std::chrono::duration_cast<std::chrono::microseconds>(
             std::chrono::steady_clock::now().time_since_epoch()).count();
}
#endif

static_assert(GAS_MODEL_N_FEATURES == EDGE_N_FEATURES, "gas_model.h không khớp số feature của edge_ai");

Mq2Reading mq2Convert(float adcMv, const Mq2Params& p) {
  Mq2Reading r;
  float v = adcMv / 1000.0f / p.divider;  // điện áp thật ở chân AO
  if (v < 0.001f) v = 0.001f;
  if (v > p.vc - 0.001f) v = p.vc - 0.001f;
  r.vout = v;
  r.rs = p.rlKohm * (p.vc - v) / v;  // Rs = RL·(Vc − Vout)/Vout
  r.ratio = r.rs / p.r0Kohm;
  if (r.ratio < 1e-3f) r.ratio = 1e-3f;
  r.ppm = p.curveA * powf(r.ratio, p.curveB);  // ppm = A·(Rs/R0)^B
  return r;
}

float mq2CalibrateR0(float rsClean, float cleanAirRatio) { return rsClean / cleanAirRatio; }

const float* FeatureExtractor::update(float ppm, float rsR0, float temp, float hum, float lux) {
  ppm_.push(ppm);
  temp_.push(temp);
  hum_.push(hum);
  if (!luxInit_) { luxBase_ = lux; luxInit_ = true; }
  float luxRel = (lux - luxBase_) / (luxBase_ + 10.0f);
  if (fabsf(luxRel) < 0.08f) luxBase_ += 0.005f * (lux - luxBase_);
  if (!init_) { baseline_ = ppm; init_ = true; }
  else if (fabsf(ppm - baseline_) < 100.0f) baseline_ += 0.005f * (ppm - baseline_);
  f_[0] = ppm;
  f_[1] = rsR0;
  f_[2] = ppm_.slope(10);
  f_[3] = ppm_.stdev();
  f_[4] = ppm - baseline_;
  f_[5] = temp;
  f_[6] = temp_.slope() * 60.0f;
  f_[7] = hum;
  f_[8] = hum_.slope() * 60.0f;
  f_[9] = luxRel;
  return f_;
}

int ModelLevelFilter::update(int raw) {
  if (raw > level_) {
    downCnt_ = 0;
    cand_ = (upCnt_ == 0) ? raw : (raw < cand_ ? raw : cand_);
    if (++upCnt_ >= nUp_) { level_ = cand_; upCnt_ = 0; }
  } else if (raw < level_) {
    upCnt_ = 0;
    if (++downCnt_ >= nDown_) { level_ = raw; downCnt_ = 0; }
  } else {
    upCnt_ = downCnt_ = 0;
  }
  return level_;
}

SensorFault Mq2FaultDetector::update(float mv) {
  same_ = (last_ >= 0 && fabsf(mv - last_) < 0.5f) ? same_ + 1 : 0;
  last_ = mv;
  low_ = (mv < 5.0f) ? low_ + 1 : 0;
  high_ = (mv > 3250.0f) ? high_ + 1 : 0;
  if (low_ >= 5) fault_ = SensorFault::DISCONNECTED;
  else if (high_ >= 5) fault_ = SensorFault::SATURATED;
  else if (same_ >= 300) fault_ = SensorFault::STUCK;  // tín hiệu MOS luôn có nhiễu; 5 phút y nguyên = bất thường
  else fault_ = SensorFault::NONE;
  return fault_;
}

EdgeOutput EdgeAI::step(const EdgeInput& in) {
  EdgeOutput o;
  ++t_;
  const float* f = fx_.update(in.ppm, in.rsR0, in.temp, in.hum, in.lux);
  o.f = f;
  o.ruleLevel = rules.update(f[0], f[2], f[6]);
  o.cause = rules.cause();
  if (mode != EdgeMode::RULE) {
    float p[GAS_MODEL_N_CLASSES];
    uint32_t t0 = nowUs();
    int k = gas_model_predict_proba(f, p);
    lastInferenceUs = (float)(nowUs() - t0);
    o.modelLevel = mf_.update(gas_model_class_label[k]);
    o.score = 1.0f - p[0];
  }
  o.warmingUp = t_ <= warmupSamples || !in.gasOk;
  if (o.warmingUp) { o.level = 0; return o; }
  switch (mode) {
    case EdgeMode::RULE: o.level = o.ruleLevel; break;
    case EdgeMode::MODEL: o.level = o.modelLevel; break;
    default: o.level = o.ruleLevel > o.modelLevel ? o.ruleLevel : o.modelLevel;  // model không hạ cấp rule
  }
  if (o.modelLevel > o.ruleLevel && mode != EdgeMode::RULE) o.cause |= CAUSE_MODEL;
  return o;
}
