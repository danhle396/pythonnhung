"""Chạy logic firmware MicroPython trên CPython: thêm firmware/src vào sys.path."""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
