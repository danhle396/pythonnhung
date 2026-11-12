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

void NowcastEngine::push(float p, uint32_t t) {
  if (n_ == N) {  // đầy: bỏ mẫu cũ nhất
    for (size_t i = 1; i < N; ++i) { p_[i - 1] = p_[i]; t_[i - 1] = t_[i]; }
    --n_;
  }
  p_[n_] = p;
  t_[n_] = t;
  ++n_;
}

void NowcastEngine::prune(uint32_t newestTs) {
  size_t k = 0;  // số mẫu quá cũ ở đầu
  while (k < n_ && t_[k] != 0 && newestTs - t_[k] > WINDOW_S) ++k;
  if (!k) return;
  for (size_t i = k; i < n_; ++i) { p_[i - k] = p_[i]; t_[i - k] = t_[i]; }
  n_ -= k;
}

void NowcastEngine::addPressure(float pMsl, uint32_t ts) {
  push(pMsl, ts);
  if (ts) prune(ts);
}

bool NowcastEngine::timed() const {
  for (size_t i = 0; i < n_; ++i)
    if (t_[i] == 0) return false;
  return n_ > 0;
}

float NowcastEngine::spanHours() const {
  if (n_ < 2) return 0.0f;
  if (timed()) return (float)(t_[n_ - 1] - t_[0]) / 3600.0f;
  return (n_ - 1) * (STEP_S / 3600.0f);  // chưa có giờ: các mẫu cách đều 10 phút
}

void NowcastEngine::assignTimes(uint32_t newestTs) {
  for (size_t i = 0; i < n_; ++i)
    if (t_[i] == 0) t_[i] = newestTs - (uint32_t)(n_ - 1 - i) * STEP_S;
}

void NowcastEngine::restore(const float* p, const uint32_t* t, size_t n, uint32_t nowTs) {
  float mp[2 * N];
  uint32_t mt[2 * N];
  size_t m = 0;
  const uint32_t first = n_ ? t_[0] : nowTs + 1;  // mẫu đã lưu phải cũ hơn mẫu hiện có (tránh trùng)
  for (size_t i = 0; i < n && m < N; ++i) {
    if (t[i] == 0 || t[i] > nowTs || nowTs - t[i] > WINDOW_S) continue;
    if (n_ && t[i] + STEP_S / 2 > first) continue;
    mp[m] = p[i];
    mt[m] = t[i];
    ++m;
  }
  for (size_t i = 0; i < n_; ++i) { mp[m] = p_[i]; mt[m] = t_[i]; ++m; }
  for (size_t i = 1; i < m; ++i)  // sắp theo thời gian (insertion sort, ≤ 38 phần tử)
    for (size_t j = i; j > 0 && mt[j - 1] > mt[j]; --j) {
      float tp = mp[j]; mp[j] = mp[j - 1]; mp[j - 1] = tp;
      uint32_t tt = mt[j]; mt[j] = mt[j - 1]; mt[j - 1] = tt;
    }
  n_ = 0;
  for (size_t i = (m > N ? m - N : 0); i < m; ++i) push(mp[i], mt[i]);
  prune(nowTs);
}

size_t NowcastEngine::exportSamples(float* p, uint32_t* t) const {
  size_t k = 0;
  for (size_t i = 0; i < n_; ++i)
    if (t_[i]) { p[k] = p_[i]; t[k] = t_[i]; ++k; }
  return k;
}

Nowcast NowcastEngine::compute(int rainLevel, float hum, int month) const {
  Nowcast nc;
  if (rainLevel >= 1) {
    nc.code = NowcastCode::RAINING;
    nc.text = "Dang mua";
    nc.textVi = "Đang mưa";
  }
  const float span_h = spanHours();
  if (span_h < 0.99f) return nc;  // cần ít nhất 1 giờ dữ liệu
  // quy đổi xu hướng về 3 giờ nếu chưa đủ 3 giờ
  nc.trend3h = (p_[n_ - 1] - p_[0]) * 3.0f / span_h;
  nc.trend = nc.trend3h <= -TREND_THRESHOLD ? PressureTrend::Falling
           : nc.trend3h >= TREND_THRESHOLD ? PressureTrend::Rising : PressureTrend::Steady;
  nc.zambretti = zambrettiLetter(p_[n_ - 1], nc.trend, month, &nc.zNumber);
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
