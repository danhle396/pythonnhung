# Load test — 20 thiết bị × 1.0 msg/s × 30 s (QoS 1)

| Chỉ số               | Giá trị           |
| -------------------- | ----------------- |
| Gửi / nhận           | 560 / 560         |
| Mất gói (broker)     | 0.000 %           |
| Thông lượng          | 18.7 msg/s        |
| Độ trễ broker P50    | 0.6 ms            |
| Độ trễ broker P95    | 2.0 ms            |
| Độ trễ broker P99    | 3.1 ms            |
| Bản ghi vào DB       | 560 (mất 0.000 %) |
| CPU backend TB / max | 54.5 % / 87.5 %   |
| RAM backend          | 182 MB            |
