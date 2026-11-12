# CHƯA CÓ MODEL — chưa có dữ liệu khí/khói đo thật để huấn luyện.
# Firmware chạy ở chế độ RULE (luật ngưỡng ppm + tốc độ tăng, xem alert.py) cho tới khi có model.
#
# Sinh model thật: thu dữ liệu bằng tools/label_logger.py rồi chạy
#     cd ml && python -m aiot_ml.train_gas_edge --data data/raw/gas_labeled.csv
# File này sẽ bị ghi đè bởi ml/mlcore/export_micropython.py (AVAILABLE = True).
AVAILABLE = False
VERSION = "none"
N_FEATURES = 10
N_CLASSES = 4
CLASS_LABEL = (0, 1, 2, 3)
CLASS_NAME = ("Normal", "Advisory", "Warning", "Danger")


def predict_proba(x):
    """Không có model: luôn trả về lớp 0 (Normal). EdgeAI không gọi hàm này khi AVAILABLE = False."""
    return 0, [1.0, 0.0, 0.0, 0.0]
