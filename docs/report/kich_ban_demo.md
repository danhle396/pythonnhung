# Kịch bản demo và video (3–5 phút)

Hai phương án: **A — có phần cứng** (bảo vệ trực tiếp), **B — không có phần cứng** (simulator, dùng để quay video
hoặc dự phòng khi thiết bị gặp sự cố). Cả hai dùng chung dashboard và backend Docker.

## Chuẩn bị (trước buổi demo 10 phút)

```bash
docker compose up -d --build                 # hoặc chạy backend + mosquitto local theo README
# Telegram: điền TELEGRAM_TOKEN, TELEGRAM_CHAT_ID trong .env rồi `docker compose up -d backend`
# mở sẵn 3 cửa sổ: dashboard http://localhost:8501 · Telegram trên điện thoại (chiếu màn hình) · terminal
```
- Phương án A: trạm đã cấp nguồn ≥ 10 phút (MQ-2 cần làm nóng), OLED hiện "Online", dashboard Tổng quan cập nhật.
- Phương án B: `python tools/simulator.py --backfill-hours 48 --period 5` chạy trước để có 48 giờ lịch sử + dự báo.
- Kiểm tra an toàn (A): phòng thoáng, không có nguồn lửa khác; dùng bật lửa gas **không bật đá**, chỉ xả gas 1–2 giây
  cách cảm biến ~5 cm; có người giám sát.

## Kịch bản (mốc thời gian cho video ~4 phút)

| Thời gian | Hành động | Lời thuyết minh gợi ý | Cần thấy |
|---|---|---|---|
| 0:00–0:30 | Giới thiệu trạm (ảnh/hộp thật), sơ đồ kiến trúc | "Trạm ESP32 5 cảm biến, AI lai edge–cloud: edge quyết định cảnh báo, cloud dự báo và leo thang." | Slide kiến trúc |
| 0:30–1:10 | Dashboard → **Tổng quan**, **Biểu đồ** 24 giờ | "Dữ liệu 10 giây/lần qua MQTT vào TimescaleDB." | Số đo thay đổi realtime |
| 1:10–1:40 | **Dự báo**: đường thực tế vs dự báo + khoảng tin cậy, xác suất mưa | "GBDT tự viết bằng NumPy, MAE nhiệt độ 1 giờ 0,30 °C." | Biểu đồ dự báo |
| 1:40–2:40 | **A:** xả gas gần MQ-2. **B:** `python tools/simulator.py --events "5:lpg_mid" --period 5` | "Edge tăng cấp 1 → 2 → 3 trong vài giây, không chờ cloud." | LED vàng → đỏ, còi; OLED; dashboard đổi màu |
| 2:40–3:10 | Telegram nhận tin cấp 2, cấp 3 (nhắc lại mỗi phút) → bấm **✅ Đã xử lý** | "Cloud gửi thông báo theo cấp, nhắc lại tới khi có người xác nhận." | Tin nhắn + nút ack; trang Cảnh báo hiện ✅ |
| 3:10–3:40 | **A:** rút Wi-Fi/tắt router rồi xả gas lần nữa. **B:** dừng simulator (Ctrl+C) | "Mất mạng: còi vẫn kêu vì quyết định ở edge; dữ liệu vào đệm LittleFS, gửi bù khi có mạng." / "Broker phát LWT, dashboard báo offline." | Còi vẫn kêu / trạng thái Offline + cảnh báo `device_offline` |
| 3:40–4:10 | Bật lại mạng → dữ liệu gửi bù xuất hiện liền mạch trên Biểu đồ; trang **Thiết bị**: đổi ngưỡng, thiết bị ack | "Cấu hình có phiên bản, thiết bị xác nhận." | Biểu đồ không bị hở; config acked |
| 4:10–4:30 | Trang **Mô hình** + kết luận | "Toàn bộ ML tự viết, 42 + 15 + 12 + 7 test, Docker một lệnh." | Bảng registry |

## Mẹo quay video

- Quay màn hình bằng OBS (Windows) hoặc Xbox Game Bar (Win + Alt + R); quay điện thoại cảnh còi/LED đặt cạnh màn hình
  (picture-in-picture khi dựng).
- Bật `--period 5` cho simulator để biểu đồ thay đổi nhanh; tắt thông báo hệ điều hành khác khi quay.
- Ghi rõ trên video nếu dùng phương án B: "dữ liệu khí mô phỏng".

## Câu hỏi thường gặp khi bảo vệ (chuẩn bị trả lời)

1. *Vì sao không dùng scikit-learn?* — Yêu cầu đề tài; tự viết giúp hiểu thuật toán và xuất sang C dễ; tính đúng được kiểm
   chứng bằng gradient check, dữ liệu đồ chơi và so khớp C/Python.
2. *Vì sao fusion lấy max?* — Bài toán an toàn ưu tiên Recall; model chỉ được báo sớm hơn, không được hạ cấp mà rule đưa ra.
3. *MQ-2 có đo chính xác ppm không?* — Không; ppm tương đối theo đường cong datasheet, phụ thuộc R₀, nhiệt, ẩm. Vì vậy dùng
   thêm xu hướng (độ dốc, độ lệch nền) và hiệu chuẩn R₀ định kỳ, CUSUM phát hiện trôi.
4. *QoS 0 có mất dữ liệu không?* — Có thể; bù bằng `seq`, đệm offline, chống trùng (device_id, ts, seq) ở backend;
   lệnh từ cloud dùng QoS 1.
5. *Dự báo dùng dữ liệu nào khi trạm mới lắp?* — Pretrain trên Open-Meteo 5 năm; khi trạm thiếu dữ liệu dùng Open-Meteo làm
   đầu vào; khi đủ ≥ 30 giờ dùng dữ liệu trạm + hiệu chỉnh bias.
