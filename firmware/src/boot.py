import gc

try:
    import esp
    esp.osdebug(None)
except ImportError:
    pass
gc.collect()
