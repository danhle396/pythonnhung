from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import altair as alt
import pandas as pd
import requests
import streamlit as st

API = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
TZ = "Asia/Ho_Chi_Minh"
REPO = Path(__file__).resolve().parents[1]
LEVEL = {0: ("🟢", "Bình thường", "#2e7d32"), 1: ("🟡", "Chú ý", "#f9a825"),
         2: ("🟠", "Cảnh báo", "#ef6c00"), 3: ("🔴", "NGUY HIỂM", "#c62828")}
TARGET_NAME = {"temp": "Nhiệt độ (°C)", "hum": "Độ ẩm (%)", "rain_prob": "Xác suất mưa"}
WINDOWS = {"1 giờ": (dt.timedelta(hours=1), "raw"), "24 giờ": (dt.timedelta(hours=24), "10m"),
           "7 ngày": (dt.timedelta(days=7), "1h")}
SERIES = {"temp_dht": "Nhiệt độ DHT22 (°C)", "hum": "Độ ẩm (%)", "pressure_msl": "Áp suất MSL (hPa)",
          "lux": "Ánh sáng (lux)", "rain_level": "Mức mưa (0–3)", "gas_ppm": "Khí gas (ppm)",
          "edge_risk": "Cấp cảnh báo edge"}

st.set_page_config(page_title="VKU AIoT Station", page_icon="🌦️", layout="wide")


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
        st.error("Cần đăng nhập (thanh bên trái) để thực hiện thao tác này.")
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


def fmt(v, nd=1, unit=""):
    return "—" if v is None or (isinstance(v, float) and pd.isna(v)) else f"{v:.{nd}f}{unit}"


def gas_banner(t, online, gas_status, last_alert):
    lvl = int(t.get("edge_risk") or 0)
    if not t:
        return "⚪", "Chưa có dữ liệu từ trạm", "#757575"
    if not online:
        when = f" từ {to_local(pd.Series([t['ts']]))[0]:%H:%M:%S}" if t.get("ts") else ""
        return "⚫", (f"Trạm mất kết nối{when} — chưa biết tình trạng khí "
                     f"<small>(cấp cuối: {lvl} — {LEVEL[lvl][1]})</small>"), "#616161"
    if last_alert.get("type") == "test" and int(last_alert.get("level") or 0) > 0:
        return "🔔", "Đang thử còi — không phải sự cố khí", "#1565c0"
    if gas_status == "error":
        return "⚠", "Lỗi cảm biến khí MQ-2 — không đánh giá được khí", "#616161"
    if (t.get("extra") or {}).get("warming_up"):
        return "⏳", "MQ-2 đang làm nóng — chưa đánh giá khí", "#757575"
    emoji, name, color = LEVEL[lvl]
    return emoji, f"Cấp cảnh báo khí: <b>{lvl} — {name}</b>", color


SENSOR_STYLE = {"ok": ("🟢", "#2e7d32"), "warn": ("🟡", "#f9a825"), "error": ("🔴", "#c62828"),
                "unknown": ("⚪", "#757575")}


def sensor_panel(health):
    st.subheader("Tình trạng cảm biến", help=f"Đánh giá từ số liệu {health.get('window_min', 10)} phút gần nhất")
    sensors = health.get("sensors") or []
    for c, s in zip(st.columns(len(sensors) or 1), sensors):
        icon, color = SENSOR_STYLE.get(s.get("status"), SENSOR_STYLE["unknown"])
        last = ""
        if s.get("status") != "ok":
            last = (f"<br><small>Lần cuối hoạt động tốt: {to_local(pd.Series([s['last_ok']]))[0]:%H:%M:%S %d/%m}</small>"
                    if s.get("last_ok") else "<br><small>Chưa ghi nhận lần nào hoạt động tốt</small>")
        c.markdown(f"<div style='border-left:6px solid {color};background:{color}1f;padding:10px 12px;"
                   f"border-radius:8px;min-height:150px'><b>{icon} {s['name']}</b><br>"
                   f"<small>{s['measures']}</small><br>{s['message']}{last}</div>", unsafe_allow_html=True)
    bad = [s["name"] for s in sensors if s.get("status") == "error"]
    if bad:
        st.error(f"⚠ Cảm biến đang lỗi: {', '.join(bad)} — số liệu của cảm biến này không đáng tin.")


if "token" not in st.session_state and os.environ.get("DASHBOARD_USER"):
    login(os.environ["DASHBOARD_USER"], os.environ.get("DASHBOARD_PASS", ""))

with st.sidebar:
    st.title("🌦️ VKU AIoT")
    st.caption("Trạm AIoT giám sát môi trường — dự báo thời tiết & cảnh báo khí dễ cháy, khói")
    devices = api_get("/api/devices") or []
    ids = [d["id"] for d in devices] or ["station01"]
    want = st.query_params.get("device", os.environ.get("DEFAULT_DEVICE_ID", "station01"))
    device = st.selectbox("Thiết bị", ids, index=ids.index(want) if want in ids else 0)
    pages = ["Tổng quan", "Biểu đồ", "Dự báo", "Cảnh báo", "Thiết bị", "Mô hình"]
    keys = ["overview", "charts", "forecast", "alerts", "device", "models"]
    qp = st.query_params.get("page", "overview")
    page = st.radio("Trang", pages, index=keys.index(qp) if qp in keys else 0)
    st.divider()
    if st.session_state.get("token"):
        st.success(f"Đã đăng nhập: {st.session_state.get('user')}")
        if st.button("Đăng xuất"):
            st.session_state.pop("token", None)
            st.rerun()
    else:
        with st.form("login"):
            u = st.text_input("Tài khoản", "admin")
            p = st.text_input("Mật khẩu", type="password")
            if st.form_submit_button("Đăng nhập"):
                st.success("OK") if login(u, p) else st.error("Sai tài khoản/mật khẩu")
    st.caption(f"API: {API}")
    if st.session_state.get("api_error"):
        st.warning(st.session_state.pop("api_error"))
    st.caption("⚠ Nguyên mẫu học thuật — không thay thế thiết bị báo cháy/báo gas đã chứng nhận.")


def page_overview():
    @st.fragment(run_every=5)
    def live():
        dev = api_get(f"/api/devices/{device}") or {}
        t = api_get("/api/telemetry/latest", device_id=device) or {}
        health = api_get(f"/api/sensors/{device}", minutes=10) or {}
        stt = {s["sensor"]: s.get("status") for s in health.get("sensors") or []}
        last_alert = (api_get("/api/alerts", device_id=device, limit=1) or [{}])[0]
        online = dev.get("status") == "online"
        emoji, text, color = gas_banner(t, online, stt.get("gas"), last_alert)
        c1, c2, c3 = st.columns([2, 1, 1])
        c1.markdown(f"<div style='padding:14px;border-radius:12px;background:{color};color:white;font-size:1.4rem'>"
                    f"{emoji} {text}</div>", unsafe_allow_html=True)
        c2.metric("Trạng thái", "🟢 Online" if online else "⚫ Offline")
        c3.metric("RSSI", f"{dev.get('rssi')} dBm" if dev.get("rssi") is not None else "—")

        def val(sensor, text):
            return "⚠ Lỗi" if stt.get(sensor) == "error" else text

        m = st.columns(6)
        m[0].metric("Nhiệt độ", val("dht", fmt(t.get("temp_dht"), 1, " °C")))
        m[1].metric("Độ ẩm", val("dht", fmt(t.get("hum"), 0, " %")))
        m[2].metric("Áp suất MSL", val("bmp", fmt(t.get("pressure_msl"), 1, " hPa")))
        m[3].metric("Ánh sáng", val("bh", fmt(t.get("lux"), 0, " lx")))
        m[4].metric("Mưa", val("rain", ["Khô", "Mưa phùn", "Mưa vừa", "Mưa to"][int(t.get("rain_level") or 0)]))
        m[5].metric("Khí gas", val("gas", fmt(t.get("gas_ppm"), 0, " ppm")), help=f"AI score {fmt(t.get('edge_score'), 2)}")
        if t.get("ts"):
            ts = pd.Timestamp(t["ts"]).tz_localize("UTC") if pd.Timestamp(t["ts"]).tzinfo is None else pd.Timestamp(t["ts"])
            st.caption(f"Cập nhật: {ts.tz_convert(TZ):%H:%M:%S %d/%m/%Y} · fw {t.get('fw')} · model {t.get('model_ver')}")
        if health:
            sensor_panel(health)
        a, b = st.columns(2)
        with a:
            st.subheader("Dự báo mới nhất")
            fc = api_get(f"/api/forecast/{device}", history_h=1) or {}
            if fc.get("latest"):
                df = pd.DataFrame(fc["latest"])
                df["Đại lượng"] = df["target"].map(TARGET_NAME)
                df["Giá trị"] = df.apply(lambda r: f"{r.value * 100:.0f} %" if r.target == "rain_prob" else f"{r.value:.1f}", axis=1)
                pv = df.pivot(index="Đại lượng", columns="horizon", values="Giá trị")
                pv.columns = [f"+{h}h" for h in pv.columns]
                st.dataframe(pv, width="stretch")
                st.caption(f"Nguồn dữ liệu: {fc.get('source')}")
            else:
                st.info("Chưa có dự báo.")
        with b:
            st.subheader("Cảnh báo gần đây")
            al = api_get("/api/alerts", device_id=device, limit=8) or []
            if al:
                df = pd.DataFrame(al)
                df["Thời gian"] = to_local(df["ts"]).dt.strftime("%H:%M:%S %d/%m")
                df["Cấp"] = df["level"].map(lambda x: f"{LEVEL[x][0]} {x}")
                df["Đã xử lý"] = df["ack_ts"].notna().map({True: "✅", False: ""})
                st.dataframe(df[["Thời gian", "Cấp", "type", "source", "gas_ppm", "Đã xử lý"]], hide_index=True,
                             width="stretch")
            else:
                st.info("Chưa có cảnh báo.")
    live()


def page_charts():
    win = st.segmented_control("Cửa sổ", list(WINDOWS), default="24 giờ") or "24 giờ"
    delta, res = WINDOWS[win]
    now = dt.datetime.now(dt.timezone.utc)
    data = api_get("/api/telemetry", device_id=device, resolution=res, **{"from": (now - delta).timestamp()})
    if not data:
        st.info("Không có dữ liệu trong cửa sổ này.")
        return
    df = pd.DataFrame(data)
    df["ts"] = to_local(df["ts"])
    cols = st.multiselect("Đại lượng", list(SERIES), default=["temp_dht", "hum", "pressure_msl", "gas_ppm"],
                          format_func=SERIES.get)
    grid = st.columns(2)
    for i, c in enumerate(cols):
        if c not in df:
            continue
        ch = alt.Chart(df).mark_line().encode(x=alt.X("ts:T", title=None),
                                               y=alt.Y(f"{c}:Q", title=SERIES[c], scale=alt.Scale(zero=False)),
                                               tooltip=["ts:T", alt.Tooltip(f"{c}:Q", format=".2f")])
        grid[i % 2].altair_chart(ch.properties(height=230), width="stretch")
    st.download_button("⬇ Tải CSV cửa sổ này", df.to_csv(index=False).encode("utf-8"), f"{device}_{res}.csv", "text/csv")
    st.link_button("⬇ Xuất CSV dữ liệu thô 24h (API)", f"{API}/api/export.csv?device_id={device}")


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


def page_forecast():
    fc = api_get(f"/api/forecast/{device}", history_h=72) or {}
    if not fc.get("history"):
        st.info("Chưa có dự báo. Backend chạy forecast mỗi 10 phút.")
    if st.button("▶ Chạy dự báo ngay"):
        if api_write("POST", f"/api/forecast/{device}/run"):
            st.rerun()
    if not fc.get("history"):
        return
    h = pd.DataFrame(fc["history"])
    h["valid_at"] = to_local(h["valid_at"])
    now = dt.datetime.now(dt.timezone.utc)
    obs = pd.DataFrame(api_get("/api/telemetry", device_id=device, resolution="1h",
                               **{"from": (now - dt.timedelta(hours=72)).timestamp()}) or [])
    if len(obs):
        obs["ts"] = to_local(obs["ts"])
    horizon = st.segmented_control("Tầm dự báo", [1, 3, 6], default=1, format_func=lambda x: f"+{x}h") or 1
    obs_col = {"temp": "temp_dht", "hum": "hum"}
    cols = st.columns(2)
    for i, tgt in enumerate(["temp", "hum"]):
        d = h[(h.target == tgt) & (h.horizon == horizon)].copy()
        if not len(d):
            continue
        d = d.sort_values("valid_at").drop_duplicates("valid_at", keep="last")
        base = alt.Chart(d).encode(x=alt.X("valid_at:T", title=None))
        band = base.mark_area(opacity=0.25, color="#ff7f0e").encode(y=alt.Y("lower:Q", scale=alt.Scale(zero=False),
                                                                             title=TARGET_NAME[tgt]), y2="upper:Q")
        line = base.mark_line(color="#ff7f0e", strokeDash=[4, 2],
                              point=alt.OverlayMarkDef(color="#ff7f0e", size=50)).encode(
            y="value:Q", tooltip=["valid_at:T", "value:Q", "lower:Q", "upper:Q"])
        ci = base.mark_rule(color="#ff7f0e", strokeWidth=2).encode(y="lower:Q", y2="upper:Q")
        layers = [band, ci, line]
        if len(obs) and obs_col[tgt] in obs:
            layers.append(alt.Chart(obs).mark_line(color="#1f77b4").encode(x="ts:T", y=f"{obs_col[tgt]}:Q"))
        cols[i].altair_chart(alt.layer(*layers).properties(height=260), width="stretch")
    st.caption("Cam nét đứt: dự báo (đầu vào là quan trắc Open-Meteo tại toạ độ trạm), vùng tô: khoảng tin cậy 95 %. "
               "Xanh: số đo tại trạm (trung bình giờ) — chỉ dùng để đối chiếu, có ý nghĩa khi trạm đặt ngoài trời.")
    err = forecast_vs_station(h, obs, obs_col)
    if len(err):
        st.subheader("Sai số dự báo so với số đo tại trạm")
        st.dataframe(err, hide_index=True, width="stretch")
        st.caption("Chỉ tính các giờ có số đo trạm (ghép giờ dự báo với trung bình giờ gần nhất, lệch ≤ 30 phút). "
                   "Chọn khoảng thời gian trạm đặt ngoài trời để đánh giá; số đo trong nhà không so được với dự báo ngoài trời.")
    r = h[h.target == "rain_prob"].sort_values("created_at").groupby("horizon").tail(1)
    st.subheader("Xác suất mưa")
    rc = st.columns(3)
    for i, (_, row) in enumerate(r.sort_values("horizon").iterrows()):
        rc[i].metric(f"Trong {row.horizon} giờ tới", f"{row.value * 100:.0f} %")


def page_alerts():
    c1, c2, c3 = st.columns(3)
    lvl = c1.multiselect("Cấp", [0, 1, 2, 3], default=[1, 2, 3], format_func=lambda x: f"{LEVEL[x][0]} {LEVEL[x][1]}")
    src = c2.selectbox("Nguồn", ["tất cả", "edge", "cloud"])
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
        tl = alt.Chart(df).mark_circle(size=90).encode(
            x=alt.X("ts_local:T", title=None, axis=alt.Axis(format="%H:%M %d/%m")), y=alt.Y("level:Q", scale=alt.Scale(domain=[0, 3]), title="Cấp"),
            color=alt.Color("source:N"), tooltip=["ts_local:T", "level", "type", "source", "gas_ppm", "cause"])
        st.altair_chart(tl.properties(height=200), width="stretch")
    for _, a in df.head(50).iterrows():
        e, nme, _ = LEVEL[int(a.level)]
        with st.container(border=True):
            c = st.columns([3, 2, 1])
            c[0].markdown(f"{e} **{nme}** · `{a.type}` · nguồn **{a.source}** · {a.ts_local:%H:%M:%S %d/%m/%Y}")
            c[1].write(f"ppm {fmt(a.gas_ppm, 0)} · {', '.join(a.cause or [])}")
            if pd.isna(a.ack_ts) and a.level > 0:
                if c[2].button("✅ Xác nhận", key=f"ack{a.id}"):
                    if api_write("POST", f"/api/alerts/{int(a.id)}/ack", json={"by": st.session_state.get("user")}):
                        st.rerun()
            elif not pd.isna(a.ack_ts):
                c[2].write(f"✅ {a.acknowledged_by}")


def page_device():
    dev = api_get(f"/api/devices/{device}") or {}
    cfg = (dev.get("config") or {}).get("config") or {}
    st.subheader(f"{dev.get('name', device)} — {dev.get('location', '')}")
    seen = to_local(pd.Series([dev["last_seen"]])).iloc[0].strftime("%H:%M:%S %d/%m/%Y") if dev.get("last_seen") else "—"
    st.caption(f"fw {dev.get('fw')} · model {dev.get('model_ver')} · lần cuối {seen} · trạng thái {dev.get('status')}")
    if dev.get("last_status"):
        with st.expander("Trạng thái chi tiết (status)"):
            st.json(dev["last_status"])
    st.markdown("#### Lệnh")
    b = st.columns(4)
    for i, (cmd, label) in enumerate([("test_alarm", "🔔 Thử còi"), ("mute", "🔇 Tắt còi 5 phút"),
                                      ("calibrate", "🎯 Hiệu chuẩn R0"), ("reboot", "🔄 Khởi động lại")]):
        if b[i].button(label, width="stretch"):
            r = api_write("POST", f"/api/devices/{device}/cmd", json={"cmd": cmd})
            if r:
                st.success(f"Đã gửi {cmd} (id {r['id'][:8]})")
    st.markdown("#### Cấu hình ngưỡng & chu kỳ")
    with st.form("cfg"):
        c = st.columns(3)
        th1 = c[0].number_input("Ngưỡng Chú ý (ppm)", 1.0, 9999.0, float(cfg.get("th1", 300)))
        th2 = c[1].number_input("Ngưỡng Cảnh báo (ppm)", 1.0, 9999.0, float(cfg.get("th2", 1000)))
        th3 = c[2].number_input("Ngưỡng Nguy hiểm (ppm)", 1.0, 9999.0, float(cfg.get("th3", 2000)))
        c = st.columns(3)
        slope1 = c[0].number_input("Độ dốc bất thường (ppm/s)", 0.1, 1000.0, float(cfg.get("slope1", 15)))
        hyst = c[1].slider("Hysteresis", 0.0, 0.45, float(cfg.get("hyst", 0.15)))
        tel = c[2].number_input("Chu kỳ telemetry (ms)", 1000, 600000, int(cfg.get("telemetry_ms", 10000)), step=1000)
        c = st.columns(3)
        dbu = c[0].number_input("Debounce tăng (mẫu)", 1, 30, int(cfg.get("debounce_up", 3)))
        dbd = c[1].number_input("Debounce giảm (mẫu)", 1, 60, int(cfg.get("debounce_down", 5)))
        modes = ["hybrid", "rule", "model"]
        mode = c[2].selectbox("Chế độ edge", modes, index=modes.index(cfg.get("mode", "hybrid")))
        if st.form_submit_button("💾 Gửi cấu hình xuống thiết bị"):
            r = api_write("PUT", f"/api/devices/{device}/config",
                          json={"th1": th1, "th2": th2, "th3": th3, "slope1": slope1, "hyst": hyst,
                                "telemetry_ms": int(tel), "debounce_up": int(dbu), "debounce_down": int(dbd),
                                "mode": mode})
            if r:
                st.success(f"Đã publish config v{r['version']} (retain). Chờ thiết bị ack.")
    hist = api_get(f"/api/devices/{device}/configs") or []
    if hist:
        h = pd.DataFrame(hist)[["version", "created_at", "created_by", "acked", "acked_at"]]
        st.dataframe(h, hide_index=True, width="stretch")
    cmds = api_get(f"/api/devices/{device}/commands") or []
    if cmds:
        st.markdown("#### Lịch sử lệnh")
        st.dataframe(pd.DataFrame(cmds)[["created_at", "cmd", "created_by", "acked", "ack_msg"]], hide_index=True,
                     width="stretch")


def page_models():
    ms = api_get("/api/models") or []
    if ms:
        df = pd.DataFrame(ms)
        act = df[df.active].sort_values("name")
        st.subheader("Mô hình đang hoạt động")
        st.dataframe(act[["name", "model", "model_ver", "metric_name", "metric_value", "created_at"]], hide_index=True,
                     width="stretch")
        with st.expander("Toàn bộ lịch sử registry"):
            st.dataframe(df[["name", "model_ver", "model", "metric_value", "active", "created_at"]], hide_index=True)
    for f, title in [("results_forecast.md", "Kết quả dự báo"), ("results_gas_edge.md", "Cảnh báo khí tại edge"),
                     ("results_anomaly.md", "Bất thường ở cloud")]:
        p = REPO / "docs" / "report" / f
        if p.exists():
            with st.expander(title):
                st.markdown(p.read_text(encoding="utf-8"))
    for img in sorted((REPO / "docs" / "report" / "figures").glob("*.png")):
        st.image(str(img), caption=img.stem)


{"Tổng quan": page_overview, "Biểu đồ": page_charts, "Dự báo": page_forecast, "Cảnh báo": page_alerts,
 "Thiết bị": page_device, "Mô hình": page_models}[page]()
