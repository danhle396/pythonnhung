import gc
import time

from edge_gas import EdgeGas

gc.collect()
free0 = gc.mem_free()
e = EdgeGas(warmup_samples=0)
N = 200
t0 = time.ticks_us()
for i in range(N):
    e.step(100.0 + (i % 50), 28.0, True)
dt_step = time.ticks_diff(time.ticks_us(), t0) / N
gc.collect()
print("edge step: %.0f us/lan (do doc ppm + luat 4 cap)" % dt_step)
print("RAM trong: %d B (EdgeGas dung ~%d B)" % (gc.mem_free(), free0 - gc.mem_free()))
