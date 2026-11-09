#!/bin/sh
# (Nâng cao) Tạo CA tự ký + chứng chỉ server cho MQTT TLS cổng 8883.
# Nhúng certs/ca.crt vào firmware/include/secrets.h (MQTT_CA_CERT) và bật MQTT_USE_TLS.
set -e
D="$(cd "$(dirname "$0")" && pwd)/certs"
CN="${1:-localhost}"
mkdir -p "$D"
openssl req -x509 -new -nodes -newkey rsa:2048 -days 3650 -subj "/CN=VKU-AIoT-CA" -keyout "$D/ca.key" -out "$D/ca.crt"
openssl req -new -nodes -newkey rsa:2048 -subj "/CN=$CN" -keyout "$D/server.key" -out "$D/server.csr"
printf "subjectAltName=DNS:%s,DNS:localhost,IP:127.0.0.1\n" "$CN" > "$D/ext.cnf"
openssl x509 -req -in "$D/server.csr" -CA "$D/ca.crt" -CAkey "$D/ca.key" -CAcreateserial -days 825 \
  -extfile "$D/ext.cnf" -out "$D/server.crt"
echo "Chứng chỉ ở $D (CN=$CN)"
