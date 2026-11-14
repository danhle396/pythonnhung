"""Lưu/nạp mô hình: đối tượng (scikit-learn, LightGBM, …) bằng joblib + file JSON đầu mục mô tả phiên bản.

<path>.joblib — đối tượng Python (chỉ nạp file do chính pipeline này sinh ra)
<path>.json   — model_ver, thời điểm, hash dữ liệu, phiên bản thư viện, meta (chỉ số test…)
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np


def library_versions() -> dict:
    out = {}
    for name in ("sklearn", "lightgbm", "statsmodels", "torch", "numpy", "pandas"):
        try:
            out[name] = __import__(name).__version__
        except Exception:
            pass
    return out


def dataset_hash(*arrays):
    h = hashlib.sha256()
    for a in arrays:
        a = np.ascontiguousarray(np.asarray(a, dtype=float))
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()[:16]


def save_model(obj, path, model_ver="v0", data_hash=None, meta=None) -> Path:
    path = Path(path).with_suffix("")
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(obj, path.with_suffix(".joblib"), compress=3)
    head = {"model_ver": model_ver, "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "data_hash": data_hash, "libraries": library_versions(), "object_file": path.name + ".joblib",
            "meta": meta or {}}
    out = path.with_suffix(".json")
    out.write_text(json.dumps(head, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return out


def load_model(path):
    path = Path(path).with_suffix(".json")
    head = json.loads(path.read_text(encoding="utf-8"))
    obj = joblib.load(path.parent / head["object_file"])
    return obj, head
