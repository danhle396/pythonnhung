# Các luồng xử lý chính

Ba tình huống quan trọng nhất, mỗi tình huống là một chuỗi bản tin giữa các thành phần:

| Tình huống            | Bắt đầu khi                          | Kết thúc khi                      |
| --------------------- | ------------------------------------ | --------------------------------- |
| Cảnh báo khí/khói     | MQ-2 đo thấy khí tăng                | Người dùng bấm "Đã xử lý"         |
| Dự báo thời tiết      | Cứ 10 phút một lần                   | Dự báo hiện trên dashboard và TFT |
| Đổi cấu hình thiết bị | Người dùng sửa ngưỡng trên dashboard | Trạm xác nhận đã áp dụng          |

## Luồng cảnh báo khí/khói

Sơ đồ tuần tự: `system_block_diagram.drawio`, trang 3 (ảnh `system_block_diagram-3.png`).

**Điểm cần nhớ**

- **Trạm tự quyết định** (bước 1–3). Đèn và còi đổi trong dưới 1 s, không cần mạng.
- **Mất mạng không mất cảnh báo.** Còi vẫn kêu; bản tin được ghi vào flash và gửi bù khi có mạng lại.
- **Cloud gửi thông báo theo cấp** (bước 6): cấp 2 gửi Telegram; cấp 3 gửi Telegram và Email.
- **Leo thang** (bước 7–10): cứ 30 s, cloud xem ppm trong 10 phút gần nhất. Nếu ppm tăng đều, cloud gửi lệnh
  `escalate` để trạm nâng cấp.
- **Nhắc lại** (bước 11–13): cảnh báo cấp 3 được gửi lại mỗi 60 s cho tới khi có người bấm "✅ Đã xử lý".

## Luồng dự báo thời tiết

1. Cứ 10 phút, forecast service lấy quan trắc Open-Meteo 4 ngày gần nhất và Open-Meteo Ensemble các giờ tới, cùng mức
   mưa YL-83 mới nhất của trạm.
2. GBDT (LightGBM) dự báo nhiệt độ, độ ẩm cho 1/3/6 giờ tới, kèm khoảng tin cậy 95 %.
3. Xác suất mưa lấy từ ensemble, hiệu chỉnh theo số Google nhập tay. Trạm đang báo mưa thì cộng thêm điểm.
   Không lấy được ensemble thì dùng GBDT.
4. Kết quả lưu vào bảng `forecasts`, gửi `forecast` (retain) về màn TFT và đẩy WebSocket cho dashboard.

**Điểm cần nhớ**

- **Dự báo không dùng số đo nhiệt độ/độ ẩm của trạm**, vì trạm đặt trong nhà nên số đo không đại diện cho thời tiết.
- **Không có mạng:** bỏ qua lượt đó, không tự đoán.

## Luồng cấu hình thiết bị

1. Dashboard gửi `PUT /api/devices/{id}/config`.
2. API kiểm tra `th1 < th2 < th3`, tăng `version`, lưu vào `device_configs`.
3. API gửi `config` (retain, QoS 1) qua Mosquitto xuống ESP32.
4. ESP32 kiểm tra dải giá trị, áp dụng, lưu `/config.json`, rồi gửi `ack`.
5. Backend nhận `ack` và đánh dấu `device_configs.acked = true`.

**Điểm cần nhớ**

- Mỗi lần sửa cấu hình tạo một **phiên bản mới**, nên luôn biết trạm đang chạy bản nào.
- Bản tin `config` được giữ lại trên broker (retain). Trạm khởi động lại sẽ nhận ngay cấu hình mới nhất.
- Cấu hình sai bị trạm từ chối bằng `ack` có `ok: false`.
