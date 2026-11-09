// Kết nối Wi-Fi + MQTT có tự kết nối lại, LWT, subscribe cmd/config/forecast.
#pragma once
#include <Arduino.h>
#include <functional>

using MqttHandler = std::function<void(const char* topicSuffix, const uint8_t* payload, unsigned int len)>;

class MqttLink {
 public:
  void begin(const char* deviceId, MqttHandler onMessage);
  // gọi liên tục trong TaskNetwork; trả về true khi đang kết nối MQTT
  bool loop();
  bool connected();
  bool publish(const char* suffix, const char* payload, bool retain = false, uint8_t qos = 0);
  int rssi();
  uint32_t reconnects() const { return reconnects_; }
  String topic(const char* suffix) const;

 private:
  bool connectMqtt();
  String id_;
  uint32_t lastTry_ = 0, reconnects_ = 0, backoff_ = 2000;
};
