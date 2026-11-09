#include "sensors.h"

#include <Adafruit_BMP280.h>
#include <BH1750.h>
#include <DHT.h>
#include <Wire.h>
#include <time.h>

#include "config.h"

static DHT dht(PIN_DHT, DHT22);
static Adafruit_BMP280 bmp(&Wire);
static BH1750 lightMeter(BH1750_ADDR);
static bool bmpPresent = false, bhPresent = false;

bool Sensors::scanI2C(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

bool Sensors::begin() {
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  Wire.setClock(100000);
  Wire.setTimeOut(50);  // tránh treo bus I2C
  dht.begin();
  bmpPresent = bmp.begin(BMP280_ADDR) || bmp.begin(0x77);
  if (bmpPresent) {
    bmp.setSampling(Adafruit_BMP280::MODE_NORMAL, Adafruit_BMP280::SAMPLING_X2, Adafruit_BMP280::SAMPLING_X16,
                    Adafruit_BMP280::FILTER_X16, Adafruit_BMP280::STANDBY_MS_500);
  }
  bhPresent = lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE, BH1750_ADDR, &Wire);
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_MQ2_AO, ADC_11db);
  analogSetPinAttenuation(PIN_RAIN_AO, ADC_11db);
  pinMode(PIN_RAIN_PWR, OUTPUT);
  digitalWrite(PIN_RAIN_PWR, LOW);
  pinMode(PIN_RAIN_DO, INPUT);
  pinMode(PIN_MQ2_DO, INPUT);
  Serial.printf("[SENS] BMP280:%d BH1750:%d OLED:%d\n", bmpPresent, bhPresent, scanI2C(OLED_ADDR));
  return bmpPresent && bhPresent;
}

// analogReadMilliVolts() dùng hệ số hiệu chỉnh eFuse của ESP32; lấy trung bình n mẫu
float Sensors::readMv(int pin, int n) {
  uint32_t s = 0;
  for (int i = 0; i < n; ++i) s += analogReadMilliVolts(pin);
  return (float)s / n;
}

int Sensors::rainLevelFromMv(int mv) {
  if (mv >= RAIN_MV_DRY) return 0;       // khô
  if (mv >= RAIN_MV_DRIZZLE) return 1;   // mưa phùn
  if (mv >= RAIN_MV_MODERATE) return 2;  // mưa vừa
  return 3;                              // mưa to
}

void Sensors::read(SensorData& d) {
  uint32_t now = millis();
  time_t epoch = time(nullptr);
  d.ts = epoch > 1700000000 ? (uint32_t)epoch : 0;

  // ---- DHT22 (tối đa 1 lần / 2 s)
  if (now - lastDht_ >= DHT_PERIOD_MS || lastDht_ == 0) {
    lastDht_ = now;
    float t = dht.readTemperature(), h = dht.readHumidity();
    if (!isnan(t) && !isnan(h) && t > -20 && t < 70 && h >= 0 && h <= 100) {
      lastTempDht_ = fTemp_.update(t);
      lastHum_ = fHum_.update(h);
      dhtFails_ = 0;
    } else if (++dhtFails_ > 3) {
      lastTempDht_ = lastHum_ = NAN;  // lỗi liên tiếp -> báo hỏng
    }
  }
  d.tempDht = lastTempDht_;
  d.hum = lastHum_;
  d.dhtOk = !isnan(d.tempDht);

  // ---- BMP280
  if (bmpPresent) {
    float t = bmp.readTemperature(), p = bmp.readPressure() / 100.0f;
    d.bmpOk = !isnan(p) && p > 800 && p < 1100;
    if (d.bmpOk) {
      d.tempBmp = fTempBmp_.update(t);
      d.pressure = fPres_.update(p);
    }
  }
  // nhiệt độ dùng chung: ưu tiên DHT22, dự phòng BMP280 (task.md mục 16)
  d.temp = d.dhtOk ? d.tempDht : d.tempBmp;
  if (d.bmpOk && !isnan(d.temp)) d.pressureMsl = seaLevelPressure(d.pressure, d.temp, STATION_ALT_M);
  if (d.dhtOk) {
    d.dew = dewPoint(d.tempDht, d.hum);
    d.heatIndex = heatIndex(d.tempDht, d.hum);
  }

  // ---- BH1750
  if (bhPresent) {
    float lx = lightMeter.readLightLevel();
    d.bhOk = lx >= 0;
    if (d.bhOk) d.lux = fLux_.update(lx);
  }

  // ---- YL-83: chỉ cấp nguồn khi đọc, mỗi 10 giây
  if (now - lastRain_ >= 10000 || lastRain_ == 0) {
    lastRain_ = now;
    digitalWrite(PIN_RAIN_PWR, HIGH);
    delay(15);
    lastRainMv_ = (int)readMv(PIN_RAIN_AO, 8);
    digitalWrite(PIN_RAIN_PWR, LOW);
    lastRainLevel_ = rainLevelFromMv(lastRainMv_);
  }
  d.rainMv = lastRainMv_;
  d.rainLevel = lastRainLevel_;
  d.rainOk = lastRainMv_ > 50;  // 0 mV -> dây đứt

  // ---- MQ-2
  float mv = readMv(PIN_MQ2_AO, 16);
  d.gasFault = gasFault_.update(mv);
  d.gasMv = fGas_.update(mv);
  d.mq2 = mq2Convert(d.gasMv, mq2);
  d.gasOk = d.gasFault == SensorFault::NONE;
}

float Sensors::calibrateR0(uint16_t samples) {
  float rs = 0;
  for (uint16_t i = 0; i < samples; ++i) {
    Mq2Reading r = mq2Convert(readMv(PIN_MQ2_AO, 16), mq2);
    rs += r.rs;
    delay(100);
  }
  rs /= samples;
  return mq2CalibrateR0(rs, MQ2_CLEAN_AIR_RATIO);
}
