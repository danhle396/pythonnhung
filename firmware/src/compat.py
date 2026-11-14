import time

try:
    ticks_ms = time.ticks_ms
    ticks_us = time.ticks_us
    ticks_diff = time.ticks_diff
    ticks_add = time.ticks_add
    sleep_ms = time.sleep_ms
    MICROPYTHON = True
except AttributeError:
    MICROPYTHON = False
    _T0 = time.monotonic()

    def ticks_ms():
        return int((time.monotonic() - _T0) * 1000)

    def ticks_us():
        return int((time.monotonic() - _T0) * 1000000)

    def ticks_diff(a, b):
        return a - b

    def ticks_add(a, b):
        return a + b

    def sleep_ms(ms):
        time.sleep(ms / 1000)

try:
    from _thread import allocate_lock
except ImportError:
    class allocate_lock:
        def acquire(self, *a):
            return True

        def release(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

EPOCH_OFFSET = 946684800 if time.gmtime(0)[0] == 2000 else 0
VALID_EPOCH = 1700000000


def epoch():
    return int(time.time()) + EPOCH_OFFSET


def has_time():
    return epoch() > VALID_EPOCH


def local_tm(ts=None, tz_h=7):
    t = epoch() if ts is None else ts
    return time.gmtime(t - EPOCH_OFFSET + tz_h * 3600)


def isnan(v):
    return v is None or v != v


def nan():
    return float("nan")
