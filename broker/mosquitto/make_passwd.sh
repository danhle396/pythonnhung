#!/bin/sh
# Tạo file passwd cho Mosquitto từ biến môi trường (chạy 1 lần, hoặc tự chạy trong container mosquitto).
#   MQTT_BACKEND_PASS=... MQTT_DEVICE_PASS=... sh broker/mosquitto/make_passwd.sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$DIR/passwd}"
: > "$OUT"
mosquitto_passwd -b "$OUT" backend "${MQTT_BACKEND_PASS:-backend-pass}"
mosquitto_passwd -b "$OUT" dashboard "${MQTT_DASHBOARD_PASS:-dashboard-pass}"
for dev in ${MQTT_DEVICES:-station01 station02 station03}; do
  mosquitto_passwd -b "$OUT" "$dev" "${MQTT_DEVICE_PASS:-change-me}"
done
chmod 0700 "$OUT" 2>/dev/null || true
echo "Đã tạo $OUT"
