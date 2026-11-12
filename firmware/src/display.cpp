#include "display.h"

#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <SPI.h>
#include <stdarg.h>
#include <time.h>

#include "config.h"

static constexpr int16_t W = 160, H = 128;  // sau khi xoay ngang (TFT_ROTATION 1/3)
static constexpr uint16_t DARKGREEN = 0x03E0, GREY = 0x7BEF;

// HSPI qua GPIO matrix: chân tuỳ chọn, chỉ ghi. MISO = -1 (core gán mặc định GPIO12 làm input, không nối gì).
static SPIClass tftSpi(HSPI);
static Adafruit_ST7735 tft(&tftSpi, PIN_TFT_CS, PIN_TFT_DC, PIN_TFT_RST);

static const char* LEVEL_TXT[] = {"BINH THUONG", "CHU Y", "CANH BAO", "NGUY HIEM"};
static const uint16_t LEVEL_BG[] = {DARKGREEN, ST77XX_YELLOW, ST77XX_ORANGE, ST77XX_RED};
static const uint16_t LEVEL_FG[] = {ST77XX_WHITE, ST77XX_BLACK, ST77XX_BLACK, ST77XX_WHITE};
static const char* RAIN_TXT[] = {"kho", "mua phun", "mua vua", "mua to"};

bool Display::begin() {
  tftSpi.begin(PIN_TFT_SCK, -1, PIN_TFT_MOSI, -1);
  tft.initR(TFT_INIT_TAB);  // gồm SWRESET nên RESET nối EN vẫn khởi tạo lại được sau reset mềm
  tft.setSPISpeed(TFT_SPI_HZ);
  tft.setRotation(TFT_ROTATION);
  tft.setTextWrap(false);
  tft.fillScreen(ST77XX_BLACK);
  tft.fillRect(0, 0, W, 14, DARKGREEN);
  tft.setTextColor(ST77XX_WHITE);
  tft.setTextSize(1);
  tft.setCursor(4, 3);
  tft.print("VKU AIoT Station");
  tft.setTextSize(2);
  tft.setCursor(4, 40);
  tft.print("Tram AIoT");
  tft.setTextSize(1);
  tft.setCursor(4, 66);
  tft.print("Da Nang 15.975N 108.253E");
  tft.setCursor(4, 80);
  tft.print("fw " FW_VERSION);
  tft.setCursor(4, 100);
  tft.setTextColor(GREY);
  tft.print("Dang khoi dong...");
  ok_ = true;  // SPI chỉ ghi: không dò được màn hình, luôn coi là có
  return ok_;
}

void Display::clearPage() {
  tft.fillScreen(ST77XX_BLACK);
  for (auto& r : rows_) r = Row();
  headerBg_ = 0xFFFF - 1;  // buộc vẽ lại thanh tiêu đề
}

void Display::row(uint8_t slot, int16_t y, uint8_t size, uint16_t fg, uint16_t bg, const char* fmt, ...) {
  char buf[sizeof(Row::txt)];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  const int cols = W / (6 * size);
  int n = strlen(buf);
  if (n > cols) n = cols;
  memset(buf + n, ' ', cols - n);
  buf[cols] = '\0';

  Row& r = rows_[slot];
  if (r.y == y && r.size == size && r.fg == fg && r.bg == bg && strcmp(r.txt, buf) == 0) return;
  if (r.size && (r.y != y || r.size != size)) tft.fillRect(0, r.y, W, 8 * r.size, ST77XX_BLACK);
  tft.setTextSize(size);
  tft.setTextColor(fg, bg);  // chữ có nền -> ghi đè chữ cũ, không cần xoá màn hình
  tft.setCursor(0, y);
  tft.print(buf);
  const int16_t used = cols * 6 * size;
  if (used < W) tft.fillRect(used, y, W - used, 8 * size, bg);
  strlcpy(r.txt, buf, sizeof(r.txt));
  r.y = y;
  r.size = size;
  r.fg = fg;
  r.bg = bg;
}

void Display::wrapped(uint8_t slot, int16_t y, uint8_t n, uint16_t fg, const char* text) {
  const int cols = W / 6;
  const char* p = text;
  for (uint8_t i = 0; i < n; ++i) {
    while (*p == ' ') ++p;
    int len = strlen(p);
    if (len > cols) {
      len = cols;
      for (int k = cols; k > cols / 2; --k)
        if (p[k] == ' ') { len = k; break; }
    }
    row(slot + i, y + 10 * i, 1, fg, ST77XX_BLACK, "%.*s", len, p);
    p += len;
  }
}

void Display::header(const char* title, uint16_t fg, uint16_t bg, const DisplayState& st) {
  if (bg != headerBg_) {
    tft.fillRect(0, 0, W, 14, bg);
    headerBg_ = bg;
    rows_[0] = Row();
  }
  // góc phải: W = Wi-Fi, M = MQTT, x = đang tắt còi
  row(0, 3, 1, fg, bg, "%-20s %c%c %c", title, st.wifi ? 'W' : '-', st.mqtt ? 'M' : '-', st.muted ? 'x' : ' ');
}

void Display::footer(uint8_t page) {
  char clock[8] = "--:--";
  time_t now = time(nullptr);
  if (now > 1600000000) {  // đã có giờ NTP
    struct tm t;
    localtime_r(&now, &t);
    strftime(clock, sizeof(clock), "%H:%M", &t);
  }
  row(kRows - 1, H - 10, 1, GREY, ST77XX_BLACK, "%-6s fw %-10s %d/3", clock, FW_VERSION, page + 1);
}

void Display::render(const DisplayState& st) {
  if (!ok_) return;
  uint32_t now = millis();
  if (now - lastFlip_ > 4000) { page_ = (page_ + 1) % 3; lastFlip_ = now; }
  const uint8_t page = st.level >= 2 ? 1 : page_;  // cảnh báo cấp ≥ 2 luôn hiển thị
  if (page != shown_) {
    clearPage();
    shown_ = page;
  }
  const int lv = st.level & 3;
  const uint16_t hbg = st.warmingUp ? GREY : LEVEL_BG[lv];
  const uint16_t hfg = st.warmingUp ? ST77XX_WHITE : LEVEL_FG[lv];
  const SensorData& s = st.s;

  if (page == 0) {
    header("MOI TRUONG", hfg, hbg, st);
    row(1, 18, 2, ST77XX_ORANGE, ST77XX_BLACK, "T %5.1f C", s.temp);
    row(2, 36, 2, ST77XX_CYAN, ST77XX_BLACK, "H %5.0f %%", s.hum);
    row(3, 58, 1, ST77XX_WHITE, ST77XX_BLACK, "Ap suat  %7.1f hPa", s.pressureMsl);
    row(4, 70, 1, ST77XX_WHITE, ST77XX_BLACK, "Anh sang %7.0f lux", s.lux);
    row(5, 82, 1, ST77XX_WHITE, ST77XX_BLACK, "Mua: %s (%d mV)", RAIN_TXT[s.rainLevel & 3], s.rainMv);
    row(6, 94, 1, ST77XX_WHITE, ST77XX_BLACK, "Diem suong %5.1f C", s.dew);
    row(7, 106, 1, ST77XX_WHITE, ST77XX_BLACK, "Chi so nhiet %5.1f C", s.heatIndex);
  } else if (page == 1) {
    header("KHI GAS / KHOI", hfg, hbg, st);
    const char* txt = st.warmingUp ? "LAM NONG..." : LEVEL_TXT[lv];
    const int pad = (13 - (int)strlen(txt)) / 2;
    row(1, 20, 2, hfg, hbg, "%*s%s", pad, "", txt);
    row(2, 42, 2, ST77XX_WHITE, ST77XX_BLACK, "%6.0f ppm", s.mq2.ppm);
    row(3, 64, 1, ST77XX_WHITE, ST77XX_BLACK, "Rs/R0       %.2f", s.mq2.ratio);
    row(4, 76, 1, ST77XX_WHITE, ST77XX_BLACK, "AI score    %.2f", st.score);
    if (st.muted) row(5, 88, 1, ST77XX_YELLOW, ST77XX_BLACK, "Coi: DA TAT (5 phut)");
    else row(5, 88, 1, ST77XX_WHITE, ST77XX_BLACK, "Coi: san sang");
    if (s.gasFault != SensorFault::NONE) row(6, 100, 1, ST77XX_RED, ST77XX_BLACK, "LOI CAM BIEN MQ-2 (%d)", (int)s.gasFault);
    else row(6, 100, 1, ST77XX_WHITE, ST77XX_BLACK, "");
  } else {
    header("DU BAO", hfg, hbg, st);
    row(1, 18, 1, ST77XX_CYAN, ST77XX_BLACK, "Edge (nowcast tai tram)");
    const uint8_t sz = strlen(st.nc.text) <= 13 ? 2 : 1;
    row(2, 30, sz, ST77XX_WHITE, ST77XX_BLACK, "%s", st.nc.text);
    row(3, 50, 1, ST77XX_WHITE, ST77XX_BLACK, "Zambretti %c  %+.1f hPa/3h", st.nc.zambretti, st.nc.trend3h);
    row(4, 66, 1, ST77XX_CYAN, ST77XX_BLACK, "Cloud (AI du bao)");
    wrapped(5, 78, 3, ST77XX_WHITE, st.cloudForecast[0] ? st.cloudForecast : "(chua co)");
  }
  footer(page);
}
