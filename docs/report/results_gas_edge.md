# Kết quả cảnh báo khí/khói tại edge

> Dữ liệu: **MÔ PHỎNG (gas_sim.py)**, 151324 mẫu 1 Hz. Số liệu dưới đây minh hoạ pipeline; cần chạy lại với dữ liệu thí nghiệm thật trước khi đưa vào báo cáo.

Model chọn: **{'model': 'RandomForest', 'n_estimators': 10, 'max_depth': 6}**

## Rule / Model / Hybrid (tập test)

| Chỉ số | Rule | Model | Hybrid |
|---|---|---|---|
| Macro-F1 (theo mẫu) | 0.569 | 0.827 | 0.615 |
| Recall cấp ≥2 (theo mẫu) | 0.843 | 0.895 | 0.920 |
| Precision cấp ≥2 (theo mẫu) | 0.615 | 0.821 | 0.606 |
| Recall cấp ≥2 (theo sự kiện) | 0.947 | 1.000 | 1.000 |
| Báo động giả ≥1 trên sự kiện nhiễu | 0.88 | 0.80 | 0.88 |
| Báo động giả ≥2 trên sự kiện nhiễu | 0.17 | 0.42 | 0.50 |
| Độ trễ phát hiện cấp ≥2, trung vị (s) | 8.0 | 8.0 | 7.0 |
| Độ trễ phát hiện cấp ≥2, P95 (s) | 19.0 | 19.299999999999997 | 12.299999999999997 |

## Recall theo từng cấp (theo mẫu)

| Cấp | Rule | Model | Hybrid |
|---|---|---|---|
| 0 Normal | 0.811 | 0.926 | 0.807 |
| 1 Advisory | 0.543 | 0.940 | 0.741 |
| 2 Warning | 0.438 | 0.839 | 0.497 |
| 3 Danger | 0.798 | 0.813 | 0.882 |

## Ma trận nhầm lẫn — Hybrid (hàng: thật, cột: dự đoán)

| | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| 0 | 19848 | 3269 | 997 | 476 |
| 1 | 69 | 2027 | 628 | 11 |
| 2 | 55 | 109 | 957 | 803 |
| 3 | 42 | 78 | 70 | 1416 |

## Tài nguyên edge & kiểm tra khớp C/Python

- 10 cây, 1016 nút, 513 lá, ước tính **17.0 kB flash**, RAM lúc chạy ≈ 656 B (bộ đệm cửa sổ + feature)
- C (g++) vs Python: lệch lớp **0**, lệch xác suất tối đa 0.0, 0.092 µs/lần trên PC (đo lại trên ESP32 bằng test_gas_model)

## Feature quan trọng (split gain)

- rs_r0: 0.326
- dtemp_min: 0.214
- gas_ppm: 0.169
- dev_base: 0.118
- slope10: 0.112
- std30: 0.038
- dhum_min: 0.010
- hum: 0.006
- lux_rel: 0.004
- temp: 0.003
