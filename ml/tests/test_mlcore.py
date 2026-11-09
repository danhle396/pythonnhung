"""Unit test cho mlcore: dữ liệu đồ chơi có đáp án biết trước, gradient check, round-trip serialize."""
import numpy as np
import pytest

from mlcore import anomaly, ensemble, explain, linear, metrics, model_selection, nn, preprocessing, smoothing, tree
from mlcore.serialize import dataset_hash, load_model, obj_from_dict, save_model


# ------------------------------------------------------------ preprocessing
def test_standard_scaler_roundtrip():
    X = np.random.default_rng(0).normal(5, 3, (200, 3))
    s = preprocessing.StandardScaler().fit(X)
    Z = s.transform(X)
    assert np.allclose(Z.mean(axis=0), 0, atol=1e-12)
    assert np.allclose(Z.std(axis=0), 1, atol=1e-12)
    assert np.allclose(s.inverse_transform(Z), X)
    s2 = preprocessing.StandardScaler.from_dict(s.to_dict())
    assert np.allclose(s2.transform(X), Z)


def test_minmax_constant_column():
    X = np.column_stack([np.arange(10.0), np.ones(10)])
    Z = preprocessing.MinMaxScaler().fit_transform(X)
    assert Z[:, 0].min() == 0 and Z[:, 0].max() == 1
    assert np.all(np.isfinite(Z[:, 1]))


def test_interpolate_gaps_respects_max_gap():
    x = np.array([1, np.nan, 3, np.nan, np.nan, np.nan, 7, np.nan], dtype=float)
    y = preprocessing.interpolate_gaps(x, max_gap=2)
    assert y[1] == 2
    assert np.isnan(y[3:6]).all()      # khoảng trống dài 3 > 2 -> giữ NaN
    assert np.isnan(y[7])              # không ngoại suy ở cuối
    assert np.allclose(preprocessing.interpolate_gaps(x)[3:6], [4, 5, 6])


def test_outliers_and_cyclic():
    x = np.r_[np.random.default_rng(1).normal(0, 1, 500), 50.0]
    assert preprocessing.iqr_outlier_mask(x)[-1]
    assert preprocessing.zscore_outlier_mask(x, 4)[-1]
    s, c = preprocessing.cyclic_encode([0, 6, 12, 23.999], 24)
    assert np.allclose([s[0], c[0]], [0, 1]) and np.allclose([s[1], c[1]], [1, 0], atol=1e-12)
    assert np.allclose(c[3], 1, atol=1e-6)


def test_lag_rolling_slope():
    x = np.arange(10.0)
    L = preprocessing.lag_matrix(x, [1, 3])
    assert np.isnan(L[0, 0]) and L[5, 0] == 4 and L[5, 1] == 2
    r = preprocessing.rolling_stat(x, 3, "mean")
    assert np.isnan(r[1]) and r[2] == 1
    assert np.isclose(preprocessing.linear_slope(3 * x + 1, dt=2.0), 1.5)


# ------------------------------------------------------------ metrics (đối chiếu tính tay)
def test_regression_metrics_by_hand():
    y, p = [1, 2, 3, 4], [1, 3, 2, 4]
    assert metrics.mae(y, p) == 0.5
    assert np.isclose(metrics.rmse(y, p), np.sqrt(0.5))
    assert np.isclose(metrics.mape(y, p), 100 * (0 + 0.5 + 1 / 3 + 0) / 4)
    assert np.isclose(metrics.r2(y, p), 1 - 2 / 5)


def test_classification_metrics_by_hand():
    y = [0, 0, 1, 1, 1, 2]
    p = [0, 1, 1, 1, 0, 2]
    cm = metrics.confusion_matrix(y, p, labels=[0, 1, 2])
    assert cm.tolist() == [[1, 1, 0], [1, 2, 0], [0, 0, 1]]
    r = metrics.precision_recall_f1(y, p, labels=[0, 1, 2])
    assert np.isclose(r["per_class"][1]["precision"], 2 / 3)
    assert np.isclose(r["per_class"][1]["recall"], 2 / 3)
    assert np.isclose(r["per_class"][0]["f1"], 0.5)


def test_auc_by_hand_with_ties():
    # cặp (dương, âm): (0.8,0.1)=1 (0.8,0.4)=1 (0.4,0.1)=1 (0.4,0.4)=0.5 => 3.5/4
    assert np.isclose(metrics.roc_auc([1, 1, 0, 0], [0.8, 0.4, 0.4, 0.1]), 0.875)
    assert metrics.roc_auc([0, 1], [0.1, 0.9]) == 1.0
    assert np.isclose(metrics.brier_score([1, 0], [0.8, 0.4]), (0.04 + 0.16) / 2)


# ------------------------------------------------------------ model selection
def test_time_split_and_tscv_no_leakage():
    tr, va, te = model_selection.time_train_val_test_split(100, 0.2, 0.2, gap=2)
    assert tr.max() < va.min() < te.min() and va.min() - tr.max() > 2
    for a, b in model_selection.TimeSeriesSplit(n_splits=4, gap=1).split(np.zeros(50)):
        assert a.max() + 1 < b.min()
    assert len(model_selection.ParameterGrid({"a": [1, 2], "b": [3, 4, 5]})) == 6


def test_grid_search_picks_best_alpha():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(200, 5))
    y = X @ np.array([1, 0, 0, 2, 0]) + rng.normal(0, 0.1, 200)
    best, score, hist = model_selection.grid_search(
        lambda alpha: linear.Ridge(alpha=alpha), {"alpha": [0.01, 1000.0]}, X, y,
        model_selection.TimeSeriesSplit(3), lambda m, X_, y_: metrics.mse(y_, m.predict(X_)))
    assert best["alpha"] == 0.01 and len(hist) == 2


# ------------------------------------------------------------ linear
def test_linear_regression_y_3x_plus_2():
    x = np.linspace(-5, 5, 100).reshape(-1, 1)
    y = 3 * x.ravel() + 2
    m = linear.LinearRegression().fit(x, y)
    assert np.isclose(m.coef_[0], 3) and np.isclose(m.intercept_, 2)
    g = linear.LinearRegression(solver="gd", lr=0.05, epochs=5000).fit(x, y)
    assert abs(g.coef_[0] - 3) < 1e-3 and abs(g.intercept_ - 2) < 1e-3


def test_ridge_shrinks():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(50, 3))
    y = X @ np.array([2.0, -1.0, 0.5])
    w0 = np.abs(linear.Ridge(alpha=0.0).fit(X, y).coef_).sum()
    w1 = np.abs(linear.Ridge(alpha=100.0).fit(X, y).coef_).sum()
    assert w1 < w0


def test_logistic_separable_and_gradcheck():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(300, 2))
    y = (X[:, 0] + 2 * X[:, 1] > 0).astype(int)
    m = linear.LogisticRegression(epochs=300, lr=0.1).fit(X, y)
    assert metrics.accuracy(y, m.predict(X)) > 0.97
    # gradient check nhị phân và đa lớp
    for K in (2, 3):
        yy = rng.integers(0, K, 40)
        mm = linear.LogisticRegression(alpha=0.1)
        mm.classes_ = np.arange(K)
        Y = mm._encode(yy)
        out = 1 if K == 2 else K
        params = {"W": rng.normal(size=(2, out)), "b": rng.normal(size=out)}
        err = nn.gradient_check(mm.loss_and_grad, params, X[:40], Y, rng.uniform(0.5, 2, 40))
        assert err < 1e-5, err


# ------------------------------------------------------------ Holt-Winters
def test_holt_winters_recovers_season():
    t = np.arange(24 * 20)
    y = 25 + 3 * np.sin(2 * np.pi * t / 24) + 0.001 * t
    hw = smoothing.HoltWinters(24).fit(y[:-24])
    f = hw.forecast(24)
    assert metrics.mae(y[-24:], f) < 0.2


# ------------------------------------------------------------ trees
def test_tree_xor_depth2_perfect():
    X = np.array([[0, 0], [0, 1], [1, 0], [1, 1]] * 25, dtype=float)
    y = np.array([0, 1, 1, 0] * 25)
    # Gini của lần chia đầu tiên trên XOR bằng 0 -> min_gain âm để vẫn chia được (như CART chuẩn)
    m = tree.DecisionTreeClassifier(max_depth=2)
    m.fit(X, y)
    if metrics.accuracy(y, m.predict(X)) < 1.0:  # trường hợp gain = 0 ở gốc
        Xb = tree.Binner(8).fit(X)
        t = tree.build_class_tree(Xb.transform(X), Xb.edges_, y, 2, max_depth=2, min_gain=-1.0)
        m.tree_ = t
    assert metrics.accuracy(y, m.predict(X)) == 1.0
    assert m.tree_.max_depth == 2


def test_tree_regression_step_function():
    x = np.linspace(0, 10, 400).reshape(-1, 1)
    y = np.where(x.ravel() < 3, 1.0, np.where(x.ravel() < 7, 5.0, -2.0))
    m = tree.DecisionTreeRegressor(max_depth=3, min_samples_leaf=1, max_bins=512).fit(x, y)
    assert metrics.mae(y, m.predict(x)) < 1e-9


def test_class_weight_increases_recall_of_rare_class():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(2000, 2))
    y = ((X[:, 0] > 1.2) & (rng.random(2000) < 0.7)).astype(int)
    r0 = metrics.recall_binary(y, tree.DecisionTreeClassifier(max_depth=2).fit(X, y).predict(X))
    r1 = metrics.recall_binary(y, tree.DecisionTreeClassifier(max_depth=2, class_weight={1: 10.0}).fit(X, y).predict(X))
    assert r1 >= r0 and r1 > 0.9


def test_entropy_criterion_and_binner():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(500, 3))
    y = (X[:, 2] > 0).astype(int)
    m = tree.DecisionTreeClassifier(max_depth=1, criterion="entropy").fit(X, y)
    assert m.tree_.feature[0] == 2 and metrics.accuracy(y, m.predict(X)) > 0.98
    b = tree.Binner(16).fit(X)
    assert all(len(e) <= 15 for e in b.edges_)
    Xb = b.transform(X)
    for j in range(3):  # bin(x) <= b  <=>  x <= edge_b
        assert np.all((Xb[:, j] <= 5) == (X[:, j] <= b.edges_[j][5]))


# ------------------------------------------------------------ ensembles
def test_random_forest_and_roundtrip():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(600, 4))
    y = (X[:, 0] * X[:, 1] > 0).astype(int)
    m = ensemble.RandomForestClassifier(n_estimators=10, max_depth=6, max_features=2).fit(X, y)
    assert metrics.accuracy(y, m.predict(X)) > 0.9
    m2 = obj_from_dict(m.to_dict())
    assert np.allclose(m.predict_proba(X), m2.predict_proba(X))
    rr = ensemble.RandomForestRegressor(n_estimators=10).fit(X, X[:, 0] ** 2)
    assert metrics.r2(X[:, 0] ** 2, rr.predict(X)) > 0.8


def test_gbdt_regression_beats_mean_and_early_stops():
    rng = np.random.default_rng(0)
    X = rng.uniform(-3, 3, size=(3000, 3))
    y = np.sin(X[:, 0]) * 2 + X[:, 1] ** 2 * 0.5 + rng.normal(0, 0.1, 3000)
    m = ensemble.GradientBoostingRegressor(n_estimators=400, learning_rate=0.1, max_depth=4,
                                           early_stopping_rounds=20).fit(X[:2000], y[:2000],
                                                                         eval_set=(X[2000:], y[2000:]))
    assert metrics.rmse(y[2000:], m.predict(X[2000:])) < 0.25
    assert m.best_iteration_ <= 400
    assert m.train_loss_[0] > m.train_loss_[-1]
    m2 = ensemble.GradientBoostingRegressor.from_dict(m.to_dict())
    assert np.allclose(m.predict(X), m2.predict(X))
    imp = m.feature_importances_
    assert imp[2] < imp[0] and imp[2] < imp[1]  # feature nhiễu ít quan trọng nhất


def test_gbdt_classifier_logloss():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(2000, 3))
    y = (X[:, 0] + X[:, 1] ** 2 > 1).astype(int)
    m = ensemble.GradientBoostingClassifier(n_estimators=150, learning_rate=0.1, max_depth=3).fit(X, y)
    p = m.predict_proba(X)[:, 1]
    assert metrics.roc_auc(y, p) > 0.97
    assert np.isclose(m.init_, np.log(y.mean() / (1 - y.mean())))


# ------------------------------------------------------------ anomaly
def test_isolation_forest_flags_injected_outliers():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(1000, 2))
    X[:5] = [[8, 8], [-7, 9], [9, -8], [10, 0], [0, -10]]
    m = anomaly.IsolationForest(n_estimators=100, contamination=0.01).fit(X)
    s = m.score_samples(X)
    assert s[:5].min() > np.quantile(s[5:], 0.99)
    assert s[:5].min() > 0.6 and np.median(s[5:]) < 0.5
    m2 = anomaly.IsolationForest.from_dict(m.to_dict())
    assert np.allclose(s, m2.score_samples(X))
    assert np.isclose(anomaly.c_factor(2), 1.0) and anomaly.c_factor(1) == 0


def test_cusum_detects_drift():
    rng = np.random.default_rng(0)
    x = np.r_[rng.normal(10, 1, 200), rng.normal(11.5, 1, 100)]
    c = anomaly.CUSUM(k=0.5, h=8).fit(x[:200])
    res = c.fit(x[:200]).detect(x)
    first = [i for i, d in res["alarms"] if d == 1]
    assert first and 200 <= first[0] < 230


def test_hourly_zscore():
    hours = np.tile(np.arange(24), 30)
    x = 10 + hours * 0.5 + np.random.default_rng(0).normal(0, 0.1, len(hours))
    m = anomaly.HourlyZScore(3).fit(x, hours)
    assert m.predict([10 + 12 * 0.5 + 2.0], [12])[0] == 1
    assert m.predict([10 + 12 * 0.5], [12])[0] == 0


# ------------------------------------------------------------ neural nets (gradient check)
def test_mlp_gradcheck_all_tasks():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(15, 4))
    for task, Y in [("regression", rng.normal(size=(15, 2))),
                    ("binary", rng.integers(0, 2, (15, 1)).astype(float)),
                    ("multiclass", np.eye(3)[rng.integers(0, 3, 15)])]:
        m = nn.MLP(hidden=(5, 4), activation="tanh", task=task, l2=1e-3)
        p = m.init_params(4, Y.shape[1])
        assert nn.gradient_check(m.loss_and_grad, p, X, Y) < 1e-5


def test_gru_gradcheck():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(6, 5, 3))
    Y = rng.normal(size=(6, 2))
    m = nn.GRURegressor(hidden=4, l2=1e-3)
    p = m.init_params(3, 2)
    for k in p:  # tham số ngẫu nhiên hơn để gradient có ý nghĩa
        p[k] += rng.normal(0, 0.3, p[k].shape)
    assert nn.gradient_check(m.loss_and_grad, p, X, Y, n_checks=30) < 1e-5


def test_mlp_learns_sine_and_gru_learns_sum():
    rng = np.random.default_rng(0)
    x = rng.uniform(-3, 3, (800, 1))
    m = nn.MLP(hidden=(32,), activation="tanh", lr=0.01, epochs=300, batch_size=64).fit(x, np.sin(x).ravel())
    assert metrics.mae(np.sin(x).ravel(), m.predict(x)) < 0.08
    Xs = rng.normal(size=(600, 6, 1))
    ys = Xs.sum(axis=(1, 2))
    g = nn.GRURegressor(hidden=16, lr=0.01, epochs=60).fit(Xs, ys)
    assert metrics.r2(ys, g.predict(Xs)) > 0.9


# ------------------------------------------------------------ explain + serialize
def test_permutation_importance_ranks_signal_first():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(500, 3))
    y = 5 * X[:, 1] + 0.1 * rng.normal(size=500)
    m = linear.Ridge(alpha=0.0).fit(X, y)
    res = explain.permutation_importance(m.predict, X, y, metrics.mae, feature_names=["a", "b", "c"])
    assert res[0][0] == "b"


def test_save_load_json_and_npz(tmp_path):
    rng = np.random.default_rng(0)
    X = rng.normal(size=(100, 3))
    y = X[:, 0] * 2
    bundle = {"scaler": preprocessing.StandardScaler().fit(X), "model": linear.Ridge(1.0).fit(X, y),
              "features": ["a", "b", "c"]}
    p = save_model(bundle, tmp_path / "bundle", model_ver="t1", data_hash=dataset_hash(X, y))
    b2, head = load_model(p)
    assert head["model_ver"] == "t1" and b2["features"] == ["a", "b", "c"]
    assert np.allclose(b2["model"].predict(X), bundle["model"].predict(X))
    mlp = nn.MLP(hidden=(4,), epochs=2).fit(X, y)
    p2 = save_model(mlp, tmp_path / "mlp", model_ver="n1")
    assert (tmp_path / "mlp.npz").exists()
    m2, _ = load_model(p2)
    assert np.allclose(m2.predict(X), mlp.predict(X))
