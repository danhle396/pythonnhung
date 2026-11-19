import numpy as np
import pandas as pd
import pytest

from aiot_ml import rain_ensemble as re_


def _js():
    """JSON giống Open-Meteo Ensemble khi gọi 3 mô hình một lúc (tên cột có hậu tố mô hình)."""
    t = ["2026-11-20T17:00", "2026-11-20T18:00"]
    h = {"time": t,
         "precipitation_ecmwf_ifs025_ensemble": [3.0, 0.0],
         "precipitation_member01_ecmwf_ifs025_ensemble": [2.5, 0.0],
         "precipitation_member02_ecmwf_ifs025_ensemble": [0.0, 0.0],
         "precipitation_member03_ecmwf_ifs025_ensemble": [0.2, None],
         "precipitation_ncep_gefs025": [1.0, 0.4],
         "precipitation_member01_ncep_gefs025": [0.0, 0.6],
         "precipitation_icon_seamless_eps": [0.3, 0.0],
         "precipitation_member01_icon_seamless_eps": [0.1, 0.0]}
    return {"hourly": h}


def test_parse_members_groups_columns_by_model():
    m = re_.parse_members(_js())
    assert set(m) == {"ecmwf", "gfs", "icon"}
    assert m["ecmwf"].shape == (2, 4) and m["gfs"].shape == (2, 2) and m["icon"].shape == (2, 2)
    assert m["ecmwf"].index[0] == pd.Timestamp("2026-11-20 17:00")


def test_features_are_member_fractions_and_skip_missing():
    m = re_.parse_members(_js())
    f = re_.features_at(m, pd.Timestamp("2026-11-20 17:00"))
    assert f["ecmwf_ge0.1"] == 0.75 and f["ecmwf_ge1"] == 0.5 and f["ecmwf_ge3"] == 0.25
    assert f["gfs_ge1"] == 0.5 and f["icon_ge0.25"] == 0.5
    f18 = re_.features_at(m, pd.Timestamp("2026-11-20 18:00"))
    assert f18["ecmwf_ge0.1"] == 0.0, "thành viên thiếu số liệu (None) bị bỏ, không tính là khô"
    assert re_.features_at(m, pd.Timestamp("2026-11-21 00:00")) is None


def test_default_prediction_pools_models_at_1mm():
    f = re_.features_at(re_.parse_members(_js()), pd.Timestamp("2026-11-20 17:00"))
    assert re_.predict_pct(f, re_.DEFAULT_CALIB) == pytest.approx(100 * (0.5 + 0.5 + 0.0) / 3)
    assert re_.predict_pct({}, re_.DEFAULT_CALIB) is None


@pytest.mark.parametrize("base,adj,expected", [(10, 0, 10), (10, 25, 20), (95, 10, 100), (5, -30, 0)])
def test_station_adjustment_is_bounded(base, adj, expected):
    assert re_.blend(base, adj) == expected
    assert re_.station_adjustment(1, None)[0] == 0 and re_.station_adjustment(1, 0)[0] == 0
    assert re_.station_adjustment(1, 2)[0] == 10 and re_.station_adjustment(3, 1)[0] == 5
    assert re_.station_adjustment(6, 3)[0] == 0


def _rows(n, rng):
    """Bài toán có đáp án: 'Google' = 100 × tỉ lệ thành viên GFS có mưa ≥ 0,5 mm."""
    rows = []
    for i in range(n):
        f = {re_.feature_name(m, thr): float(rng.random()) for m in re_.MODELS for thr in re_.THRESHOLDS}
        rows.append({"features": f, "google_pct": 100 * f["gfs_ge0.5"], "issued_at": f"2026-11-{1 + i // 24:02d}T{i % 24:02d}"})
    return rows


def test_fit_calibration_recovers_known_source_and_threshold(tmp_path):
    rows = _rows(80, np.random.default_rng(0))
    c = re_.fit_calibration(rows)
    assert c["threshold"] == 0.5
    assert c["weights"]["gfs"] > 0 and c["weights"]["ecmwf"] == 0 and c["weights"]["icon"] == 0
    assert c["metrics"]["train_all"]["MAE"] < 1e-6 and c["metrics"]["valid_recent"]["within10"] == 1.0
    assert c["metrics"]["valid_default"]["MAE"] > 10, "cấu hình mặc định không biết nguồn đúng"
    re_.save_calibration(c, tmp_path / "c.json")
    back = re_.load_calibration(tmp_path / "c.json")
    assert re_.predict_pct(rows[0]["features"], back) == pytest.approx(rows[0]["google_pct"])
    assert re_.load_calibration(tmp_path / "missing.json")["version"] == "ens-default"


def test_fit_calibration_needs_enough_rows():
    with pytest.raises(ValueError):
        re_.fit_calibration(_rows(re_.MIN_FIT_ROWS - 1, np.random.default_rng(1)))


def test_isotonic_mapping_is_used_when_relationship_is_nonlinear():
    rng = np.random.default_rng(2)
    rows = _rows(120, rng)
    for r in rows:  # Google "nén" xác suất về giữa: 20 + 0.5·p
        r["google_pct"] = 20 + 0.5 * 100 * r["features"]["icon_ge1"]
    c = re_.fit_calibration(rows)
    assert c["metrics"]["use_isotonic"] is True and c["isotonic"]
    assert c["metrics"]["valid_recent"]["MAE"] < 3
