#include "mqtt_client.h"

#include <PubSubClient.h>
#include <WiFi.h>

#include "config.h"
#include "secrets.h"

#ifdef MQTT_USE_TLS
#include <WiFiClientSecure.h>
static WiFiClientSecure net;
#else
static WiFiClient net;
#endif
static PubSubClient client(net);
static MqttHandler handler;
static String prefix;

static void onMqtt(char* topic, byte* payload, unsigned int len) {
  String t(topic);
  if (handler && t.startsWith(prefix)) handler(t.c_str() + prefix.length(), payload, len);
}

String MqttLink::topic(const char* suffix) const { return prefix + suffix; }

void MqttLink::begin(const char* deviceId, MqttHandler onMessage) {
  id_ = deviceId;
  prefix = String(TOPIC_PREFIX) + deviceId + "/";
  handler = onMessage;
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
#ifdef MQTT_USE_TLS
  net.setCACert(MQTT_CA_CERT);
#endif
  client.setServer(MQTT_HOST, MQTT_PORT);
  client.setBufferSize(MQTT_MAX_PACKET_SIZE);
  client.setKeepAlive(15);
  client.setCallback(onMqtt);
}

bool MqttLink::connectMqtt() {
  String will = topic("status");
  String cid = id_ + "-" + String((uint32_t)ESP.getEfuseMac(), HEX);
  // LWT: broker tự publish {"state":"offline"} (retain) khi thiết bị mất kết nối bất thường
  if (!client.connect(cid.c_str(), MQTT_USER, MQTT_PASS, will.c_str(), 1, true, "{\"state\":\"offline\"}")) {
    return false;
  }
  client.subscribe(topic("cmd").c_str(), 1);
  client.subscribe(topic("config").c_str(), 1);
  client.subscribe(topic("forecast").c_str(), 1);
  ++reconnects_;
  backoff_ = 2000;
  return true;
}

bool MqttLink::loop() {
  if (WiFi.status() != WL_CONNECTED) return false;
  if (!client.connected()) {
    uint32_t now = millis();
    if (now - lastTry_ < backoff_) return false;
    lastTry_ = now;
    if (!connectMqtt()) {
      backoff_ = backoff_ < 30000 ? backoff_ * 2 : 30000;  // exponential backoff
      Serial.printf("[MQTT] kết nối thất bại rc=%d, thử lại sau %lu ms\n", client.state(), (unsigned long)backoff_);
      return false;
    }
    Serial.println("[MQTT] đã kết nối");
  }
  client.loop();
  return true;
}

bool MqttLink::connected() { return WiFi.status() == WL_CONNECTED && client.connected(); }

// PubSubClient chỉ hỗ trợ publish QoS 0; QoS 1 phía edge được bảo đảm bằng seq + đệm offline + chống trùng ở cloud.
bool MqttLink::publish(const char* suffix, const char* payload, bool retain, uint8_t) {
  if (!connected()) return false;
  return client.publish(topic(suffix).c_str(), payload, retain);
}

int MqttLink::rssi() { return WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0; }
