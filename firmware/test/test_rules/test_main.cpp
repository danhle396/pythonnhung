// Unit test (Unity) cho logic thuần C++: bộ lọc, rule engine (hysteresis/debounce), alert manager, nowcast.
//   pio test -e native -f test_rules
#include <unity.h>
#include <initializer_list>

#include "alert.h"
#include "edge_ai.h"
#include "filters.h"
#include "nowcast.h"

void setUp() {}
void tearDown() {}

static void test_median_removes_spike() {
  Median5 m;
  float out = 0;
  for (float v : {10.f, 10.f, 500.f, 10.f, 10.f}) out = m.update(v);
  TEST_ASSERT_EQUAL_FLOAT(10.f, out);
}

static void test_ewma_and_ring_slope() {
  Ewma e(0.5f);
  e.update(0);
  TEST_ASSERT_EQUAL_FLOAT(5.f, e.update(10));
  RingBuffer<10> r;
  for (int i = 0; i < 15; ++i) r.push(3.0f * i + 1);
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 3.0f, r.slope());
  TEST_ASSERT_EQUAL_UINT32(10, r.size());
  TEST_ASSERT_EQUAL_FLOAT(43.f, r.last());
}

static void test_rule_debounce_and_immediate_danger() {
  RuleEngine r;
  TEST_ASSERT_EQUAL(0, r.update(1200, 0, 0));
  TEST_ASSERT_EQUAL(0, r.update(1200, 0, 0));
  TEST_ASSERT_EQUAL(2, r.update(1200, 0, 0));
  RuleEngine r2;
  TEST_ASSERT_EQUAL(3, r2.update(2500, 0, 0));
}

static void test_rule_hysteresis() {
  RuleConfig c;
  c.debounceUp = 1;
  c.debounceDown = 3;
  RuleEngine r(c);
  TEST_ASSERT_EQUAL(2, r.update(1100, 0, 0));
  for (int i = 0; i < 5; ++i) TEST_ASSERT_EQUAL(2, r.update(950, 0, 0));  // > 850 -> giữ
  TEST_ASSERT_EQUAL(2, r.update(800, 0, 0));
  TEST_ASSERT_EQUAL(2, r.update(800, 0, 0));
  TEST_ASSERT_EQUAL(1, r.update(800, 0, 0));
}

static void test_rule_spike_rejected_and_temp_escalation() {
  RuleEngine r;
  float seq[] = {10, 10, 1500, 10, 10, 1500, 10};
  int mx = 0;
  for (float p : seq) { int l = r.update(p, 0, 0); if (l > mx) mx = l; }
  TEST_ASSERT_EQUAL(0, mx);
  RuleConfig c;
  c.debounceUp = 1;
  RuleEngine r2(c);
  TEST_ASSERT_EQUAL(2, r2.update(1200, 0, 0.2f));
  TEST_ASSERT_EQUAL(3, r2.update(1200, 0, 1.5f));
}

static void test_alert_mute_and_reescalate() {
  AlertManager a(300000);
  Actions x = a.update(2, 1000);
  TEST_ASSERT_TRUE(x.levelChanged);
  TEST_ASSERT_EQUAL((int)BuzzerMode::INTERMITTENT, (int)x.buzzer);
  a.pressMute(1100);
  x = a.update(2, 1200);
  TEST_ASSERT_EQUAL((int)BuzzerMode::OFF, (int)x.buzzer);
  TEST_ASSERT_EQUAL((int)LedMode::RED_BLINK, (int)x.led);  // vẫn giữ LED
  x = a.update(3, 1300);                                     // cấp tăng -> còi kêu lại
  TEST_ASSERT_EQUAL((int)BuzzerMode::CONTINUOUS, (int)x.buzzer);
  AlertManager b(1000);
  b.update(2, 0);
  b.pressMute(0);
  TEST_ASSERT_EQUAL((int)BuzzerMode::OFF, (int)b.update(2, 500).buzzer);
  TEST_ASSERT_EQUAL((int)BuzzerMode::INTERMITTENT, (int)b.update(2, 1500).buzzer);  // hết hạn mute
}

static void test_cloud_escalation_never_lowers() {
  AlertManager a;
  a.cloudEscalate(1, 0);
  TEST_ASSERT_EQUAL(3, a.update(3, 10).level);
  a.cloudEscalate(3, 20);
  TEST_ASSERT_EQUAL(3, a.update(0, 30).level);
}

static void test_mq2_conversion_and_fault() {
  Mq2Params p;
  // Rs/R0 = 1 => ppm = A
  float rs = p.r0Kohm;
  float v = p.vc * p.rlKohm / (rs + p.rlKohm);
  Mq2Reading r = mq2Convert(v * p.divider * 1000.0f, p);
  TEST_ASSERT_FLOAT_WITHIN(1e-3, 1.0f, r.ratio);
  TEST_ASSERT_FLOAT_WITHIN(0.5f, p.curveA, r.ppm);
  Mq2FaultDetector f;
  for (int i = 0; i < 5; ++i) f.update(0.0f);
  TEST_ASSERT_EQUAL((int)SensorFault::DISCONNECTED, (int)f.fault());
  for (int i = 0; i < 5; ++i) f.update(3300.0f);
  TEST_ASSERT_EQUAL((int)SensorFault::SATURATED, (int)f.fault());
}

static void test_edge_hybrid_never_below_rule() {
  EdgeAI e;
  e.warmupSamples = 0;
  e.rules.cfg.debounceUp = 1;
  EdgeOutput o;
  for (int i = 0; i < 5; ++i) o = e.step({2500.f, 0.5f, 28.f, 70.f, 100.f, true});
  TEST_ASSERT_EQUAL(3, o.ruleLevel);
  TEST_ASSERT_TRUE(o.level >= o.ruleLevel);
}

static void test_nowcast_trends() {
  NowcastEngine n;
  for (int i = 0; i < 19; ++i) n.addPressure(1012.0f - 0.15f * i);  // giảm 2.7 hPa / 3h
  Nowcast c = n.compute(0, 80.0f, 11);
  TEST_ASSERT_EQUAL((int)PressureTrend::Falling, (int)c.trend);
  TEST_ASSERT_TRUE(c.code == NowcastCode::RAIN_SOON || c.code == NowcastCode::POSSIBLE_RAIN);
  NowcastEngine s;
  for (int i = 0; i < 19; ++i) s.addPressure(1022.0f);
  TEST_ASSERT_EQUAL((int)NowcastCode::FINE, (int)s.compute(0, 60.0f, 3).code);
  TEST_ASSERT_EQUAL((int)NowcastCode::RAINING, (int)s.compute(2, 60.0f, 3).code);
}

// Thử còi: cấp 3 trong 3 s, đánh dấu testing (để gửi type "test", không phải sự cố khí / cloud nâng cấp)
static void test_alarm_test_is_flagged() {
  AlertManager m;
  m.testAlarm(1000);
  Actions a = m.update(0, 1000);
  TEST_ASSERT_EQUAL(3, a.level);
  TEST_ASSERT_TRUE(a.testing);
  a = m.update(0, 4500);
  TEST_ASSERT_EQUAL(0, a.level);
  TEST_ASSERT_FALSE(a.testing);
  m.cloudEscalate(2, 5000);
  a = m.update(0, 5000);
  TEST_ASSERT_EQUAL(2, a.level);
  TEST_ASSERT_FALSE(a.testing);
}

// Board khởi động lại: mẫu đã lưu (có giờ) được nạp lại -> không phải chờ lại 1 giờ; quãng tắt máy tính đúng.
static void test_nowcast_restore_after_reboot() {
  const uint32_t T0 = 1794470000;
  NowcastEngine a;
  for (int i = 0; i < 6; ++i) a.addPressure(1012.0f - 0.2f * i, T0 + i * 600);  // 50 phút, giảm
  TEST_ASSERT_EQUAL((int)PressureTrend::Unknown, (int)a.compute(0, 80.0f, 11).trend);  // < 1 giờ
  float p[NowcastEngine::N];
  uint32_t t[NowcastEngine::N];
  size_t n = a.exportSamples(p, t);
  TEST_ASSERT_EQUAL(6, (int)n);

  // khởi động lại sau 15 phút tắt máy; mẫu đầu tiên lấy trước khi có NTP (ts = 0)
  NowcastEngine b;
  b.addPressure(1010.6f, 0);
  const uint32_t now = T0 + 5 * 600 + 15 * 60 + 60;  // NTP về 1 phút sau mẫu đầu
  b.assignTimes(now - 60);
  b.restore(p, t, n, now);
  TEST_ASSERT_EQUAL(7, (int)b.samples());
  TEST_ASSERT_TRUE(b.timed());
  TEST_ASSERT_FLOAT_WITHIN(0.01f, (5 * 600 + 15 * 60) / 3600.0f, b.spanHours());  // 65 phút thật, không phải 60
  Nowcast c = b.compute(0, 80.0f, 11);
  TEST_ASSERT_EQUAL((int)PressureTrend::Falling, (int)c.trend);  // giảm 1.4 hPa / 65 phút -> ≈ -3.9 hPa/3h
  TEST_ASSERT_FLOAT_WITHIN(0.05f, -1.4f * 3.0f / b.spanHours(), c.trend3h);

  // mẫu đã lưu quá 3 giờ bị bỏ
  NowcastEngine old;
  old.restore(p, t, n, T0 + 5 * 3600);
  TEST_ASSERT_EQUAL(0, (int)old.samples());
}

static void test_derived_quantities() {
  TEST_ASSERT_FLOAT_WITHIN(0.05f, 25.0f, dewPoint(25.0f, 100.0f));
  float p0 = seaLevelPressure(1009.0f, 28.0f, 8.0f);
  TEST_ASSERT_TRUE(p0 > 1009.8f && p0 < 1010.1f);
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_median_removes_spike);
  RUN_TEST(test_ewma_and_ring_slope);
  RUN_TEST(test_rule_debounce_and_immediate_danger);
  RUN_TEST(test_rule_hysteresis);
  RUN_TEST(test_rule_spike_rejected_and_temp_escalation);
  RUN_TEST(test_alert_mute_and_reescalate);
  RUN_TEST(test_cloud_escalation_never_lowers);
  RUN_TEST(test_mq2_conversion_and_fault);
  RUN_TEST(test_edge_hybrid_never_below_rule);
  RUN_TEST(test_nowcast_trends);
  RUN_TEST(test_nowcast_restore_after_reboot);
  RUN_TEST(test_alarm_test_is_flagged);
  RUN_TEST(test_derived_quantities);
  return UNITY_END();
}
