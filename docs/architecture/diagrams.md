# Sơ đồ kiến trúc và CSDL

Mọi sơ đồ của dự án đều là file **draw.io**. Mở bằng [diagrams.net](https://app.diagrams.net) (File → Open) để xem và sửa.

| File                                               | Trang | Nội dung                                          | Ảnh xuất (dùng trong slide)    |
| -------------------------------------------------- | ----- | ------------------------------------------------- | ------------------------------ |
| `docs/architecture/system_block_diagram.drawio`    | 1     | Sơ đồ khối hệ thống                               | `system_block_diagram-1.png`   |
|                                                    | 2     | Lược đồ CSDL                                      | `system_block_diagram-2.png`   |
|                                                    | 3     | Luồng cảnh báo khí (sơ đồ tuần tự)                | `system_block_diagram-3.png`   |
| `docs/hardware/wiring.drawio`                      | 1–2   | Đấu dây: cảm biến; còi, LED, màn TFT              | `wiring-1.png`, `wiring-2.png` |

Sửa xong thì xuất lại ảnh (ảnh nằm cạnh file `.drawio`), rồi thay ảnh trong slide `docs/report/VKU_SLIDE_Newbie.pptx`:

```bash
python tools/render_drawio.py docs/architecture/system_block_diagram.drawio
python tools/render_drawio.py docs/hardware/wiring.drawio
```

## Sơ đồ khối hệ thống (trang 1)

Đọc từ trái sang phải:

1. **Cảm biến** (5 loại) → **ESP32**: lọc nhiễu và tự quyết định cấp cảnh báo khí, bật còi, LED, màn TFT.
2. ESP32 ⇄ **Mosquitto** ⇄ **Backend** qua MQTT. Trạm gửi số đo và cảnh báo lên (QoS 0, kèm số thứ tự `seq` và đệm
   offline); cloud gửi lệnh, cấu hình và dự báo xuống.
3. **Backend** lưu dữ liệu vào TimescaleDB, dự báo nhiệt độ/độ ẩm bằng GBDT từ Open-Meteo, gửi Telegram/Email và phục vụ
   dashboard. Xác suất mưa lấy từ Open-Meteo Ensemble (ECMWF/GFS/ICON), hiệu chỉnh theo số Google nhập ở dashboard,
   cộng thêm khi YL-83 đang báo mưa.
4. **Huấn luyện offline** (`ml/`) tạo mô hình dự báo thời tiết cho backend. Cảnh báo khí không dùng mô hình AI.

Ý chính: **trạm tự quyết định cảnh báo, cloud lo phần nặng.**

|                 | Edge: trạm ESP32                                       | Cloud: Docker Compose                                        |
| --------------- | ------------------------------------------------------ | ------------------------------------------------------------ |
| Làm gì          | Đọc cảm biến, lọc nhiễu, phân cấp khí 0–3, bật đèn/còi | Lưu trữ, gửi thông báo, leo thang cảnh báo, dự báo thời tiết |
| Khi mất mạng    | Vẫn cảnh báo, dữ liệu được đệm trên flash              | Nhận LWT và báo trạm offline                                 |
| Độ trễ cảnh báo | Dưới 1 s                                               | Vài giây (gửi Telegram)                                      |

Cấp cảnh báo khí do **luật 4 cấp** trên trạm quyết định (ngưỡng ppm, độ dốc ppm, nhiệt độ tăng + hysteresis,
debounce). Cloud chỉ có thể **nâng** cấp bằng lệnh `escalate` khi thấy ppm tăng đều trong 10 phút, không hạ cấp của trạm.

## Lược đồ CSDL (trang 2)

Mọi bảng đều gắn với `devices` (mỗi trạm một dòng), trừ `model_registry` và `google_rain_obs` (màu xám trong sơ đồ).
Nguồn chuẩn: `backend/app/db/models.py`.

| Bảng              | Lưu gì                                                                                       |
| ----------------- | -------------------------------------------------------------------------------------------- |
| `devices`         | Thông tin trạm: tên, toạ độ, firmware, lần cuối thấy, online/offline                         |
| `telemetry`       | Số đo cảm biến (5 s/lần). Khoá `(device_id, ts, seq)` để không ghi trùng khi trạm gửi bù     |
| `alerts`          | Cảnh báo. `source = edge` nếu trạm phát, `cloud` nếu backend tự tạo (ví dụ `device_offline`) |
| `notifications`   | Từng lần gửi Telegram/Email cho một cảnh báo, kèm độ trễ và kết quả                          |
| `forecasts`       | Dự báo 1/3/6 giờ, kèm cận dưới và cận trên                                                   |
| `google_rain_obs` | Xác suất mưa của Google do người dùng nhập tay, dùng để hiệu chỉnh dự báo mưa                |
| `device_configs`  | Các phiên bản cấu hình đã gửi xuống trạm và trạm đã xác nhận (ack) chưa                      |
| `commands`        | Lệnh đã gửi xuống trạm (`mute`, `calibrate`…) và trạm đã xác nhận chưa                       |
| `model_registry`  | Các mô hình ML, độ đo, mô hình nào đang được dùng                                            |

Sửa bảng/cột trong `models.py` thì cập nhật trang 2 cho khớp. Luồng cảnh báo (trang 3) được giải thích trong `sequences.md`.
