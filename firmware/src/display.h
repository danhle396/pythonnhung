// Màn hình TFT 1.8" ST7735S 128x160 (SPI), xoay ngang 160x128, 3 trang luân phiên 4 s.
// Trang khí/khói luôn được ưu tiên khi cấp ≥ 2. Thanh tiêu đề đổi màu theo cấp cảnh báo.
// Chỉ vẽ lại dòng nào đổi nội dung (chữ có nền) nên màn hình không nháy khi cập nhật 2 lần/giây.
#pragma once
#include <Arduino.h>
#include "nowcast.h"
#include "sensors.h"

struct DisplayState {
  SensorData s;
  int level = 0;
  bool muted = false, wifi = false, mqtt = false, warmingUp = true;
  float score = 0;
  Nowcast nc;
  char cloudForecast[64] = "";
};

class Display {
 public:
  bool begin();
  void render(const DisplayState& st);

 private:
  struct Row {
    char txt[28];
    int16_t y = -1;
    uint16_t fg = 0, bg = 0;
    uint8_t size = 0;
  };
  static constexpr uint8_t kRows = 10;
  void clearPage();
  void header(const char* title, uint16_t fg, uint16_t bg, const DisplayState& st);
  // In 1 dòng (cỡ chữ 1 = 26 ký tự, cỡ 2 = 13 ký tự), tự đệm khoảng trắng để xoá chữ cũ.
  void row(uint8_t slot, int16_t y, uint8_t size, uint16_t fg, uint16_t bg, const char* fmt, ...);
  // Ngắt chuỗi dài thành tối đa n dòng cỡ chữ 1 (ngắt ở dấu cách).
  void wrapped(uint8_t slot, int16_t y, uint8_t n, uint16_t fg, const char* text);
  void footer(uint8_t page);

  bool ok_ = false;
  uint8_t page_ = 0, shown_ = 0xFF;
  uint16_t headerBg_ = 0;
  uint32_t lastFlip_ = 0;
  Row rows_[kRows];
};
