#include "filters.h"

float Median5::update(float v) {
  w_[i_] = v;
  i_ = (i_ + 1) % 5;
  if (n_ < 5) ++n_;
  float s[5];
  for (size_t k = 0; k < n_; ++k) s[k] = w_[k];
  // sắp xếp chèn (n ≤ 5)
  for (size_t a = 1; a < n_; ++a) {
    float x = s[a];
    size_t b = a;
    while (b > 0 && s[b - 1] > x) { s[b] = s[b - 1]; --b; }
    s[b] = x;
  }
  return s[n_ / 2];
}

// Magnus: γ = ln(RH/100) + a·T/(b+T),  Td = b·γ/(a−γ)
float dewPoint(float t, float rh) {
  const float a = 17.62f, b = 243.12f;
  if (rh < 0.001f) rh = 0.001f;
  float g = logf(rh / 100.0f) + a * t / (b + t);
  return b * g / (a - g);
}

// NOAA Rothfusz, trả về °C
float heatIndex(float t, float rh) {
  if (t < 27.0f) return t;
  float T = t * 9.0f / 5.0f + 32.0f, R = rh;
  float hi = -42.379f + 2.04901523f * T + 10.14333127f * R - 0.22475541f * T * R - 6.83783e-3f * T * T -
             5.481717e-2f * R * R + 1.22874e-3f * T * T * R + 8.5282e-4f * T * R * R - 1.99e-6f * T * T * R * R;
  return (hi - 32.0f) * 5.0f / 9.0f;
}

// P0 = P·(1 − 0.0065·h/(T + 0.0065·h + 273.15))^(−5.257)
float seaLevelPressure(float p, float t, float h) {
  return p * powf(1.0f - 0.0065f * h / (t + 0.0065f * h + 273.15f), -5.257f);
}
