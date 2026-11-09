#include "storage.h"

#include <LittleFS.h>
#include <Preferences.h>

#include "config.h"

static const char* FILE_OLD = "/offline_a.jsonl";
static const char* FILE_CUR = "/offline_b.jsonl";
static Preferences prefs;
static const size_t HALF = OFFLINE_MAX_RECORDS / 2;

bool Storage::begin() {
  ok_ = LittleFS.begin(true);  // format nếu chưa có
  if (ok_) {
    countA_ = countLines(FILE_OLD);
    countB_ = countLines(FILE_CUR);
  }
  prefs.begin("aiot", false);
  return ok_;
}

size_t Storage::countLines(const char* path) {
  if (!LittleFS.exists(path)) return 0;
  File f = LittleFS.open(path, "r");
  size_t n = 0;
  while (f.available()) if (f.read() == '\n') ++n;
  f.close();
  return n;
}

bool Storage::append(const char* topic, const char* payload) {
  if (!ok_) return false;
  if (countB_ >= HALF) {  // xoay vòng: bỏ file cũ nhất, file hiện tại thành file cũ
    LittleFS.remove(FILE_OLD);
    LittleFS.rename(FILE_CUR, FILE_OLD);
    countA_ = countB_;
    countB_ = 0;
  }
  File f = LittleFS.open(FILE_CUR, "a");
  if (!f) return false;
  f.print(topic);
  f.print('\t');
  f.print(payload);
  f.print('\n');
  f.close();
  ++countB_;
  return true;
}

size_t Storage::replay(const std::function<bool(const String&, const String&)>& fn, size_t maxRecords) {
  if (!ok_ || pending() == 0) return 0;
  size_t sent = 0;
  const char* files[2] = {FILE_OLD, FILE_CUR};
  for (int i = 0; i < 2 && sent < maxRecords; ++i) {
    if (!LittleFS.exists(files[i])) continue;
    File f = LittleFS.open(files[i], "r");
    String rest;  // các dòng chưa gửi được sẽ ghi lại
    bool stop = false;
    while (f.available()) {
      String line = f.readStringUntil('\n');
      if (line.length() == 0) continue;
      if (stop || sent >= maxRecords) { rest += line + "\n"; stop = true; continue; }
      int tab = line.indexOf('\t');
      if (tab < 0) continue;
      if (fn(line.substring(0, tab), line.substring(tab + 1))) ++sent;
      else { rest += line + "\n"; stop = true; }
    }
    f.close();
    LittleFS.remove(files[i]);
    size_t remain = 0;
    if (rest.length()) {
      File w = LittleFS.open(files[i], "w");
      w.print(rest);
      w.close();
      for (size_t k = 0; k < rest.length(); ++k) if (rest[k] == '\n') ++remain;
    }
    (i == 0 ? countA_ : countB_) = remain;
    if (stop) break;
  }
  return sent;
}

void Storage::loadConfig(DeviceConfig& c) {
  c.rule.th1 = prefs.getFloat("th1", DEF_TH1_PPM);
  c.rule.th2 = prefs.getFloat("th2", DEF_TH2_PPM);
  c.rule.th3 = prefs.getFloat("th3", DEF_TH3_PPM);
  c.rule.slope1 = prefs.getFloat("slope1", DEF_SLOPE1);
  c.rule.dtemp3 = prefs.getFloat("dtemp3", DEF_DTEMP3);
  c.rule.hyst = prefs.getFloat("hyst", DEF_HYST);
  c.rule.debounceUp = prefs.getInt("dbUp", DEF_DEBOUNCE_UP);
  c.rule.debounceDown = prefs.getInt("dbDown", DEF_DEBOUNCE_DOWN);
  c.r0Kohm = prefs.getFloat("r0", MQ2_R0_DEFAULT_KOHM);
  c.telemetryMs = prefs.getUInt("telMs", TELEMETRY_PERIOD_MS);
  c.edgeMode = prefs.getUChar("mode", 2);
  c.version = prefs.getUInt("cfgVer", 0);
}

void Storage::saveConfig(const DeviceConfig& c) {
  prefs.putFloat("th1", c.rule.th1);
  prefs.putFloat("th2", c.rule.th2);
  prefs.putFloat("th3", c.rule.th3);
  prefs.putFloat("slope1", c.rule.slope1);
  prefs.putFloat("dtemp3", c.rule.dtemp3);
  prefs.putFloat("hyst", c.rule.hyst);
  prefs.putInt("dbUp", c.rule.debounceUp);
  prefs.putInt("dbDown", c.rule.debounceDown);
  prefs.putFloat("r0", c.r0Kohm);
  prefs.putUInt("telMs", c.telemetryMs);
  prefs.putUChar("mode", c.edgeMode);
  prefs.putUInt("cfgVer", c.version);
}

// seq tăng dần, lưu NVS theo khối 100 để không ghi flash mỗi lần (sau reboot nhảy cóc tối đa 100)
uint32_t Storage::nextSeq() {
  static uint32_t seq = 0, reserved = 0;
  if (seq >= reserved) {
    seq = prefs.getUInt("seq", 0);
    reserved = seq + 100;
    prefs.putUInt("seq", reserved);
  }
  return ++seq;
}
