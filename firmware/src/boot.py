# Chạy trước main.py mỗi lần khởi động. Giữ tối thiểu: thu gom rác, tắt log debug của ESP-IDF.
import gc

try:
    import esp
    esp.osdebug(None)
except ImportError:
    pass
gc.collect()
