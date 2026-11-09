// So khớp predict() của gas_model.h (C) với Python trên cùng vector kiểm thử (task.md 8.2).
// Chạy được cả trên PC (pio test -e native -f test_gas_model) lẫn trên ESP32 (pio test -e esp32dev -f test_gas_model)
// — trên ESP32 còn đo thời gian suy luận (µs).
#include <math.h>
#include <unity.h>

#include "gas_model.h"
#include "gas_model_testvec.h"

#ifdef ARDUINO
#include <Arduino.h>
#endif

void setUp() {}
void tearDown() {}

static void test_c_matches_python() {
  int bad = 0;
  float maxdiff = 0;
  for (int i = 0; i < GAS_MODEL_N_TEST; ++i) {
    float p[GAS_MODEL_N_CLASSES];
    int c = gas_model_predict_proba(gas_model_test_x[i], p);
    if (c != gas_model_test_class_idx[i]) ++bad;
    for (int k = 0; k < GAS_MODEL_N_CLASSES; ++k) {
      float d = fabsf(p[k] - gas_model_test_proba[i][k]);
      if (d > maxdiff) maxdiff = d;
    }
  }
  TEST_ASSERT_EQUAL_INT(0, bad);
  TEST_ASSERT_TRUE(maxdiff < 1e-5f);
}

#ifdef ARDUINO
static void test_inference_time() {
  float p[GAS_MODEL_N_CLASSES];
  uint32_t t0 = micros();
  for (int r = 0; r < 10; ++r)
    for (int i = 0; i < GAS_MODEL_N_TEST; ++i) gas_model_predict_proba(gas_model_test_x[i], p);
  float us = (micros() - t0) / (10.0f * GAS_MODEL_N_TEST);
  char msg[64];
  snprintf(msg, sizeof msg, "ESP32 inference: %.2f us/sample", us);
  TEST_MESSAGE(msg);
  TEST_ASSERT_TRUE(us < 1000.0f);
}

void setup() {
  delay(2000);
  UNITY_BEGIN();
  RUN_TEST(test_c_matches_python);
  RUN_TEST(test_inference_time);
  UNITY_END();
}
void loop() {}
#else
int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_c_matches_python);
  return UNITY_END();
}
#endif
