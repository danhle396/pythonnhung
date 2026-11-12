# Sao chép thành credentials.py và điền thông tin thật. credentials.py nằm trong .gitignore.
WIFI_SSID = "your-wifi"
WIFI_PASS = "your-password"
MQTT_HOST = "192.168.1.10"   # IP máy chạy Mosquitto (docker compose hoặc cài trực tiếp)
MQTT_PORT = 1883
MQTT_USER = "station01"
MQTT_PASS = "change-me"
# TLS cổng 8883 (tuỳ chọn): chép broker/mosquitto/certs/ca.crt lên board rồi bật dòng dưới, MQTT_PORT = 8883
# MQTT_CA_FILE = "ca.crt"
