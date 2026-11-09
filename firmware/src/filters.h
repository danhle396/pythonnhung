// Bộ lọc tín hiệu thuần C++ (không phụ thuộc Arduino) — dùng chung cho firmware và unit test native.
#pragma once
#include <stddef.h>
#include <math.h>

// Vòng đệm kích thước cố định, không cấp phát động.
template <size_t N>
class RingBuffer {
 public:
  void push(float v) {
    buf_[head_] = v;
    head_ = (head_ + 1) % N;
    if (count_ < N) ++count_;
  }
  size_t size() const { return count_; }
  bool full() const { return count_ == N; }
  void clear() { head_ = count_ = 0; }
  // phần tử thứ i tính từ cũ nhất (0) đến mới nhất (size()-1)
  float at(size_t i) const { return buf_[(head_ + N - count_ + i) % N]; }
  float last() const { return at(count_ - 1); }
  float mean() const;
  float stdev() const;  // độ lệch chuẩn tổng thể (chia n) — giống np.std
  // Độ dốc bình phương tối thiểu của `n` phần tử mới nhất (đơn vị: giá trị / mẫu)
  float slope(size_t n = N) const;

 private:
  float buf_[N] = {0};
  size_t head_ = 0, count_ = 0;
};

template <size_t N>
float RingBuffer<N>::mean() const {
  if (!count_) return 0.0f;
  float s = 0;
  for (size_t i = 0; i < count_; ++i) s += at(i);
  return s / count_;
}

template <size_t N>
float RingBuffer<N>::stdev() const {
  if (count_ < 2) return 0.0f;
  float m = mean(), s = 0;
  for (size_t i = 0; i < count_; ++i) {
    float d = at(i) - m;
    s += d * d;
  }
  return sqrtf(s / count_);
}

template <size_t N>
float RingBuffer<N>::slope(size_t n) const {
  if (n > count_) n = count_;
  if (n < 2) return 0.0f;
  size_t start = count_ - n;
  float tm = (n - 1) / 2.0f, ym = 0;
  for (size_t i = 0; i < n; ++i) ym += at(start + i);
  ym /= n;
  float num = 0, den = 0;
  for (size_t i = 0; i < n; ++i) {
    float tc = i - tm;
    num += tc * (at(start + i) - ym);
    den += tc * tc;
  }
  return num / den;
}

// Median cửa sổ 5 — loại bỏ spike đơn lẻ.
class Median5 {
 public:
  float update(float v);
  void reset() { n_ = 0; }

 private:
  float w_[5] = {0};
  size_t n_ = 0, i_ = 0;
};

// EWMA: s_t = α·x_t + (1 − α)·s_{t−1}
class Ewma {
 public:
  explicit Ewma(float alpha = 0.25f) : a_(alpha) {}
  float update(float v) {
    if (!init_) { s_ = v; init_ = true; }
    else s_ = a_ * v + (1 - a_) * s_;
    return s_;
  }
  float value() const { return s_; }
  bool ready() const { return init_; }
  void reset() { init_ = false; }

 private:
  float a_, s_ = 0;
  bool init_ = false;
};

// Median-5 rồi EWMA (task.md 6.2)
class SensorFilter {
 public:
  explicit SensorFilter(float alpha = 0.25f) : ewma_(alpha) {}
  float update(float v) {
    if (isnan(v)) return ewma_.value();
    return ewma_.update(med_.update(v));
  }
  float value() const { return ewma_.value(); }

 private:
  Median5 med_;
  Ewma ewma_;
};

// Đại lượng dẫn xuất
float dewPoint(float tempC, float rh);
float heatIndex(float tempC, float rh);
float seaLevelPressure(float pHpa, float tempC, float altM);
