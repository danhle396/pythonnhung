"""mlcore — thư viện Machine Learning tự xây dựng từ đầu cho đề tài AIoT VKU.

Chỉ dùng NumPy cho tính toán mảng (pandas chỉ dùng ở tầng xử lý dữ liệu bên ngoài).
Không phụ thuộc scikit-learn, XGBoost, LightGBM, TensorFlow, PyTorch, statsmodels...

Mọi model có giao diện chung:
    fit(X, y) -> self
    predict(X) -> ndarray
    predict_proba(X) -> ndarray          (với model phân loại)
    to_dict() -> dict / from_dict(d)     (tuần tự hoá)
"""

__version__ = "1.0.0"

from . import (  # noqa: F401
    anomaly,
    ensemble,
    explain,
    linear,
    metrics,
    model_selection,
    nn,
    optim,
    preprocessing,
    serialize,
    smoothing,
    tree,
)
