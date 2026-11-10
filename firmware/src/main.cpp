// Trạm AIoT VKU — ESP32: thu thập cảm biến, Edge AI cảnh báo khí/khói 4 cấp, nowcast, MQTT, đệm offline.
// Kiến trúc FreeRTOS (task.md 6.1):
//   TaskSensors (core 1, 1 Hz) --qSamples--> TaskEdgeAI (core 1) --qOut--> TaskNetwork (core 0) --MQTT-->
//   Cảnh báo tại edge KHÔNG phụ thuộc mạng: TaskEdgeAI điều khiển còi/LED/relay trực tiếp.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include <HTTPUpdate.h>
#include <esp_task_wdt.h>
#include <time.h>

#include "alert.h"
#include "config.h"
#include "display.h"
#include "edge_ai.h"
#include "gas_model.h"
#include "mqtt_client.h"
#include "nowcast.h"
#include "sensors.h"
#include "storage.h"

struct OutMsg {
  char suffix[12];
  char payload[760];
  bool retain;
  bool buffer;  // ghi vào đệm offline nếu chưa gửi được
};

static QueueHandle_t qSamples, qOut;
static SemaphoreHandle_t mtx;
static Sensors sensors;
static EdgeAI edge;
static AlertManager alerts(MUTE_DURATION_MS);
static NowcastEngine nowcaster;
static MqttLink mqtt;
static Storage storage;
static Display display;
static DeviceConfig cfg;
static DisplayState dstate;
static Nowcast lastNowcast;

static volatile bool flagCalibrate = false, flagReboot = false, flagTestAlarm = false, flagMute = false,
                     flagConfigChanged = true;
static volatile int cloudLevel = 0;
static volatile bool flagOta = false;
static char otaUrl[200] = "";
static const char* LEVEL_NAME[] = {"normal", "advisory", "warning", "danger"};

// ------------------------------------------------------------------ tiện ích JSON
static void setNum(JsonDocument& d, const char* k, float v, int digits = 2) {
  if (isnan(v)) d[k] = nullptr;
  else d[k] = serialized(String(v, digits));
}

static void enqueue(const char* suffix, JsonDocument& doc, bool retain = false, bool buffer = false) {
  OutMsg m;
  strlcpy(m.suffix, suffix, sizeof(m.suffix));
  size_t n = serializeJson(doc, m.payload, sizeof(m.payload));
  if (n == 0 || n >= sizeof(m.payload) - 1) return;
  m.retain = retain;
  m.buffer = buffer;
  if (xQueueSend(qOut, &m, 0) != pdTRUE && buffer) storage.append(m.suffix, m.payload);  // hàng đợi đầy
}

static void causeToJson(JsonArray arr, uint32_t c, const RuleConfig& r) {
  char b[24];
  if (c & CAUSE_PPM_TH1) { snprintf(b, sizeof b, "gas_ppm>%.0f", r.th1); arr.add(b); }
  if (c & CAUSE_SLOPE) arr.add("slope_high");
  if (c & CAUSE_PPM_TH2) { snprintf(b, sizeof b, "gas_ppm>%.0f", r.th2); arr.add(b); }
  if (c & CAUSE_PPM_TH3) { snprintf(b, sizeof b, "gas_ppm>%.0f", r.th3); arr.add(b); }
  if (c & CAUSE_TEMP_RISING) arr.add("temp_rising");
  if (c & CAUSE_MODEL) arr.add("model");
  if (c & CAUSE_CLOUD) arr.add("cloud_escalation");
  if (c & CAUSE_TEST) arr.add("test_alarm");
}

static void sendAck(const char* ref, const char* id, bool ok, const char* msg) {
  JsonDocument d;
  d["device_id"] = DEVICE_ID;
  d["ts"] = (uint32_t)time(nullptr);
  d["ref"] = ref;
  if (id) d["id"] = id;
  d["ok"] = ok;
  d["msg"] = msg;
  enqueue("ack", d);
}

// ------------------------------------------------------------------ xử lý lệnh từ cloud
static void applyConfigJson(JsonDocument& j) {
  DeviceConfig c = cfg;
  c.rule.th1 = j["th1"] | c.rule.th1;
  c.rule.th2 = j["th2"] | c.rule.th2;
  c.rule.th3 = j["th3"] | c.rule.th3;
  c.rule.slope1 = j["slope1"] | c.rule.slope1;
  c.rule.dtemp3 = j["dtemp3"] | c.rule.dtemp3;
  c.rule.hyst = j["hyst"] | c.rule.hyst;
  c.rule.debounceUp = j["debounce_up"] | c.rule.debounceUp;
  c.rule.debounceDown = j["debounce_down"] | c.rule.debounceDown;
  c.telemetryMs = j["telemetry_ms"] | c.telemetryMs;
  c.r0Kohm = j["r0_kohm"] | c.r0Kohm;
  const char* mode = j["mode"] | "";
  if (!strcmp(mode, "rule")) c.edgeMode = 0;
  else if (!strcmp(mode, "model")) c.edgeMode = 1;
  else if (!strcmp(mode, "hybrid")) c.edgeMode = 2;
  c.version = j["version"] | c.version + 1;
  bool valid = c.rule.th1 > 0 && c.rule.th1 < c.rule.th2 && c.rule.th2 < c.rule.th3 && c.rule.th3 < 10000 &&
               c.rule.hyst >= 0 && c.rule.hyst < 0.5f && c.rule.debounceUp >= 1 && c.rule.debounceUp <= 30 &&
               c.rule.debounceDown >= 1 && c.rule.debounceDown <= 60 && c.telemetryMs >= 1000 &&
               c.telemetryMs <= 600000 && c.r0Kohm > 0.1f && c.r0Kohm < 1000;
  if (!valid) { sendAck("config", nullptr, false, "invalid ranges"); return; }
  xSemaphoreTake(mtx, portMAX_DELAY);
  cfg = c;
  flagConfigChanged = true;
  xSemaphoreGive(mtx);
  storage.saveConfig(c);
  char msg[32];
  snprintf(msg, sizeof msg, "config v%lu applied", (unsigned long)c.version);
  sendAck("config", nullptr, true, msg);
}

static void onMessage(const char* suffix, const uint8_t* payload, unsigned int len) {
  JsonDocument j;
  if (deserializeJson(j, payload, len)) { sendAck(suffix, nullptr, false, "bad json"); return; }
  if (!strcmp(suffix, "cmd")) {
    const char* cmd = j["cmd"] | "";
    const char* id = j["id"] | "";
    if (!strcmp(cmd, "mute")) flagMute = true;
    else if (!strcmp(cmd, "test_alarm")) flagTestAlarm = true;
    else if (!strcmp(cmd, "calibrate")) flagCalibrate = true;
    else if (!strcmp(cmd, "reboot")) flagReboot = true;
    else if (!strcmp(cmd, "escalate")) cloudLevel = constrain((int)(j["level"] | 0), 0, 3);
    else if (!strcmp(cmd, "ota")) {  // OTA firmware qua HTTP: {"cmd":"ota","url":"http://host/firmware.bin"}
      const char* url = j["url"] | "";
      if (strncmp(url, "http://", 7) != 0 && strncmp(url, "https://", 8) != 0) {
        sendAck("cmd", id, false, "bad url");
        return;
      }
      strlcpy(otaUrl, url, sizeof(otaUrl));
      flagOta = true;
    }
    else { sendAck("cmd", id, false, "unknown cmd"); return; }
    sendAck("cmd", id, true, cmd);
  } else if (!strcmp(suffix, "config")) {
    applyConfigJson(j);
  } else if (!strcmp(suffix, "forecast")) {
    const char* summary = j["summary"] | "";
    xSemaphoreTake(mtx, portMAX_DELAY);
    strlcpy(dstate.cloudForecast, summary, sizeof(dstate.cloudForecast));
    xSemaphoreGive(mtx);
  }
}

// ------------------------------------------------------------------ cơ cấu chấp hành
static void driveActuators(const Actions& a, uint32_t now) {
  bool blink = (now / 250) % 2;
  digitalWrite(PIN_LED_GREEN, a.led == LedMode::GREEN);
  digitalWrite(PIN_LED_YELLOW, a.led == LedMode::YELLOW);
  digitalWrite(PIN_LED_RED, a.led == LedMode::RED_SOLID || (a.led == LedMode::RED_BLINK && blink));
  bool buzz = a.buzzer == BuzzerMode::CONTINUOUS || (a.buzzer == BuzzerMode::INTERMITTENT && (now % 1000) < 200);
  digitalWrite(PIN_BUZZER, buzz);
  digitalWrite(PIN_RELAY, a.relay);
}

// ------------------------------------------------------------------ TASK: cảm biến
static void TaskSensors(void*) {
  esp_task_wdt_add(nullptr);
  TickType_t last = xTaskGetTickCount();
  for (;;) {
    SensorData d;
    sensors.read(d);
    xQueueSend(qSamples, &d, 0);
    esp_task_wdt_reset();
    vTaskDelayUntil(&last, pdMS_TO_TICKS(SENSOR_PERIOD_MS));
  }
}

// ------------------------------------------------------------------ TASK: Edge AI + cảnh báo
static void TaskEdgeAI(void*) {
  esp_task_wdt_add(nullptr);
  SensorData d;
  Actions act;
  uint32_t lastTel = 0, lastNow = 0, lastDisp = 0, btnSince = 0;
  bool btnPrev = HIGH;
  SensorFault prevFault = SensorFault::NONE;
  EdgeOutput o;
  for (;;) {
    uint32_t now = millis();
    if (flagConfigChanged) {
      xSemaphoreTake(mtx, portMAX_DELAY);
      edge.rules.cfg = cfg.rule;
      edge.mode = (EdgeMode)cfg.edgeMode;
      sensors.mq2.r0Kohm = cfg.r0Kohm;
      flagConfigChanged = false;
      xSemaphoreGive(mtx);
    }
    if (flagMute) { alerts.pressMute(now); flagMute = false; }
    if (flagTestAlarm) { alerts.testAlarm(now); flagTestAlarm = false; }
    if (cloudLevel > 0) { alerts.cloudEscalate(cloudLevel, now); cloudLevel = 0; }
    // nút nhấn: chống dội 50 ms, nhấn = mute 5 phút
    bool btn = digitalRead(PIN_BUTTON);
    if (btn != btnPrev) { btnSince = now; btnPrev = btn; }
    else if (btn == LOW && btnSince && now - btnSince > 50) { alerts.pressMute(now); btnSince = 0; }

    if (xQueueReceive(qSamples, &d, pdMS_TO_TICKS(100)) == pdTRUE) {
      EdgeInput in{d.mq2.ppm, d.mq2.ratio, isnan(d.temp) ? 25.0f : d.temp, isnan(d.hum) ? 70.0f : d.hum,
                   isnan(d.lux) ? 0.0f : d.lux, d.gasOk};
      o = edge.step(in);
      act = alerts.update(o.level, now);
      uint32_t ts = d.ts ? d.ts : (uint32_t)time(nullptr);
      if (act.levelChanged) {
        JsonDocument j;
        j["device_id"] = DEVICE_ID;
        j["ts"] = ts;
        j["seq"] = storage.nextSeq();
        j["type"] = (o.cause & CAUSE_TEST) ? "test" : "gas";
        j["level"] = act.level;
        j["prev_level"] = act.prevLevel;
        j["level_name"] = LEVEL_NAME[act.level & 3];
        uint32_t cause = o.cause | (act.level > o.level ? CAUSE_CLOUD : 0);
        causeToJson(j["cause"].to<JsonArray>(), cause, edge.rules.cfg);
        setNum(j, "gas_ppm", d.mq2.ppm, 0);
        setNum(j, "score", o.score, 3);
        j["rule_level"] = o.ruleLevel;
        j["model_level"] = o.modelLevel;
        JsonArray a = j["action"].to<JsonArray>();
        if (act.led == LedMode::RED_SOLID) a.add("led_red_solid");
        else if (act.led == LedMode::RED_BLINK) a.add("led_red_blink");
        else if (act.led == LedMode::YELLOW) a.add("led_yellow");
        else a.add("led_green");
        if (act.buzzer == BuzzerMode::CONTINUOUS) a.add("buzzer_continuous");
        if (act.buzzer == BuzzerMode::INTERMITTENT) a.add("buzzer_intermittent");
        if (act.relay) a.add("fan_on");
        j["edge_latency_ms"] = millis() - now;
        enqueue("alert", j, false, true);
      }
      if (d.gasFault != prevFault) {
        JsonDocument j;
        j["device_id"] = DEVICE_ID;
        j["ts"] = ts;
        j["seq"] = storage.nextSeq();
        j["type"] = "sensor_fault";
        j["sensor"] = "mq2";
        j["fault"] = (int)d.gasFault;  // 0 hết lỗi, 1 stuck, 2 mất kết nối, 3 bão hoà
        j["level"] = act.level;
        j["prev_level"] = act.level;
        enqueue("alert", j, false, true);
        prevFault = d.gasFault;
      }
      uint32_t period = act.level >= 1 ? TELEMETRY_ALERT_PERIOD_MS : cfg.telemetryMs;
      if (now - lastTel >= period) {
        lastTel = now;
        JsonDocument j;
        j["device_id"] = DEVICE_ID;
        j["ts"] = ts;
        j["seq"] = storage.nextSeq();
        setNum(j, "temp_dht", d.tempDht);
        setNum(j, "hum", d.hum);
        setNum(j, "temp_bmp", d.tempBmp);
        setNum(j, "pressure", d.pressure);
        setNum(j, "pressure_msl", d.pressureMsl);
        setNum(j, "lux", d.lux, 1);
        setNum(j, "dew_point", d.dew);
        setNum(j, "heat_index", d.heatIndex);
        j["rain_raw"] = d.rainMv;
        j["rain_level"] = d.rainLevel;
        setNum(j, "gas_raw", d.gasMv, 0);
        setNum(j, "gas_rs_r0", d.mq2.ratio, 3);
        setNum(j, "gas_ppm", d.mq2.ppm, 1);
        setNum(j, "gas_slope", o.f ? o.f[2] : 0, 2);
        j["edge_risk"] = act.level;
        setNum(j, "edge_score", o.score, 3);
        j["warming_up"] = o.warmingUp;
        JsonObject ok = j["sensor_ok"].to<JsonObject>();
        ok["dht"] = d.dhtOk; ok["bmp"] = d.bmpOk; ok["bh"] = d.bhOk; ok["rain"] = d.rainOk; ok["gas"] = d.gasOk;
        j["fw"] = FW_VERSION;
        j["model_ver"] = GAS_MODEL_VERSION;
        enqueue("telemetry", j, false, true);
      }
      // nowcast: 1 mẫu áp suất / 10 phút (mẫu đầu tiên ngay khi có dữ liệu)
      if (!isnan(d.pressureMsl) && (lastNow == 0 || now - lastNow >= NOWCAST_SAMPLE_MS)) {
        lastNow = now;
        nowcaster.addPressure(d.pressureMsl);
        struct tm tmv;
        int month = getLocalTime(&tmv, 0) ? tmv.tm_mon + 1 : 11;
        lastNowcast = nowcaster.compute(d.rainLevel, isnan(d.hum) ? 70 : d.hum, month);
        JsonDocument j;
        j["device_id"] = DEVICE_ID;
        j["ts"] = ts;
        j["code"] = (int)lastNowcast.code;
        j["text"] = lastNowcast.textVi;
        j["trend"] = (int)lastNowcast.trend;
        setNum(j, "trend_3h", lastNowcast.trend3h);
        j["zambretti"] = String(lastNowcast.zambretti);
        j["samples"] = nowcaster.samples();
        enqueue("nowcast", j, true, false);
      }
      xSemaphoreTake(mtx, portMAX_DELAY);
      dstate.s = d;
      dstate.level = act.level;
      dstate.muted = act.muted;
      dstate.score = o.score;
      dstate.warmingUp = o.warmingUp;
      dstate.nc = lastNowcast;
      xSemaphoreGive(mtx);
    }
    driveActuators(act, millis());
    if (millis() - lastDisp > 500) {
      lastDisp = millis();
      xSemaphoreTake(mtx, portMAX_DELAY);
      DisplayState copy = dstate;
      xSemaphoreGive(mtx);
      copy.wifi = WiFi.status() == WL_CONNECTED;
      copy.mqtt = mqtt.connected();
      display.render(copy);
    }
    esp_task_wdt_reset();
  }
}

// ------------------------------------------------------------------ TASK: mạng
static void TaskNetwork(void*) {
  esp_task_wdt_add(nullptr);
  uint32_t lastStatus = 0;
  bool wasConnected = false;
  OutMsg m;
  for (;;) {
    bool up = mqtt.loop();
    if (up && !wasConnected) lastStatus = 0;  // vừa kết nối lại -> gửi status ngay
    wasConnected = up;
    if (up && storage.pending()) {  // gửi bù dữ liệu đệm offline
      storage.replay([](const String& t, const String& p) { return mqtt.publish(t.c_str(), p.c_str()); }, 20);
    }
    while (xQueueReceive(qOut, &m, 0) == pdTRUE) {
      if (!mqtt.publish(m.suffix, m.payload, m.retain) && m.buffer) storage.append(m.suffix, m.payload);
    }
    if (up && millis() - lastStatus >= STATUS_PERIOD_MS) {
      lastStatus = millis();
      JsonDocument j;
      j["state"] = "online";
      j["device_id"] = DEVICE_ID;
      j["ts"] = (uint32_t)time(nullptr);
      j["rssi"] = mqtt.rssi();
      j["uptime_s"] = millis() / 1000;
      j["free_heap"] = ESP.getFreeHeap();
      j["min_free_heap"] = ESP.getMinFreeHeap();
      j["reconnects"] = mqtt.reconnects();
      j["offline_pending"] = storage.pending();
      j["fw"] = FW_VERSION;
      j["model_ver"] = GAS_MODEL_VERSION;
      j["edge_mode"] = cfg.edgeMode;
      j["config_ver"] = cfg.version;
      j["inference_us"] = edge.lastInferenceUs;
      j["reset_reason"] = (int)esp_reset_reason();
      char buf[400];
      serializeJson(j, buf, sizeof buf);
      mqtt.publish("status", buf, true);
    }
    if (flagCalibrate) {  // đo R0 trong không khí sạch (~5 s)
      flagCalibrate = false;
      esp_task_wdt_reset();
      float r0 = sensors.calibrateR0(50);
      xSemaphoreTake(mtx, portMAX_DELAY);
      cfg.r0Kohm = r0;
      flagConfigChanged = true;
      xSemaphoreGive(mtx);
      storage.saveConfig(cfg);
      char msg[40];
      snprintf(msg, sizeof msg, "R0=%.2f kOhm", r0);
      sendAck("calibrate", nullptr, true, msg);
    }
    if (flagOta) {  // tải firmware mới; thành công -> tự khởi động lại
      flagOta = false;
      mqtt.publish("status", "{\"state\":\"updating\"}", true);
      esp_task_wdt_delete(nullptr);  // tải có thể lâu hơn timeout WDT
      WiFiClient otaClient;
      httpUpdate.rebootOnUpdate(true);
      t_httpUpdate_return r = httpUpdate.update(otaClient, otaUrl);
      esp_task_wdt_add(nullptr);
      char msg[64];
      snprintf(msg, sizeof msg, "ota failed: %s", httpUpdate.getLastErrorString().c_str());
      sendAck("ota", nullptr, r == HTTP_UPDATE_NO_UPDATES, r == HTTP_UPDATE_NO_UPDATES ? "no update" : msg);
    }
    if (flagReboot) {
      mqtt.publish("status", "{\"state\":\"rebooting\"}", true);
      delay(200);
      ESP.restart();
    }
    esp_task_wdt_reset();
    vTaskDelay(pdMS_TO_TICKS(20));
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n[BOOT] VKU AIoT Station fw " FW_VERSION ", model " GAS_MODEL_VERSION);
  for (int p : std::initializer_list<int>{PIN_LED_GREEN, PIN_LED_YELLOW, PIN_LED_RED, PIN_BUZZER, PIN_RELAY}) {
    pinMode(p, OUTPUT);
    digitalWrite(p, LOW);
  }
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  storage.begin();
  storage.loadConfig(cfg);
  sensors.mq2.rlKohm = MQ2_RL_KOHM;
  sensors.mq2.vc = MQ2_VC;
  sensors.mq2.divider = MQ2_DIVIDER;
  sensors.mq2.r0Kohm = cfg.r0Kohm;
  sensors.begin();
  display.begin();
  edge.warmupSamples = MQ2_WARMUP_S;  // MQ-2 cần làm nóng ~60 s, chưa cảnh báo
  mtx = xSemaphoreCreateMutex();
  qSamples = xQueueCreate(4, sizeof(SensorData));
  qOut = xQueueCreate(12, sizeof(OutMsg));
  mqtt.begin(DEVICE_ID, onMessage);
  configTzTime(TZ_INFO, NTP_SERVER);
  esp_task_wdt_init(WDT_TIMEOUT_S, true);  // Task WDT: treo > 30 s -> reset
  xTaskCreatePinnedToCore(TaskSensors, "sensors", 4096, nullptr, 3, nullptr, 1);
  xTaskCreatePinnedToCore(TaskEdgeAI, "edgeai", 8192, nullptr, 4, nullptr, 1);
  xTaskCreatePinnedToCore(TaskNetwork, "network", 10240, nullptr, 2, nullptr, 0);
}

void loop() { vTaskDelete(nullptr); }
