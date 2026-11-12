"""Module MicroPython sinh từ cây/rừng (mlcore.export_micropython) khớp 100 % với mlcore, và biên dịch được bằng
mpy-cross cho ESP32."""
import subprocess
import sys

import numpy as np
import pytest

from mlcore import ensemble, tree
from mlcore.export_micropython import (export_forest_micropython, load_module_from_source, predict_float32,
                                       to_float32_list)


def _data():
    rng = np.random.default_rng(3)
    X = rng.normal(size=(800, 10)).astype(np.float32).astype(float)
    y = (X[:, 0] > 0.3).astype(int) + (X[:, 1] + X[:, 2] > 1).astype(int) + (X[:, 3] > 1.5).astype(int)
    return X, y


@pytest.mark.parametrize("kind", ["tree", "forest"])
def test_micropython_module_matches_mlcore(tmp_path, kind):
    X, y = _data()
    if kind == "tree":
        m = tree.DecisionTreeClassifier(max_depth=6, class_weight="balanced").fit(X, y)
    else:
        m = ensemble.RandomForestClassifier(n_estimators=7, max_depth=5).fit(X, y)
    cls_idx, proba = predict_float32(m, X)
    # mô phỏng float32 phải trùng dự đoán gốc (ngưỡng là trung điểm nên không có ca biên)
    assert (m.classes_[cls_idx] == m.predict(X)).mean() == 1.0
    src = export_forest_micropython(m, [f"f{i}" for i in range(10)], model_ver="test")
    mod = load_module_from_source(src)
    assert mod.AVAILABLE and mod.N_FEATURES == 10 and mod.VERSION == "test"
    bad, maxdiff = 0, 0.0
    for i in range(len(X)):
        k, p = mod.predict_proba(to_float32_list(X[i]))
        bad += k != cls_idx[i]
        maxdiff = max(maxdiff, max(abs(a - b) for a, b in zip(p, proba[i])))
    assert bad == 0, "module MicroPython và mlcore dự đoán lệch lớp"
    assert maxdiff < 1e-5
    # cú pháp hợp lệ với MicroPython (mpy-cross)
    if pytest.importorskip("mpy_cross"):
        f = tmp_path / "gas_model.py"
        f.write_text(src, encoding="utf-8")
        r = subprocess.run([sys.executable, "-m", "mpy_cross", "-march=xtensawin", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
