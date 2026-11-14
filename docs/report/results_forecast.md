# Kết quả dự báo thời tiết (tập test 2025)

Dữ liệu: Open-Meteo theo giờ tại VKU. Train 2021-01-02 → 2023-12-31, val 2024, test 2025-01-01 → 2025-12-31. 56 feature.

Thư viện: Holt-Winters — statsmodels; Ridge, Logistic — scikit-learn; GBDT — LightGBM; GRU — PyTorch. Độ đo — scikit-learn.

## Hồi quy — MAE (RMSE)

| Mô hình        | temp_1h           | temp_3h           | temp_6h           | hum_1h            | hum_3h            | hum_6h            |
| -------------- | ----------------- | ----------------- | ----------------- | ----------------- | ----------------- | ----------------- |
| Persistence    | 0.593 (0.831)     | 1.559 (2.107)     | 2.759 (3.496)     | 2.968 (4.256)     | 7.541 (10.253)    | 13.210 (16.681)   |
| Seasonal naive | 0.994 (1.387)     | 0.993 (1.387)     | 0.992 (1.386)     | 4.919 (6.877)     | 4.923 (6.883)     | 4.930 (6.903)     |
| Holt-Winters   | 0.369 (0.530)     | 0.796 (1.085)     | 1.221 (1.602)     | 2.206 (3.097)     | 4.547 (6.109)     | 6.682 (8.640)     |
| Ridge          | 0.348 (0.490)     | 0.690 (0.912)     | 0.837 (1.109)     | 2.045 (2.846)     | 3.822 (5.070)     | 4.515 (5.908)     |
| GBDT           | **0.299 (0.442)** | 0.538 (0.757)     | **0.688 (0.947)** | **1.870 (2.664)** | 3.242 (4.449)     | **3.954 (5.380)** |
| GRU (PyTorch)  | 0.306 (0.447)     | **0.536 (0.746)** | 0.697 (0.950)     | 1.894 (2.674)     | **3.240 (4.425)** | 4.075 (5.458)     |

## Dự báo mưa — F1 / ROC-AUC / Brier (ngưỡng chọn trên val)

| Mô hình     | rain_1h               | rain_3h               | rain_6h               |
| ----------- | --------------------- | --------------------- | --------------------- |
| Persistence | 0.826 / 0.865 / 0.124 | 0.783 / 0.813 / 0.178 | 0.723 / 0.766 / 0.254 |
| Logistic    | 0.828 / 0.931 / 0.096 | 0.827 / 0.915 / 0.115 | 0.839 / 0.901 / 0.127 |
| GBDT        | 0.830 / 0.939 / 0.092 | 0.833 / 0.926 / 0.107 | 0.851 / 0.913 / 0.118 |

## Thời gian huấn luyện GBDT (giây) / số cây

- temp_1h: 0.4s, 261 cây, suy luận 1.7 µs/mẫu
- temp_3h: 0.6s, 457 cây, suy luận 3.9 µs/mẫu
- temp_6h: 0.7s, 333 cây, suy luận 2.3 µs/mẫu
- hum_1h: 0.5s, 311 cây, suy luận 2.4 µs/mẫu
- hum_3h: 0.8s, 309 cây, suy luận 2.8 µs/mẫu
- hum_6h: 0.6s, 198 cây, suy luận 1.8 µs/mẫu
- rain_1h: GBDT 0.4s (280 cây), Logistic 0.7s
- rain_3h: GBDT 0.4s (266 cây), Logistic 1.0s
- rain_6h: GBDT 0.3s (202 cây), Logistic 0.8s
- GRU (PyTorch, 6 đầu ra chung): 24s

## Mức quan trọng feature (temp_1h, GBDT)

| Feature          | Gain (chuẩn hoá) |     | Feature          | Permutation ΔMAE |
| ---------------- | ---------------- | --- | ---------------- | ---------------- |
| hour_sin         | 0.373            |     | hour_sin         | 0.2235           |
| temp_d1          | 0.085            |     | cos_zenith       | 0.1020           |
| cos_zenith       | 0.072            |     | temp_d1          | 0.0653           |
| pres_d3          | 0.072            |     | hour_cos         | 0.0260           |
| hours_since_rain | 0.048            |     | temp_mean24      | 0.0182           |
| pres_trend3      | 0.039            |     | hours_since_rain | 0.0099           |
| sky_mean3        | 0.028            |     | pres_d3          | 0.0074           |
| temp_mean24      | 0.028            |     | temp             | 0.0068           |
| hour_cos         | 0.024            |     | pres_d1          | 0.0058           |
| temp             | 0.021            |     | sky_mean3        | 0.0056           |
