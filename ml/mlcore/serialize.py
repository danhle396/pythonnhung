"""Lưu / tải model.

- Cây, rừng, GBDT, scaler... -> JSON (đọc được bằng mắt, dễ kiểm tra, dễ xuất sang C).
- Mạng nơ-ron -> .npz (trọng số nhị phân) + JSON header.
Mọi file có header: model_ver, created_at, data_hash (SHA-256 dữ liệu huấn luyện), mlcore_version, meta.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from pathlib import Path

import numpy as np

from . import __version__
from .anomaly import CUSUM, HourlyZScore, IsolationForest
from .ensemble import (GradientBoostingClassifier, GradientBoostingRegressor, RandomForestClassifier,
                       RandomForestRegressor)
from .linear import LinearRegression, LogisticRegression, Ridge
from .nn import MLP, GRURegressor
from .preprocessing import MinMaxScaler, StandardScaler
from .smoothing import HoltWinters
from .tree import DecisionTreeClassifier, DecisionTreeRegressor

REGISTRY = {c.__name__: c for c in [
    StandardScaler, MinMaxScaler, LinearRegression, Ridge, LogisticRegression, HoltWinters,
    DecisionTreeRegressor, DecisionTreeClassifier, RandomForestClassifier, RandomForestRegressor,
    GradientBoostingRegressor, GradientBoostingClassifier, IsolationForest, CUSUM, HourlyZScore,
    MLP, GRURegressor]}

NPZ_TYPES = {"MLP", "GRURegressor"}


def obj_from_dict(d):
    """Khôi phục đối tượng từ dict có khoá 'type'. Dict lồng nhau (bundle) được khôi phục đệ quy."""
    if isinstance(d, dict) and d.get("type") in REGISTRY:
        return REGISTRY[d["type"]].from_dict(d)
    if isinstance(d, dict):
        return {k: obj_from_dict(v) for k, v in d.items()}
    if isinstance(d, list):
        return [obj_from_dict(v) for v in d]
    return d


def obj_to_dict(o):
    if hasattr(o, "to_dict"):
        return o.to_dict()
    if isinstance(o, dict):
        return {k: obj_to_dict(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [obj_to_dict(v) for v in o]
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    return o


def dataset_hash(*arrays):
    h = hashlib.sha256()
    for a in arrays:
        a = np.ascontiguousarray(np.asarray(a, dtype=float))
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()[:16]


def _header(model_ver, data_hash, meta):
    return {"model_ver": model_ver, "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "data_hash": data_hash, "mlcore_version": __version__, "meta": meta or {}}


def save_model(obj, path, model_ver="v0", data_hash=None, meta=None):
    """Lưu model hoặc bundle (dict chứa nhiều đối tượng). Trả về đường dẫn file chính."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    head = _header(model_ver, data_hash, meta)
    if getattr(obj, "to_dict", None) and obj.to_dict().get("type") in NPZ_TYPES:
        d = obj.to_dict()
        params = d.pop("params")
        npz = path.with_suffix(".npz")
        np.savez_compressed(npz, **{k: np.asarray(v) for k, v in params.items()})
        head["model"] = d
        head["weights_file"] = npz.name
        out = path.with_suffix(".json")
    else:
        head["model"] = obj_to_dict(obj)
        out = path.with_suffix(".json")
    out.write_text(json.dumps(head, ensure_ascii=False), encoding="utf-8")
    return out


def load_model(path):
    """Trả về (obj, header)."""
    path = Path(path).with_suffix(".json")
    head = json.loads(path.read_text(encoding="utf-8"))
    d = head["model"]
    if "weights_file" in head:
        w = np.load(path.parent / head["weights_file"])
        d = dict(d)
        d["params"] = {k: w[k] for k in w.files}
    return obj_from_dict(d), head
