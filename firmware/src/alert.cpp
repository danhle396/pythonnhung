#include "alert.h"

int RuleEngine::rawLevel(float ppm, float slope, float dtemp, float scale, uint32_t* cause) const {
  uint32_t c = 0;
  int lvl = 0;
  if (ppm >= cfg.th1 * scale) { lvl = 1; c |= CAUSE_PPM_TH1; }
  if (slope >= cfg.slope1 * scale) { if (lvl < 1) lvl = 1; c |= CAUSE_SLOPE; }
  if (ppm >= cfg.th2 * scale) { lvl = 2; c |= CAUSE_PPM_TH2; }
  if (ppm >= cfg.th3 * scale) { lvl = 3; c |= CAUSE_PPM_TH3; }
  else if (lvl >= 2 && dtemp >= cfg.dtemp3) { lvl = 3; c |= CAUSE_TEMP_RISING; }
  if (cause) *cause = c;
  return lvl;
}

int RuleEngine::update(float ppm, float slope, float dtemp) {
  uint32_t c = 0;
  int up = rawLevel(ppm, slope, dtemp, 1.0f, &c);
  if (up > level_) {
    downCnt_ = 0;
    if (up == 3) {  // cấp Nguy hiểm: tăng ngay, không debounce
      level_ = 3; upCnt_ = 0; cause_ = c;
    } else if (++upCnt_ >= cfg.debounceUp) {
      level_ = up; upCnt_ = 0; cause_ = c;
    }
    return level_;
  }
  upCnt_ = 0;
  int down = rawLevel(ppm, slope, dtemp, 1.0f - cfg.hyst, nullptr);
  if (down < level_) {
    if (++downCnt_ >= cfg.debounceDown) {
      level_ = down; downCnt_ = 0;
      if (down == 0) cause_ = 0;
    }
  } else {
    downCnt_ = 0;
  }
  return level_;
}

void AlertManager::pressMute(uint32_t nowMs) {
  if (level_ >= 1) {
    mutedLevel_ = level_;
    mutedUntil_ = nowMs + muteMs_;
  }
}

void AlertManager::cloudEscalate(int level, uint32_t nowMs, uint32_t holdMs) {
  cloudLevel_ = level;
  cloudUntil_ = nowMs + holdMs;
}

Actions AlertManager::update(int edgeLevel, uint32_t nowMs) {
  Actions a;
  int lvl = edgeLevel;
  if (timeBefore(nowMs, cloudUntil_) && cloudLevel_ > lvl) lvl = cloudLevel_;  // cloud chỉ được nâng cấp
  bool testing = timeBefore(nowMs, testUntil_);
  if (testing) lvl = 3;
  a.testing = testing;
  a.prevLevel = level_;
  a.levelChanged = (lvl != level_);
  level_ = lvl;
  a.level = lvl;
  // mute hết hạn hoặc cấp tăng vượt cấp đã mute -> còi kêu lại
  bool muted = mutedLevel_ >= 0 && timeBefore(nowMs, mutedUntil_) && lvl <= mutedLevel_ && !testing;
  if (!muted) mutedLevel_ = -1;  // hết hạn / cấp tăng / về 0 -> huỷ mute
  a.muted = muted;
  switch (lvl) {
    case 0: a.led = LedMode::GREEN; break;
    case 1: a.led = LedMode::YELLOW; break;
    case 2: a.led = LedMode::RED_BLINK; a.buzzer = BuzzerMode::INTERMITTENT; a.relay = true; break;
    default: a.led = LedMode::RED_SOLID; a.buzzer = BuzzerMode::CONTINUOUS; a.relay = true; break;
  }
  if (muted) a.buzzer = BuzzerMode::OFF;
  return a;
}
