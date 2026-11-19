from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import altair as alt
import pandas as pd
import requests
import streamlit as st

import theme as ui

API = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
TZ = "Asia/Ho_Chi_Minh"
REPO = Path(__file__).resolve().parents[1]
LEVEL = {0: ("🟢", "Bình thường"), 1: ("🟡", "Chú ý"), 2: ("🟠", "Cảnh báo"), 3: ("🔴", "Nguy hiểm")}
TARGET_NAME = {"temp": "Nhiệt độ (°C)", "hum": "Độ ẩm (%)", "rain_prob": "Xác suất mưa",
               "rain_ens": "Mưa — ensemble", "rain_ml": "Mưa — LightGBM"}
RAIN_MAX_DEV = 10  # mục tiêu: xác suất mưa không lệch số Google (nhập tay) quá 10 điểm %
WINDOWS = {"1 giờ": (dt.timedelta(hours=1), "raw", "%H:%M"), "24 giờ": (dt.timedelta(hours=24), "10m", "%H:%M"),
           "7 ngày": (dt.timedelta(days=7), "1h", "%d/%m")}
SERIES = {"temp_dht": ("Nhiệt độ", "°C", ui.COLORS["temp"]), "hum": ("Độ ẩm", "%RH", ui.COLORS["hum"]),
          "pressure_msl": ("Áp suất MSL", "hPa", ui.COLORS["pressure"]), "lux": ("Ánh sáng", "lux", ui.COLORS["light"]),
          "rain_level": ("Mức mưa", "0–3", ui.COLORS["rain"]), "gas_ppm": ("Khí gas", "ppm", ui.COLORS["gas"]),
          "edge_risk": ("Cấp cảnh báo edge", "0–3", ui.LEVEL_COLORS[3])}
RAIN = ["Khô", "Mưa phùn", "Mưa vừa", "Mưa to"]
PAGES = {"overview": "Tổng quan", "charts": "Biểu đồ", "forecast": "Dự báo", "alerts": "Cảnh báo",
         "device": "Thiết bị", "models": "Mô hình"}
SENSOR_COLORS = {"ok": ui.LEVEL_COLORS[0], "warn": ui.LEVEL_COLORS[1], "error": ui.LEVEL_COLORS[3],
                 "unknown": "#8e9aab"}

st.set_page_config(page_title="VKU AIoT Station", page_icon="◐", layout="wide", initial_sidebar_state="collapsed")
st.html(ui.CSS)


def api_get(path, **params):
    try:
        r = requests.get(f"{API}{path}", params={k: v for k, v in params.items() if v is not None}, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.session_state["api_error"] = f"{path}: {e}"
        return None


def api_write(method, path, json=None):
    tok = st.session_state.get("token")
    if not tok:
        st.error("Cần đăng nhập (nút tài khoản ở góc phải) để thực hiện thao tác này.")
        return None
    r = requests.request(method, f"{API}{path}", json=json, headers={"Authorization": f"Bearer {tok}"}, timeout=20)
    if r.status_code >= 400:
        st.error(f"Lỗi {r.status_code}: {r.text[:300]}")
        return None
    return r.json()


def login(user, pw):
    try:
        r = requests.post(f"{API}/api/auth/token", data={"username": user, "password": pw}, timeout=10)
        if r.ok:
            st.session_state["token"] = r.json()["access_token"]
            st.session_state["user"] = user
            return True
    except Exception:
        pass
    return False


def to_local(s):
    return pd.to_datetime(s, utc=True, format="mixed").dt.tz_convert(TZ)


def local_ts(v, fmt_="%H:%M:%S %d/%m/%Y"):
    return "—" if not v else to_local(pd.Series([v]))[0].strftime(fmt_)


def fmt(v, nd=1, unit=""):
    return "—" if v is None or (isinstance(v, float) and pd.isna(v)) else f"{v:,.{nd}f}{unit}".replace(",", " ")


def gas_status(t, online, gas_sensor, last_alert):
    """(html, màu) cho dải trạng thái khí."""
    lvl = int(t.get("edge_risk") or 0) if t else 0
    if not t:
        return "Chưa có dữ liệu từ trạm", "#8e9aab"
    if not online:
        return (f"Trạm mất kết nối từ {local_ts(t.get('ts'), '%H:%M:%S')} — chưa biết tình trạng khí "
                f"<small>· cấp cuối {lvl} {LEVEL[lvl][1]}</small>"), "#6b7686"
    if last_alert.get("type") == "test" and int(last_alert.get("level") or 0) > 0:
        return "Đang thử còi — không phải sự cố khí", "#2563eb"
    if gas_sensor == "error":
        return "Lỗi cảm biến khí MQ-2 — không đánh giá được khí", "#6b7686"
    if (t.get("extra") or {}).get("warming_up"):
        return "MQ-2 đang làm nóng — chưa đánh giá khí", "#8e9aab"
    return f"Cấp cảnh báo khí: <b>{lvl} — {LEVEL[lvl][1]}</b>", ui.LEVEL_COLORS[lvl]


def panel(key):
    return st.container(key=f"panel-{key}")


# ------------------------------------------------------------------ khung chung
if "token" not in st.session_state and os.environ.get("DASHBOARD_USER"):
    login(os.environ["DASHBOARD_USER"], os.environ.get("DASHBOARD_PASS", ""))

devices = api_get("/api/devices") or []
ids = [d["id"] for d in devices] or ["station01"]
want = st.query_params.get("device", os.environ.get("DEFAULT_DEVICE_ID", "station01"))
dev_key = st.session_state.get("device", want if want in ids else ids[0])
dev_row = next((d for d in devices if d["id"] == dev_key), {})
online = dev_row.get("status") == "online"
st.html(ui.topbar("ESP32 · DHT22 · BMP280 · BH1750 · YL-83 · MQ-2 · MQTT", [
    ui.pill(dev_key, "ok" if online else ("bad" if dev_row else "")),
    ui.pill("Online" if online else ("Offline" if dev_row else "Không rõ"), "ok" if online else "bad"),
    ui.pill("API", "bad" if not devices and st.session_state.get("api_error") else "ok"),
]))

nav, sel, acc = st.columns([5, 2, 1.2], vertical_alignment="center")
with nav:
    qp = st.query_params.get("page", "overview")
    keys = list(PAGES)
    with st.container(key="nav"):
        page = st.radio("Trang", list(PAGES.values()), index=keys.index(qp) if qp in keys else 0, horizontal=True,
                        label_visibility="collapsed")
with sel:
    device = st.selectbox("Thiết bị", ids, index=ids.index(dev_key) if dev_key in ids else 0, key="device",
                          label_visibility="collapsed")
with acc:
    with st.popover(f"👤 {st.session_state['user']}" if st.session_state.get("token") else "Đăng nhập",
                    width="stretch"):
        if st.session_state.get("token"):
            st.caption(f"Đã đăng nhập: {st.session_state.get('user')}")
            if st.button("Đăng xuất", width="stretch"):
                st.session_state.pop("token", None)
                st.rerun()
        else:
            with st.form("login"):
                u = st.text_input("Tài khoản", "admin")
                p = st.text_input("Mật khẩu", type="password")
                if st.form_submit_button("Đăng nhập", type="primary"):
                    st.toast("Đã đăng nhập") if login(u, p) else st.error("Sai tài khoản/mật khẩu")


# ------------------------------------------------------------------ Tổng quan
def page_overview():
    @st.fragment(run_every=2)
    def live():
        dev = api_get(f"/api/devices/{device}") or {}
        t = api_get("/api/telemetry/latest", device_id=device) or {}
        health = api_get(f"/api/sensors/{device}", minutes=10) or {}
        stt = {s["sensor"]: s.get("status") for s in health.get("sensors") or []}
        last_alert = (api_get("/api/alerts", device_id=device, limit=1) or [{}])[0]
        is_online = dev.get("status") == "online"
        text, color = gas_status(t, is_online, stt.get("gas"), last_alert)
        st.html(ui.status(text, color))
        st.html(ui.info_bar([
            ("Cập nhật", local_ts(t.get("ts"), "%H:%M:%S %d/%m")),
            ("Wi-Fi RSSI", f"{dev['rssi']} dBm" if dev.get("rssi") is not None else "—"),
            ("Trạng thái", "Online" if is_online else "Offline"),
        ]))

        def c(title, sensor, value, nd, unit, sub, color):
            bad = stt.get(sensor) == "error"
            return ui.card(title, "⚠ Lỗi" if bad else fmt(value, nd), "" if bad else unit, sub, color, alert=bad)

        rain_lvl = t.get("rain_level")
        rain = ui.card("Mưa", "⚠ Lỗi" if stt.get("rain") == "error" else
                       (RAIN[int(rain_lvl)] if rain_lvl is not None else "—"), "", "YL-83", ui.COLORS["rain"],
                       alert=stt.get("rain") == "error")
        st.html(ui.cards([
            c("Nhiệt độ", "dht", t.get("temp_dht"), 1, "°C", "DHT22", ui.COLORS["temp"]),
            c("Độ ẩm", "dht", t.get("hum"), 0, "%RH", "DHT22", ui.COLORS["hum"]),
            c("Áp suất MSL", "bmp", t.get("pressure_msl"), 1, "hPa", "BMP280", ui.COLORS["pressure"]),
            c("Ánh sáng", "bh", t.get("lux"), 0, "lux", "BH1750", ui.COLORS["light"]),
            rain,
            c("Khí gas", "gas", t.get("gas_ppm"), 0, "ppm", "MQ-2", ui.COLORS["gas"]),
        ]))

        a, b, d = st.columns([1.2, 1, 1])
        with a, panel("sensors"):
            rows = []
            for s in health.get("sensors") or []:
                extra = ""
                if s.get("status") != "ok":
                    extra = (f"<small>Lần cuối hoạt động tốt: {local_ts(s['last_ok'], '%H:%M:%S %d/%m')}</small>"
                             if s.get("last_ok") else "<small>Chưa ghi nhận lần nào hoạt động tốt</small>")
                rows.append(f"<div class='sensor' style='--c:{SENSOR_COLORS.get(s.get('status'), '#8e9aab')}'><i></i>"
                            f"<div><b>{ui.esc(s['name'])}</b> <small>{ui.esc(s['measures'])}</small>"
                            f"{ui.esc(s['message'])}{extra}</div></div>")
            bad = [s["name"] for s in health.get("sensors") or [] if s.get("status") == "error"]
            note = (f"<p class='note' style='color:var(--bad)'>⚠ Cảm biến đang lỗi: {ui.esc(', '.join(bad))} — "
                    f"số liệu của cảm biến này không đáng tin.</p>") if bad else ""
            st.html(ui.title("Tình trạng cảm biến", f"{health.get('window_min', 10)} phút gần nhất")
                    + ("".join(rows) or "<p class='empty'>Chưa có dữ liệu.</p>") + note)
        with b, panel("forecast"):
            fc = api_get(f"/api/forecast/{device}", history_h=1) or {}
            body = "<p class='empty'>Chưa có dự báo.</p>"
            if fc.get("latest"):
                df = pd.DataFrame(fc["latest"])
                df = df[~df.target.isin(["rain_ml", "rain_ens"])]
                df["Đại lượng"] = df["target"].map(TARGET_NAME)
                df["v"] = df.apply(lambda r: f"{r.value * 100:.0f} %" if r.target.startswith("rain")
                                   else f"{r.value:.1f}", axis=1)
                pv = df.pivot(index="Đại lượng", columns="horizon", values="v")
                pv.columns = [f"+{h}h" for h in pv.columns]
                body = ui.table(pv.reset_index()) + f"<p class='note'>Nguồn: {ui.esc(fc.get('source'))}</p>"
            st.html(ui.title("Dự báo mới nhất") + body)
        with d, panel("alerts"):
            al = (api_get("/api/alerts", device_id=device, limit=6) or [])[:6]
            items = "".join(
                f"<div class='alert-row'><time>{local_ts(x['ts'], '%H:%M:%S %d/%m')}</time>"
                f"{ui.level_badge(x['level'], LEVEL[int(x['level'])][1])}{ui.esc(x['type'])} · {ui.esc(x['source'])}"
                f"{' · ✅' if x.get('ack_ts') else ''}</div>" for x in al)
            st.html(ui.title("Cảnh báo gần đây") + (items or "<p class='empty'>Chưa có cảnh báo.</p>"))
    live()


# ------------------------------------------------------------------ Biểu đồ
def page_charts():
    tb1, tb2 = st.columns([1, 2], vertical_alignment="center")
    win = tb1.segmented_control("Cửa sổ", list(WINDOWS), default="24 giờ", label_visibility="collapsed") or "24 giờ"
    cols = tb2.multiselect("Đại lượng", list(SERIES), default=["temp_dht", "hum", "pressure_msl", "gas_ppm"],
                           format_func=lambda c: SERIES[c][0], label_visibility="collapsed")
    delta, res, xf = WINDOWS[win]
    now = dt.datetime.now(dt.timezone.utc)
    data = api_get("/api/telemetry", device_id=device, resolution=res, **{"from": (now - delta).timestamp()})
    if not data:
        st.info("Không có dữ liệu trong cửa sổ này.")
        return
    df = pd.DataFrame(data)
    df["ts"] = to_local(df["ts"])
    grid = st.columns(2)
    for i, c in enumerate(x for x in cols if x in df):
        name, unit, color = SERIES[c]
        with grid[i % 2], panel(f"chart-{c}"):
            st.html(ui.title(f"{name} ({unit})"))
            st.altair_chart(ui.line_chart(df, "ts", c, color, x_format=xf), width="stretch", theme=None)
    left, right = st.columns([2, 1])
    with left, panel("stats"):
        rows = [{"Đại lượng": f"{SERIES[c][0]} ({SERIES[c][1]})", "Nhỏ nhất": fmt(df[c].min(), 1),
                 "Lớn nhất": fmt(df[c].max(), 1), "Trung bình": fmt(df[c].mean(), 1)} for c in SERIES if c in df]
        st.html(ui.title("Thống kê", win) + ui.table(pd.DataFrame(rows)) + f"<p class='note'>{len(df)} điểm dữ liệu</p>")
    with right, panel("export"):
        st.html(ui.title("Xuất dữ liệu"))
        st.download_button("⇩ CSV cửa sổ này", df.to_csv(index=False).encode("utf-8"), f"{device}_{res}.csv", "text/csv",
                           width="stretch")
        st.link_button("⇩ CSV dữ liệu thô 24 giờ", f"{API}/api/export.csv?device_id={device}", width="stretch")


# ------------------------------------------------------------------ Dự báo
def forecast_vs_station(h: pd.DataFrame, obs: pd.DataFrame, obs_col: dict) -> pd.DataFrame:
    """MAE và độ lệch trung bình của dự báo so với số đo trạm, theo đại lượng × tầm dự báo."""
    if not len(h) or not len(obs):
        return pd.DataFrame()
    o = obs.copy()
    o["t_mid"] = o["ts"] + pd.Timedelta(minutes=30)
    o = o.sort_values("t_mid")
    rows = []
    for tgt, col in obs_col.items():
        if col not in o:
            continue
        for hz in (1, 3, 6):
            d = h[(h.target == tgt) & (h.horizon == hz)].sort_values("valid_at").drop_duplicates("valid_at", keep="last")
            if not len(d):
                continue
            m = pd.merge_asof(d[["valid_at", "value"]], o[["t_mid", col]].dropna(), left_on="valid_at", right_on="t_mid",
                              direction="nearest", tolerance=pd.Timedelta(minutes=30)).dropna()
            if not len(m):
                continue
            e = m["value"] - m[col]
            rows.append({"Đại lượng": TARGET_NAME[tgt], "Tầm": f"+{hz}h", "Số giờ": len(m),
                         "MAE": round(float(e.abs().mean()), 2), "Lệch TB (dự báo − đo)": round(float(e.mean()), 2)})
    return pd.DataFrame(rows)


def google_table(rows: list[dict]) -> pd.DataFrame:
    """Bảng số Google đã nhập so với dự báo ensemble đã hiệu chỉnh (giờ địa phương, điểm %)."""
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows)
    d["Giờ"] = to_local(d["valid_at"]).dt.strftime("%H:%M %d/%m")
    d["Lệch"] = (d["pred_pct"] - d["google_pct"]).abs()
    out = pd.DataFrame({"Giờ": d["Giờ"], "Google (%)": d["google_pct"].round(0),
                        "Hệ thống (%)": d["pred_pct"].round(0), "Lệch (điểm)": d["Lệch"].round(0)})
    out["≤ 10"] = ["✅" if e <= RAIN_MAX_DEV else "❌" for e in d["Lệch"]]
    return out


def google_panel():
    """Nhập số Google tra trên Google Search (miễn phí) → so sánh, rồi học hiệu chỉnh ensemble."""
    g = api_get("/api/rain/google", limit=24) or {}
    m, cal = g.get("metrics") or {}, g.get("calibration") or {}
    n, need = m.get("n") or 0, g.get("min_fit_rows", 40)
    with panel("fc-google"):
        summary = (f"{n} giờ đã nhập · lệch TB {m['MAE']:.1f} điểm · {m['within10'] * 100:.0f} % số giờ lệch ≤ {RAIN_MAX_DEV}"
                   if n else "Chưa nhập số Google nào")
        w = cal.get("weights") or {}
        how = (f"Đang dùng: <b>{ui.esc(cal.get('version', '?'))}</b> — ngưỡng {cal.get('threshold')} mm, trọng số "
               + ", ".join(f"{ui.esc(k)} {v:g}" for k, v in w.items())
               + (", ánh xạ đẳng biến" if cal.get("isotonic") else ""))
        st.html(ui.title("Xác suất mưa so với Google", "nhập tay, miễn phí") + f"<p class='note'>{summary}. {how}.</p>")
        now = pd.Timestamp.now(tz=TZ)
        with st.form("google-form", clear_on_submit=True, border=False):
            c1, c2 = st.columns(2)
            day = c1.date_input("Ngày Google hiển thị", value=now.date(), format="DD/MM/YYYY")
            first = c2.selectbox("Giờ đầu tiên (ô bên trái)", list(range(24)), index=(now.hour + 1) % 24,
                                 format_func=lambda x: f"{x:02d}:00")
            cols = st.columns(5)
            vals = [cols[k].number_input(f"Ô {k + 1} (%)", 0, 100, value=None, step=10, key=f"g{k}") for k in range(5)]
            if st.form_submit_button("Lưu số Google", width="stretch"):
                t0 = pd.Timestamp(day) + pd.Timedelta(hours=first)
                items = [{"valid_at": (t0 + pd.Timedelta(hours=k)).isoformat(), "pct": v}
                         for k, v in enumerate(vals) if v is not None]
                if not items:
                    st.warning("Chưa nhập ô nào.")
                elif api_write("POST", "/api/rain/google", {"items": items}):
                    st.toast(f"Đã lưu {len(items)} giờ")
                    st.rerun()
        if st.button(f"Học lại hiệu chỉnh từ số Google ({n}/{need} giờ)", disabled=n < need, width="stretch"):
            c = api_write("POST", "/api/rain/calibrate")
            if c:
                v = (c.get("metrics") or {}).get("valid_recent") or {}
                st.toast(f"Hiệu chỉnh mới {c['version']}: lệch TB {v.get('MAE')} điểm trên dữ liệu mới nhất")
                st.rerun()
        t = google_table(g.get("rows") or [])
        if len(t):
            st.html(ui.table(t))
        st.html("<p class='note'>Tra \"dự báo thời tiết tại VKU\" trên Google, chọn đúng ngày, nhập 5 ô xác suất mưa theo giờ. "
                "Hệ thống chụp dự báo ensemble Open-Meteo (ECMWF + GFS + ICON, miễn phí) cho đúng các giờ đó; đủ "
                f"{need} giờ thì bấm học lại để chọn ngưỡng mưa và trọng số mô hình sao cho gần Google nhất.</p>")


def page_forecast():
    fc = api_get(f"/api/forecast/{device}", history_h=72) or {}
    tb1, tb2 = st.columns([3, 1], vertical_alignment="center")
    horizon = tb1.segmented_control("Tầm dự báo", [1, 3, 6], default=1, format_func=lambda x: f"+{x} giờ",
                                    label_visibility="collapsed") or 1
    if tb2.button("⟳ Chạy dự báo ngay", width="stretch"):
        if api_write("POST", f"/api/forecast/{device}/run"):
            st.toast("Đã chạy dự báo")
            st.rerun()
    if not fc.get("history"):
        st.info("Chưa có dự báo. Backend chạy forecast mỗi 10 phút.")
        google_panel()
        return
    h = pd.DataFrame(fc["history"])
    h["valid_at"] = to_local(h["valid_at"])
    r = h[h.target == "rain_prob"].sort_values("created_at").groupby("horizon").tail(1).sort_values("horizon")
    e = h[h.target == "rain_ens"].set_index(["created_at", "horizon"])["value"]

    def rain_card(row):
        ev = e.get((row.created_at, row.horizon))
        if ev is None:
            return ui.card(f"Mưa trong {int(row.horizon)} giờ tới", f"{row.value * 100:.0f}", "%",
                           "LightGBM (dự phòng, không có ensemble)", ui.COLORS["hum"])
        return ui.card(f"Mưa lúc +{int(row.horizon)} giờ", f"{row.value * 100:.0f}", "%",
                       f"Ensemble {ev * 100:.0f} % · trạm {(row.value - ev) * 100:+.0f}", ui.COLORS["hum"])
    st.html(ui.cards([rain_card(row) for _, row in r.iterrows()]))
    now = dt.datetime.now(dt.timezone.utc)
    obs = pd.DataFrame(api_get("/api/telemetry", device_id=device, resolution="1h",
                               **{"from": (now - dt.timedelta(hours=72)).timestamp()}) or [])
    if len(obs):
        obs["ts"] = to_local(obs["ts"])
    obs_col = {"temp": "temp_dht", "hum": "hum"}
    cols = st.columns(2)
    for i, tgt in enumerate(["temp", "hum"]):
        d = h[(h.target == tgt) & (h.horizon == horizon)].sort_values("valid_at").drop_duplicates("valid_at",
                                                                                                    keep="last")
        if not len(d):
            continue
        color = ui.COLORS["temp" if tgt == "temp" else "hum"]
        base = alt.Chart(d).encode(x=alt.X("valid_at:T", title=None, axis=alt.Axis(format="%H:%M %d/%m")))
        band = base.mark_area(opacity=0.15, color=color).encode(
            y=alt.Y("lower:Q", scale=alt.Scale(zero=False), title=None), y2="upper:Q")
        line = base.mark_line(color=color, strokeWidth=2, point=alt.OverlayMarkDef(color=color, size=30)).encode(
            y="value:Q", tooltip=[alt.Tooltip("valid_at:T", title="Thời điểm", format="%H:%M %d/%m"),
                                  alt.Tooltip("value:Q", title="Dự báo", format=".1f"),
                                  alt.Tooltip("lower:Q", title="Thấp", format=".1f"),
                                  alt.Tooltip("upper:Q", title="Cao", format=".1f")])
        layers = [band, line]
        if len(obs) and obs_col[tgt] in obs:
            layers.append(alt.Chart(obs).mark_line(color=ui.COLORS["observed"], strokeDash=[4, 3]).encode(
                x="ts:T", y=f"{obs_col[tgt]}:Q"))
        with cols[i], panel(f"fc-{tgt}"):
            st.html(ui.title(TARGET_NAME[tgt], f"+{horizon} giờ"))
            st.altair_chart(alt.layer(*layers).properties(height=250), width="stretch", theme=None)
    st.html("<p class='note'>Đường màu: dự báo, vùng tô: khoảng tin cậy 95 %. Nét đứt xám: số đo tại trạm.</p>")
    err = forecast_vs_station(h, obs, obs_col)
    if len(err):
        with panel("fc-err"):
            st.html(ui.title("Sai số dự báo so với số đo tại trạm") + ui.table(err))
    google_panel()


# ------------------------------------------------------------------ Cảnh báo
def page_alerts():
    c1, c2, c3 = st.columns([2, 1, 1], vertical_alignment="center")
    lvl = c1.multiselect("Cấp", [0, 1, 2, 3], default=[1, 2, 3], format_func=lambda x: f"{x} · {LEVEL[x][1]}",
                         label_visibility="collapsed")
    src = c2.selectbox("Nguồn", ["tất cả", "edge", "cloud"], label_visibility="collapsed")
    unacked = c3.toggle("Chỉ chưa xử lý")
    al = api_get("/api/alerts", device_id=device, limit=500, unacked=unacked or None,
                 source=None if src == "tất cả" else src) or []
    df = pd.DataFrame(al)
    if not len(df):
        st.info("Không có cảnh báo.")
        return
    df = df[df.level.isin(lvl)]
    df["ts_local"] = to_local(df["ts"])
    if len(df):
        with panel("timeline"):
            st.html(ui.title("Dòng thời gian", f"{len(df)} cảnh báo"))
            tl = alt.Chart(df).mark_circle(size=90, opacity=0.85).encode(
                x=alt.X("ts_local:T", title=None, axis=alt.Axis(format="%H:%M %d/%m")),
                y=alt.Y("level:Q", scale=alt.Scale(domain=[0, 3]), title=None, axis=alt.Axis(values=[0, 1, 2, 3])),
                color=alt.Color("source:N", title="Nguồn", scale=alt.Scale(range=["#2563eb", "#e8590c"])),
                tooltip=[alt.Tooltip("ts_local:T", title="Thời gian", format="%H:%M:%S %d/%m"), "level", "type", "source",
                         "gas_ppm"])
            st.altair_chart(tl.properties(height=190), width="stretch", theme=None)
    with panel("alert-list"):
        st.html(ui.title("Danh sách"))
        for _, a in df.head(50).iterrows():
            left, right = st.columns([6, 1], vertical_alignment="center")
            ppm = f" · {fmt(a.gas_ppm, 0)} ppm" if a.gas_ppm is not None and not pd.isna(a.gas_ppm) else ""
            cause = f" · {', '.join(a.cause)}" if isinstance(a.cause, list) and a.cause else ""
            left.html(f"<div class='alert-row'><time>{a.ts_local:%H:%M:%S %d/%m/%Y}</time>"
                      f"{ui.level_badge(a.level, LEVEL[int(a.level)][1])}<b>{ui.esc(a.type)}</b> · "
                      f"{ui.esc(a.source)}{ui.esc(ppm)}{ui.esc(cause)}</div>")
            if pd.isna(a.ack_ts) and a.level > 0:
                if right.button("Xác nhận", key=f"ack{a.id}", width="stretch"):
                    if api_write("POST", f"/api/alerts/{int(a.id)}/ack", json={"by": st.session_state.get("user")}):
                        st.toast("Đã xác nhận cảnh báo")
                        st.rerun()
            elif not pd.isna(a.ack_ts):
                right.html(f"<span class='pill ok'><i></i><b>{ui.esc(a.acknowledged_by)}</b></span>")


# ------------------------------------------------------------------ Thiết bị
def page_device():
    dev = api_get(f"/api/devices/{device}") or {}
    cfg = (dev.get("config") or {}).get("config") or {}
    st.html(ui.info_bar([("Thiết bị", dev.get("name", device)), ("Vị trí", dev.get("location") or "—"),
                         ("Firmware", dev.get("fw") or "—"), ("Mô hình", dev.get("model_ver") or "—"),
                         ("Lần cuối", local_ts(dev.get("last_seen"), "%H:%M:%S %d/%m")),
                         ("Trạng thái", dev.get("status") or "—")]))
    left, right = st.columns([1, 2])
    with left, panel("cmd"):
        st.html(ui.title("Điều khiển thiết bị"))
        for cmd, label, kind in [("test_alarm", "🔔 Thử còi", "primary"), ("mute", "🔇 Tắt còi 5 phút", "secondary"),
                                 ("calibrate", "🎯 Hiệu chuẩn R0", "secondary"), ("reboot", "⏻ Khởi động lại", "secondary")]:
            if st.button(label, width="stretch", type=kind):
                r = api_write("POST", f"/api/devices/{device}/cmd", json={"cmd": cmd})
                if r:
                    st.toast(f"Đã gửi {cmd} (id {r['id'][:8]})")
        st.html("<p class='note'>Lệnh gửi qua MQTT <code>…/cmd</code>; thiết bị trả lời ở <code>…/ack</code>.</p>")
    with right, panel("cfg"):
        st.html(ui.title("Cấu hình ngưỡng & chu kỳ"))
        with st.form("cfg", border=False):
            c = st.columns(3)
            th1 = c[0].number_input("Ngưỡng Chú ý (ppm)", 1.0, 9999.0, float(cfg.get("th1", 300)))
            th2 = c[1].number_input("Ngưỡng Cảnh báo (ppm)", 1.0, 9999.0, float(cfg.get("th2", 1000)))
            th3 = c[2].number_input("Ngưỡng Nguy hiểm (ppm)", 1.0, 9999.0, float(cfg.get("th3", 2000)))
            c = st.columns(3)
            slope1 = c[0].number_input("Độ dốc bất thường (ppm/s)", 0.1, 1000.0, float(cfg.get("slope1", 15)))
            hyst = c[1].slider("Hysteresis", 0.0, 0.45, float(cfg.get("hyst", 0.15)))
            tel = c[2].number_input("Chu kỳ telemetry (ms)", 1000, 600000, int(cfg.get("telemetry_ms", 5000)), step=1000)
            c = st.columns(3)
            dbu = c[0].number_input("Debounce tăng (mẫu)", 1, 30, int(cfg.get("debounce_up", 3)))
            dbd = c[1].number_input("Debounce giảm (mẫu)", 1, 60, int(cfg.get("debounce_down", 5)))
            modes = ["hybrid", "rule", "model"]
            mode = c[2].selectbox("Chế độ edge", modes, index=modes.index(cfg.get("mode", "hybrid")))
            if st.form_submit_button("💾 Gửi cấu hình xuống thiết bị", type="primary"):
                r = api_write("PUT", f"/api/devices/{device}/config",
                              json={"th1": th1, "th2": th2, "th3": th3, "slope1": slope1, "hyst": hyst,
                                    "telemetry_ms": int(tel), "debounce_up": int(dbu), "debounce_down": int(dbd),
                                    "mode": mode})
                if r:
                    st.toast(f"Đã gửi cấu hình v{r['version']} — chờ thiết bị xác nhận")
    hist = api_get(f"/api/devices/{device}/configs") or []
    cmds = api_get(f"/api/devices/{device}/commands") or []
    a, b = st.columns(2)
    with a, panel("cfg-hist"):
        body = "<p class='empty'>Chưa có.</p>"
        if hist:
            h = pd.DataFrame(hist)[["version", "created_at", "created_by", "acked"]]
            h["created_at"] = to_local(h["created_at"]).dt.strftime("%H:%M %d/%m")
            h["acked"] = h["acked"].map({True: "✅", False: "—"})
            body = ui.table(h.rename(columns={"version": "Phiên bản", "created_at": "Thời gian", "created_by": "Người gửi",
                                              "acked": "Thiết bị nhận"}))
        st.html(ui.title("Lịch sử cấu hình") + body)
    with b, panel("cmd-hist"):
        body = "<p class='empty'>Chưa có.</p>"
        if cmds:
            c = pd.DataFrame(cmds)[["created_at", "cmd", "created_by", "acked"]]
            c["created_at"] = to_local(c["created_at"]).dt.strftime("%H:%M %d/%m")
            c["acked"] = c["acked"].map({True: "✅", False: "—"})
            body = ui.table(c.rename(columns={"created_at": "Thời gian", "cmd": "Lệnh", "created_by": "Người gửi",
                                              "acked": "Thiết bị nhận"}))
        st.html(ui.title("Lịch sử lệnh") + body)
    if dev.get("last_status"):
        with st.expander("Trạng thái chi tiết (status)"):
            st.json(dev["last_status"])


# ------------------------------------------------------------------ Mô hình
def page_models():
    ms = api_get("/api/models") or []
    if ms:
        df = pd.DataFrame(ms)
        act = df[df.active].sort_values("name")[["name", "model", "model_ver", "metric_name", "metric_value"]].copy()
        act["metric_value"] = act["metric_value"].map(lambda v: f"{v:.3f}")
        with panel("models"):
            st.html(ui.title("Mô hình đang hoạt động", f"{len(act)} mô hình") + ui.table(act.rename(columns={
                "name": "Tên", "model": "Thuật toán", "model_ver": "Phiên bản", "metric_name": "Độ đo",
                "metric_value": "Giá trị"})))
        with st.expander("Toàn bộ lịch sử registry"):
            st.dataframe(df[["name", "model_ver", "model", "metric_value", "active", "created_at"]], hide_index=True)
    for f, name in [("results_forecast.md", "Kết quả dự báo"), ("results_gas_edge.md", "Cảnh báo khí tại edge"),
                    ("results_anomaly.md", "Bất thường ở cloud")]:
        p = REPO / "docs" / "report" / f
        if p.exists():
            with st.expander(name):
                st.markdown(p.read_text(encoding="utf-8"))


{"Tổng quan": page_overview, "Biểu đồ": page_charts, "Dự báo": page_forecast, "Cảnh báo": page_alerts,
 "Thiết bị": page_device, "Mô hình": page_models}[page]()

if st.session_state.get("api_error"):
    st.warning(st.session_state.pop("api_error"))
