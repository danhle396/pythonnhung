"""Kiểm tra predict() bằng C (biên dịch bằng g++/gcc trên PC) khớp 100% với Python."""
import shutil
import subprocess

import numpy as np
import pytest

from mlcore import ensemble, tree
from mlcore.export_c import export_forest_c, export_test_vectors_c, predict_c_like

CXX = shutil.which("g++") or shutil.which("gcc") or shutil.which("clang")

HARNESS = r"""
#include <stdio.h>
#include <math.h>
#include "model.h"
#include "testvec.h"
int main(void) {
    int bad = 0; float maxdiff = 0.0f;
    for (int i = 0; i < M_N_TEST; ++i) {
        float p[M_N_CLASSES];
        int c = m_predict_proba(m_test_x[i], p);
        if (c != m_test_class_idx[i]) ++bad;
        for (int k = 0; k < M_N_CLASSES; ++k) {
            float d = fabsf(p[k] - m_test_proba[i][k]);
            if (d > maxdiff) maxdiff = d;
        }
    }
    printf("%d %g\n", bad, maxdiff);
    return 0;
}
"""


def _data():
    rng = np.random.default_rng(3)
    X = rng.normal(size=(800, 5)).astype(np.float32).astype(float)
    y = (X[:, 0] > 0.3).astype(int) + (X[:, 1] + X[:, 2] > 1).astype(int) + (X[:, 3] > 1.5).astype(int)
    return X, y


@pytest.mark.parametrize("kind", ["tree", "forest"])
def test_c_matches_python(tmp_path, kind):
    if CXX is None:
        pytest.skip("không có trình biên dịch C")
    X, y = _data()
    if kind == "tree":
        m = tree.DecisionTreeClassifier(max_depth=6, class_weight="balanced").fit(X, y)
    else:
        m = ensemble.RandomForestClassifier(n_estimators=7, max_depth=5).fit(X, y)
    cls_idx, proba = predict_c_like(m, X)
    # mô phỏng float32 phải trùng dự đoán gốc (ngưỡng là trung điểm nên không có ca biên)
    assert (m.classes_[cls_idx] == m.predict(X)).mean() == 1.0
    (tmp_path / "model.h").write_text(export_forest_c(m, [f"f{i}" for i in range(5)], prefix="m"), encoding="utf-8")
    (tmp_path / "testvec.h").write_text(export_test_vectors_c(X, cls_idx, proba, prefix="m", n_max=800), encoding="utf-8")
    (tmp_path / "main.c").write_text(HARNESS, encoding="utf-8")
    exe = tmp_path / "t.exe"
    subprocess.run([CXX, "-O2", "-x", "c++", str(tmp_path / "main.c"), "-o", str(exe)], check=True,
                   cwd=tmp_path)
    out = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout.split()
    assert int(out[0]) == 0, "C và Python dự đoán lệch lớp"
    assert float(out[1]) < 1e-6
