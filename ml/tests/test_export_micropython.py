import subprocess
import sys

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier

from aiot_ml.export_micropython import (export_forest_micropython, load_module_from_source, predict_float32,
                                        to_float32_list)


def _data():
    rng = np.random.default_rng(3)
    X = rng.normal(size=(800, 10)).astype(np.float32).astype(float)
    y = (X[:, 0] > 0.3).astype(int) + (X[:, 1] + X[:, 2] > 1).astype(int) + (X[:, 3] > 1.5).astype(int)
    return X, y


@pytest.mark.parametrize("kind", ["tree", "forest"])
def test_micropython_module_matches_sklearn(tmp_path, kind):
    X, y = _data()
    if kind == "tree":
        m = DecisionTreeClassifier(max_depth=6, class_weight="balanced", random_state=0).fit(X, y)
    else:
        m = RandomForestClassifier(n_estimators=7, max_depth=5, random_state=0).fit(X, y)
    cls_idx, proba = predict_float32(m, X)
    np.testing.assert_allclose(proba, m.predict_proba(X), atol=1e-5)
    assert (m.classes_[cls_idx] == m.predict(X)).mean() == 1.0
    src = export_forest_micropython(m, [f"f{i}" for i in range(10)], model_ver="test")
    mod = load_module_from_source(src)
    assert mod.AVAILABLE and mod.N_FEATURES == 10 and mod.VERSION == "test"
    bad, maxdiff = 0, 0.0
    for i in range(len(X)):
        k, p = mod.predict_proba(to_float32_list(X[i]))
        bad += k != cls_idx[i]
        maxdiff = max(maxdiff, max(abs(a - b) for a, b in zip(p, proba[i])))
    assert bad == 0, "module MicroPython và scikit-learn dự đoán lệch lớp"
    assert maxdiff < 1e-5
    if pytest.importorskip("mpy_cross"):
        f = tmp_path / "gas_model.py"
        f.write_text(src, encoding="utf-8")
        r = subprocess.run([sys.executable, "-m", "mpy_cross", "-march=xtensawin", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
