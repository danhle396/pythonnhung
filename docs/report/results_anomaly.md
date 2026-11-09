# Phát hiện bất thường ở cloud

Dữ liệu: **simulated** — 20 ngày train (bình thường), 10 ngày test có 4 sự cố rò rỉ chậm cài vào.

| Phương pháp | ROC-AUC | Precision | Recall | Sự cố phát hiện | Trễ trung vị (phút) | Cửa sổ báo nhầm/ngày |
|---|---|---|---|---|---|---|
| IsolationForest | 0.935 | 0.46 | 0.33 | 4/4 | 90.0 | 2.61 |
| HourlyZScore | 0.836 | 0.08 | 0.92 | 4/4 | 10.0 | 72.85 |

CUSUM trên R0 hằng ngày: trôi bắt đầu ngày 18, báo động đầu tiên ngày 20 ⇒ đề xuất hiệu chuẩn lại MQ-2.
