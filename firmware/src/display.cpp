#include "display.h"

#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Wire.h>

#include "config.h"

static Adafruit_SSD1306 oled(128, 64, &Wire, -1);
static const char* LEVEL_TXT[] = {"BINH THUONG", "CHU Y", "CANH BAO", "NGUY HIEM"};

bool Display::begin() {
  ok_ = oled.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR);
  if (ok_) {
    oled.clearDisplay();
    oled.setTextColor(SSD1306_WHITE);
    oled.setTextSize(1);
    oled.setCursor(0, 0);
    oled.println("VKU AIoT Station");
    oled.println("fw " FW_VERSION);
    oled.display();
  }
  return ok_;
}

void Display::render(const DisplayState& st) {
  if (!ok_) return;
  uint32_t now = millis();
  if (now - lastFlip_ > 4000) { page_ = (page_ + 1) % 3; lastFlip_ = now; }
  uint8_t page = st.level >= 2 ? 1 : page_;  // cảnh báo cấp ≥ 2 luôn hiển thị
  oled.clearDisplay();
  oled.setTextSize(1);
  // thanh trạng thái góc phải
  oled.setCursor(92, 0);
  oled.print(st.wifi ? "W" : "-");
  oled.print(st.mqtt ? "M" : "-");
  oled.print(st.muted ? "x" : " ");
  oled.setCursor(0, 0);
  const SensorData& s = st.s;
  if (page == 0) {
    oled.println("MOI TRUONG");
    oled.printf("T  %5.1f C  H %4.0f%%\n", s.temp, s.hum);
    oled.printf("P  %7.1f hPa\n", s.pressureMsl);
    oled.printf("Lux %8.0f\n", s.lux);
    oled.printf("Mua muc %d (%d mV)\n", s.rainLevel, s.rainMv);
    oled.printf("DewP %4.1f HI %4.1f\n", s.dew, s.heatIndex);
  } else if (page == 1) {
    oled.println("KHI GAS / KHOI");
    oled.setTextSize(2);
    oled.setCursor(0, 12);
    if (st.warmingUp) oled.println("WARM-UP");
    else oled.println(LEVEL_TXT[st.level & 3]);
    oled.setTextSize(1);
    oled.setCursor(0, 34);
    oled.printf("%.0f ppm  Rs/R0 %.2f\n", s.mq2.ppm, s.mq2.ratio);
    oled.printf("AI score %.2f\n", st.score);
    if (s.gasFault != SensorFault::NONE) oled.printf("LOI CAM BIEN %d\n", (int)s.gasFault);
  } else {
    oled.println("DU BAO");
    oled.printf("Edge: %s\n", st.nc.text);
    oled.printf("Zambretti %c  %+.1f/3h\n", st.nc.zambretti, st.nc.trend3h);
    oled.println("Cloud:");
    oled.println(st.cloudForecast[0] ? st.cloudForecast : "(chua co)");
  }
  oled.display();
}
