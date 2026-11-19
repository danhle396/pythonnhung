from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")

HERE = Path(__file__).resolve().parent
APP = str(HERE.parent / "app.py")
FIX = json.loads((HERE / "api_fixture.json").read_text(encoding="utf-8"))
PAGES = ["overview", "charts", "forecast", "alerts", "device", "models"]


class Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code, self.ok, self.text = data, status, status < 400, json.dumps(data)

    def json(self):
        return self._data

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(self.status_code)


def fake_get(url, params=None, **kw):
    path = "/" + url.split("://", 1)[-1].split("/", 1)[1]
    return Resp(FIX[path]) if path in FIX else Resp({"detail": "not found"}, 404)


def fake_post(url, data=None, **kw):
    return Resp({"access_token": "t", "token_type": "bearer"})


SENT = []


def fake_request(method, url, json=None, **kw):
    SENT.append((method, url, json))
    if url.endswith("/config"):
        return Resp({"version": 1})
    if "/ack" in url:
        return Resp({"ok": True})
    return Resp({"id": "0123456789abcdef"})


@pytest.fixture(autouse=True)
def patched(monkeypatch):
    monkeypatch.setenv("DASHBOARD_USER", "admin")
    monkeypatch.setenv("DASHBOARD_PASS", "x")
    with mock.patch("requests.get", fake_get), mock.patch("requests.post", fake_post), \
            mock.patch("requests.request", fake_request):
        yield


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_exception(page):
    at = st_testing.AppTest.from_file(APP, default_timeout=60)
    at.query_params["page"] = page
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.radio[0].value == ["Tổng quan", "Biểu đồ", "Dự báo", "Cảnh báo", "Thiết bị", "Mô hình"][PAGES.index(page)]
    assert any("topbar" in h.proto.body for h in at.html), "thiếu thanh trên cùng"


def test_overview_shows_sensor_status():
    at = st_testing.AppTest.from_file(APP, default_timeout=60)
    at.query_params["page"] = "overview"
    at.run()
    html = " ".join(h.proto.body for h in at.html)
    assert "Tình trạng cảm biến" in html
    for s in FIX["/api/sensors/station01"]["sensors"]:
        assert s["name"] in html
    bad = [s for s in FIX["/api/sensors/station01"]["sensors"] if s["status"] == "error"]
    if bad:
        assert "Cảm biến đang lỗi" in html
        assert "card alert" in html and "⚠ Lỗi" in html


def test_ack_and_config_submit():
    SENT.clear()
    at = st_testing.AppTest.from_file(APP, default_timeout=60)
    at.query_params["page"] = "alerts"
    at.run()
    ack = [b for b in at.button if b.key and b.key.startswith("ack")]
    assert ack, "phải có nút xác nhận cho cảnh báo chưa ack"
    ack[0].click().run()
    assert any("/ack" in u for _, u, _ in SENT)

    at = st_testing.AppTest.from_file(APP, default_timeout=60)
    at.query_params["page"] = "device"
    at.run()
    at.button(key="FormSubmitter:cfg-💾 Gửi cấu hình xuống thiết bị").click().run()
    put = [j for m, u, j in SENT if m == "PUT"]
    assert put and put[0]["th1"] < put[0]["th2"] < put[0]["th3"]


def test_forecast_page_rain_from_ensemble_and_google_entry(monkeypatch):
    fc = json.loads(json.dumps(FIX["/api/forecast/station01"]))
    for part in ("latest", "history"):
        extra = []
        for row in fc[part]:
            if row["target"] == "rain_prob":
                extra.append({**row, "target": "rain_ens", "value": max(0.0, row["value"] - 0.05)})
                extra.append({**row, "target": "rain_ml", "value": min(1.0, row["value"] + 0.2)})
        fc[part] += extra
    monkeypatch.setitem(FIX, "/api/forecast/station01", fc)
    monkeypatch.setitem(FIX, "/api/rain/google", {
        "rows": [{"id": 1, "entered_at": "2026-11-19T09:00:00+00:00", "valid_at": "2026-11-20T10:00:00+00:00",
                  "google_pct": 70.0, "pred_pct": 66.0, "default_pct": 66.0},
                 {"id": 2, "entered_at": "2026-11-19T09:00:00+00:00", "valid_at": "2026-11-20T13:00:00+00:00",
                  "google_pct": 40.0, "pred_pct": 66.0, "default_pct": 66.0}],
        "metrics": {"n": 2, "MAE": 15.0, "within10": 0.5}, "min_fit_rows": 40,
        "calibration": {"version": "ens-default", "threshold": 1.0, "weights": {"ecmwf": 1, "gfs": 1, "icon": 1},
                        "n": 0, "metrics": None, "isotonic": False}})
    at = st_testing.AppTest.from_file(APP, default_timeout=60)
    at.query_params["page"] = "forecast"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    html = " ".join(h.proto.body for h in at.html)
    assert "Mưa lúc +1 giờ" in html and "Ensemble " in html
    assert "Xác suất mưa so với Google" in html and "2 giờ đã nhập" in html and "50 % số giờ lệch ≤ 10" in html
    assert "17:00 20/11" in html and "❌" in html and "✅" in html
    assert any("Học lại" in b.label and b.disabled for b in at.button), "chưa đủ 40 giờ thì không cho học lại"
