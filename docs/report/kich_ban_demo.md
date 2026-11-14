# Kịch bản demo và video (3–5 phút)

Demo chạy trên **trạm thật** (dự án chỉ dùng số liệu đo thật, không có bộ giả lập). Dùng chung dashboard và backend
Docker. Quay video dự phòng trước buổi bảo vệ phòng khi thiết bị gặp sự cố.

## Chuẩn bị (trước buổi demo 10 phút)

```bash
docker compose up -d --build                 # hoặc chạy backend + mosquitto local theo README
# Telegram: điền TELEGRAM_TOKEN, TELEGRAM_CHAT_ID trong .env rồi `docker compose up -d backend`
# mở sẵn 3 cửa sổ: dashboard http://localhost:8501 · Telegram trên điện thoại (chiếu màn hình) · terminal
```
- Trạm đã cấp nguồn ≥ 10 phút (MQ-2 cần làm nóng), màn TFT hiện "W M" (Wi-Fi + MQTT), dashboard Tổng quan cập nhật. Trang Dự báo
  luôn có dữ liệu (đầu vào là Open-Meteo); bảng sai số so với trạm chỉ có ý nghĩa cho khoảng trạm đặt ngoài trời.
- Kiểm tra an toàn: phòng thoáng, không có nguồn lửa khác; dùng bật lửa gas **không bật đá**, chỉ xả gas 1–2 giây
  cách cảm biến ~5 cm; có người giám sát.

## Kịch bản (mốc thời gian cho video ~4 phút)

| Thời gian | Hành động                                                                                                    | Lời thuyết minh gợi ý                                                                                                                         | Cần thấy                                                                         |
| --------- | ------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| 0:00–0:30 | Giới thiệu trạm (ảnh/hộp thật), sơ đồ kiến trúc                                                              | "Trạm ESP32 5 cảm biến, AI lai edge–cloud: edge quyết định cảnh báo, cloud dự báo và leo thang."                                              | Slide kiến trúc                                                                  |
| 0:30–1:10 | Dashboard → **Tổng quan**, **Biểu đồ** 24 giờ                                                                | "Dữ liệu 10 giây/lần qua MQTT vào TimescaleDB."                                                                                               | Số đo thay đổi realtime                                                          |
| 1:10–1:40 | **Dự báo**: đường thực tế vs dự báo + khoảng tin cậy, xác suất mưa                                           | "GBDT (LightGBM), MAE nhiệt độ 1 giờ 0,30 °C."                                                                                                | Biểu đồ dự báo                                                                   |
| 1:40–2:40 | Xả gas gần MQ-2                                                                                              | "Edge tăng cấp 1 → 2 → 3 trong vài giây, không chờ cloud."                                                                                    | LED xanh nháy → đỏ, còi; màn TFT chuyển trang khí/khói nền đỏ; dashboard đổi màu |
| 2:40–3:10 | Telegram nhận tin cấp 2, cấp 3 (nhắc lại mỗi phút) → bấm **✅ Đã xử lý**                                     | "Cloud gửi thông báo theo cấp, nhắc lại tới khi có người xác nhận."                                                                           | Tin nhắn + nút ack; trang Cảnh báo hiện ✅                                       |
| 3:10–3:40 | Rút Wi-Fi/tắt router rồi xả gas lần nữa                                                                      | "Mất mạng: còi vẫn kêu vì quyết định ở edge; dữ liệu vào đệm offline trên flash, gửi bù khi có mạng. Broker phát LWT, dashboard báo offline." | Còi vẫn kêu; dashboard Offline + cảnh báo `device_offline`                       |
| 3:40–4:10 | Bật lại mạng → dữ liệu gửi bù xuất hiện liền mạch trên Biểu đồ; trang **Thiết bị**: đổi ngưỡng, thiết bị ack | "Cấu hình có phiên bản, thiết bị xác nhận."                                                                                                   | Biểu đồ không bị hở; config acked                                                |
| 4:10–4:30 | Trang **Mô hình** + kết luận                                                                                 | "Mô hình từ thư viện chuẩn, 21 + 21 + 33 + 8 test, Docker một lệnh."                                                                          | Bảng registry                                                                    |

## Mẹo quay video

- Quay màn hình bằng OBS (Windows) hoặc Xbox Game Bar (Win + Alt + R); quay điện thoại cảnh còi/LED đặt cạnh màn hình
  (picture-in-picture khi dựng).
- Đặt chu kỳ telemetry 1 s khi quay (`PUT /api/devices/station01/config {"telemetry_ms": 1000}`) để biểu đồ thay đổi
  nhanh; tắt thông báo hệ điều hành khác khi quay.

## Câu hỏi thường gặp khi bảo vệ (chuẩn bị trả lời)

1. *Vì sao dùng thư viện (scikit-learn, LightGBM, statsmodels, PyTorch)?* — Để bảo đảm tính đúng đắn của dự báo: các cài
   đặt này được kiểm chứng rộng rãi, kết quả so sánh mô hình đáng tin và người khác chạy lại được. Phần tự làm là feature,
   cách chia dữ liệu, chọn mô hình và bộ xuất Random Forest sang MicroPython (unit test khớp scikit-learn, lệch 0).
2. *Vì sao fusion lấy max?* — Bài toán an toàn ưu tiên Recall; model chỉ được báo sớm hơn, không được hạ cấp mà rule đưa ra.
   *Sao chưa có model khí?* — Đề tài chỉ dùng số liệu đo thật; chưa đủ dữ liệu thí nghiệm MQ-2 có nhãn nên edge đang chạy
   rule, pipeline huấn luyện + xuất MicroPython đã sẵn sàng (`train_gas_edge --data`).
3. *MQ-2 có đo chính xác ppm không?* — Không; ppm tương đối theo đường cong datasheet, phụ thuộc R₀, nhiệt, ẩm. Vì vậy dùng
   thêm xu hướng (độ dốc, độ lệch nền) và hiệu chuẩn R₀ bằng lệnh `calibrate`.
4. *QoS 0 có mất dữ liệu không?* — Có thể; bù bằng `seq`, đệm offline, chống trùng (device_id, ts, seq) ở backend;
   lệnh từ cloud dùng QoS 1.
5. *Dự báo dùng dữ liệu nào khi trạm mới lắp?* — Mô hình học trên Open-Meteo 5 năm và luôn dự báo từ quan
   trắc Open-Meteo gần nhất. Trạm ở mặt đất, chủ yếu trong nhà, nên số đo trạm chỉ dùng để kiểm tra dự báo đúng/sai
   trong đêm đặt ngoài trời.
