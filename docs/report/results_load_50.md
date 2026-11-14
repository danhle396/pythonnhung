# Load test — 50 thiết bị × 1.0 msg/s × 30 s (QoS 1)

| Chỉ số               | Giá trị            |
| -------------------- | ------------------ |
| Gửi / nhận           | 1400 / 1400        |
| Mất gói (broker)     | 0.000 %            |
| Thông lượng          | 46.7 msg/s         |
| Độ trễ broker P50    | 0.6 ms             |
| Độ trễ broker P95    | 2.2 ms             |
| Độ trễ broker P99    | 4.1 ms             |
| Bản ghi vào DB       | 1400 (mất 0.000 %) |
| CPU backend TB / max | 61.4 % / 132.8 %   |
| RAM backend          | 183 MB             |
