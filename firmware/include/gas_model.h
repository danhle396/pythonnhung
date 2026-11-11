// CHƯA CÓ MODEL — chưa có dữ liệu khí/khói đo thật để huấn luyện.
// Firmware chạy ở chế độ RULE (luật ngưỡng ppm + tốc độ tăng, xem alert.cpp) cho tới khi có model.
//
// Sinh model thật: thu dữ liệu bằng tools/label_logger.py rồi chạy
//     cd ml && python -m aiot_ml.train_gas_edge --data data/raw/gas_labeled.csv
// File này sẽ bị ghi đè bởi ml/mlcore/export_c.py (GAS_MODEL_AVAILABLE = 1).
#ifndef GAS_MODEL_H
#define GAS_MODEL_H

#include <stdint.h>

#define GAS_MODEL_AVAILABLE 0
#define GAS_MODEL_VERSION "none"
#define GAS_MODEL_N_FEATURES 10
#define GAS_MODEL_N_CLASSES 4

static const int8_t gas_model_class_label[4] = {0, 1, 2, 3};
static const char* const gas_model_class_name[4] = {"Normal", "Advisory", "Warning", "Danger"};

/* Không có model: luôn trả về cấp 0 (Normal). EdgeAI không gọi hàm này khi GAS_MODEL_AVAILABLE = 0. */
static inline int gas_model_predict_proba(const float* x, float* proba) {
    (void)x;
    proba[0] = 1.0f;
    for (int k = 1; k < GAS_MODEL_N_CLASSES; ++k) proba[k] = 0.0f;
    return 0;
}

static inline int gas_model_predict(const float* x) {
    float p[GAS_MODEL_N_CLASSES];
    return gas_model_class_label[gas_model_predict_proba(x, p)];
}

#endif  // GAS_MODEL_H
