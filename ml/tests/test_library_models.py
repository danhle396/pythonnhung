import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.linear_model import Ridge

from aiot_ml import prep
from aiot_ml.serialize import load_model, save_model
from aiot_ml.train_forecast import best_f1_threshold, holt_winters_rolling


def test_save_load_roundtrip_keeps_predictions(tmp_path):
    rng = np.random.default_rng(0)
    X = rng.normal(size=(300, 5))
    y = X[:, 0] * 2 - X[:, 1] + rng.normal(0, 0.1, 300)
    for model in (LGBMRegressor(n_estimators=20, verbose=-1, random_state=0), Ridge(alpha=1.0)):
        model.fit(X, y)
        path = save_model({"model": model, "features": list("abcde")}, tmp_path / type(model).__name__,
                          model_ver="t1", data_hash="x", meta={"MAE": 0.1})
        obj, head = load_model(path)
        assert head["model_ver"] == "t1" and "sklearn" in head["libraries"]
        np.testing.assert_allclose(obj["model"].predict(X), model.predict(X))


def test_holt_winters_rolling_matches_statsmodels_and_beats_naive():
    idx = pd.date_range("2024-01-01", periods=24 * 60, freq="1h")
    rng = np.random.default_rng(1)
    y = pd.Series(27 + 3 * np.sin(2 * np.pi * idx.hour / 24) + np.cumsum(rng.normal(0, 0.05, len(idx))), index=idx)
    fc, params = holt_winters_rolling(y, idx[24 * 40], 24 * 30, 24, 3)  # tự assert khớp statsmodels.forecast()
    true = y.shift(-3)
    test = idx[24 * 41:-3]
    mae_hw = np.mean(np.abs(fc.loc[test] - true.loc[test]))
    mae_pers = np.mean(np.abs(y.loc[test] - true.loc[test]))
    assert mae_hw < mae_pers
    assert 0 <= params["smoothing_level"] <= 1


def test_best_f1_threshold_prefers_separating_cut():
    y = np.array([0] * 50 + [1] * 50)
    p = np.r_[np.linspace(0.0, 0.4, 50), np.linspace(0.6, 1.0, 50)]
    thr, f1 = best_f1_threshold(y, p)
    assert 0.4 < thr <= 0.6 and f1 == 1.0


def test_prep_helpers():
    x = np.array([1.0, np.nan, 3.0, np.nan, np.nan, np.nan, np.nan, 8.0])
    out = prep.interpolate_gaps(x, max_gap=3)
    assert out[1] == 2.0 and np.isnan(out[3:7]).all()
    r = prep.rolling_stat(np.arange(6.0), 3, "mean")
    assert np.isnan(r[:2]).all() and r[2] == 1.0 and r[5] == 4.0
    assert prep.linear_slope([1, 3, 5, 7]) == 2.0
