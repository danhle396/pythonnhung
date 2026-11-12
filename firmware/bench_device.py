# Đo tài nguyên Edge AI NGAY TRÊN ESP32 (chạy bằng: python -m mpremote connect COM5 run firmware/bench_device.py).
# Cần đã nạp firmware (deploy.py) để import được các module. In ra: thời gian 1 bước edge (feature + rule [+ model]),
# thời gian suy luận gas_model (nếu có), RAM trống. Số liệu này dùng cho mục "Tài nguyên edge" của báo cáo.
import gc
import time

import gas_model
from edge_ai import MODE_HYBRID, EdgeAI

gc.collect()
free0 = gc.mem_free()
e = EdgeAI(mode=MODE_HYBRID, warmup_samples=0)
N = 200
# chuỗi ppm đầu vào cố định (chỉ để đo thời gian tính toán, không phải dữ liệu đo)
t0 = time.ticks_us()
for i in range(N):
    e.step(100.0 + (i % 50), 2.0, 28.0, 75.0, 300.0, True)
dt_step = time.ticks_diff(time.ticks_us(), t0) / N
gc.collect()
print("edge step: %.0f us/lan (feature 10 chieu + rule%s)" % (dt_step, " + model" if gas_model.AVAILABLE else ""))
if gas_model.AVAILABLE:
    x = list(e.fx.f)
    t0 = time.ticks_us()
    for _ in range(N):
        gas_model.predict_proba(x)
    print("gas_model %s: %.0f us/lan suy luan" % (gas_model.VERSION, time.ticks_diff(time.ticks_us(), t0) / N))
else:
    print("gas_model: chua co (AVAILABLE = False) -> edge chay rule")
print("RAM trong: %d B (EdgeAI dung ~%d B)" % (gc.mem_free(), free0 - gc.mem_free()))
