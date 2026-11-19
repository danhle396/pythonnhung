"""Giao diện dashboard theo phong cách bản giữa kỳ (mid): thanh trên cùng, thẻ số đo có viền màu, panel bo góc.

Chỉ có CSS và HTML tĩnh (không JavaScript); màu nền/chữ của widget lấy từ `.streamlit/config.toml`.
"""
from __future__ import annotations

import html

import altair as alt

COLORS = {"temp": "#e8590c", "hum": "#1c7ed6", "pressure": "#7048e8", "light": "#d4a106", "rain": "#0c8599",
          "gas": "#c2255c", "forecast": "#2563eb", "observed": "#6b7686"}
LEVEL_COLORS = {0: "#16a34a", 1: "#d97706", 2: "#ea580c", 3: "#dc2626"}

CSS = """
<style>
:root {
  --bg: #f4f6f9; --surface: #ffffff; --border: #e3e7ee; --text: #1c2430; --muted: #6b7686;
  --accent: #2563eb; --ok: #16a34a; --bad: #dc2626; --warn: #d97706; --alert-bg: #fef2f2;
  --radius: 12px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f141b; --surface: #171e27; --border: #263040; --text: #e6ebf2; --muted: #8e9aab;
    --accent: #5b8def; --alert-bg: #3a1a1d;
  }
}
/* khung trang */
header[data-testid="stHeader"] { background: transparent; height: 2.5rem; }
[data-testid="stAppDeployButton"], [data-testid="stDecoration"] { display: none; }
[data-testid="stMainBlockContainer"] { max-width: 1280px; padding: 0 16px 2rem !important; }
.stMain { overflow-x: hidden; }
h1, h2, h3 { font-weight: 600 !important; }

/* thanh trên cùng */
.topbar {
  display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between;
  background: var(--surface); border-bottom: 1px solid var(--border);
  margin: 0 calc(50% - 50vw) 4px; padding: 12px max(16px, calc(50vw - 624px));
}
.brand { display: flex; gap: 12px; align-items: center; }
.brand .logo { font-size: 1.8rem; color: var(--accent); line-height: 1; }
.brand h1 { font-size: 1.15rem; margin: 0; padding: 0; }
.brand p { margin: 0; font-size: .78rem; color: var(--muted); }
.topbar-right { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.pill {
  display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 999px;
  font-size: .82rem; border: 1px solid var(--border); background: var(--surface); color: var(--text);
}
.pill i { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); display: inline-block; }
.pill.ok i { background: var(--ok); box-shadow: 0 0 0 3px color-mix(in srgb, var(--ok) 25%, transparent); }
.pill.ok b { color: var(--ok); }
.pill.bad i { background: var(--bad); }
.pill.bad b { color: var(--bad); }
.pill.warn i { background: var(--warn); }
.pill.warn b { color: var(--warn); }

/* điều hướng: radio hiển thị như nút phân đoạn */
.st-key-nav [role="radiogroup"] {
  display: inline-flex; flex-wrap: wrap; gap: 0; background: var(--surface);
  border: 1px solid var(--border); border-radius: 10px; padding: 3px;
}
.st-key-nav [data-testid="stRadioOption"] { margin: 0 !important; padding: 6px 14px; border-radius: 7px; cursor: pointer; }
.st-key-nav [data-testid="stRadioOption"] > div > div:not([data-testid="stMarkdownContainer"]) { display: none; }
.st-key-nav [data-testid="stRadioOption"] p { color: var(--muted); font-size: .92rem; }
.st-key-nav [data-testid="stRadioOption"][data-selected="true"] { background: var(--accent); }
.st-key-nav [data-testid="stRadioOption"][data-selected="true"] p { color: #fff; }

/* nút phân đoạn (segmented_control) */
[data-testid="stButtonGroup"] [role="radiogroup"] {
  background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 3px; gap: 0;
}
button[data-variant="segmented_control"] {
  border: 0 !important; background: transparent !important; border-radius: 7px !important; box-shadow: none !important;
}
button[data-variant="segmented_control"] p { color: var(--muted); }
button[data-variant="segmented_control"][aria-checked="true"] { background: var(--accent) !important; }
button[data-variant="segmented_control"][aria-checked="true"] p { color: #fff !important; }

/* panel */
[class*="st-key-panel"] {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px;
}
.panel-title { font-weight: 600; font-size: 1rem; margin: 0 0 .5rem; }
.panel-title span { color: var(--muted); font-weight: 400; font-size: .85rem; }
.note { color: var(--muted); font-size: .8rem; margin: .4rem 0 0; }

/* thanh thông tin */
.info-bar {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 10px 16px;
}
.info-bar div { display: flex; flex-direction: column; }
.info-bar span { font-size: .75rem; color: var(--muted); }
.info-bar b { font-weight: 600; font-variant-numeric: tabular-nums; }

/* trạng thái khí */
.status {
  display: flex; align-items: center; gap: 14px; border-radius: var(--radius); padding: 14px 18px;
  background: color-mix(in srgb, var(--c) 12%, var(--surface)); border: 1px solid var(--c);
}
.status .dot { width: 14px; height: 14px; border-radius: 50%; background: var(--c); flex: none;
  box-shadow: 0 0 0 5px color-mix(in srgb, var(--c) 25%, transparent); }
.status .txt { font-size: 1.15rem; }
.status .txt small { color: var(--muted); font-size: .85rem; }

/* thẻ số đo */
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 16px; }
.card {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 14px 16px; border-top: 4px solid var(--c);
}
.card h3 { margin: 0 !important; padding: 0 !important; font-size: .8rem !important; color: var(--muted);
  font-weight: 500 !important; text-transform: uppercase; letter-spacing: .04em; }
.card .value { margin: .35rem 0 .15rem; font-size: 2rem; font-weight: 650; font-variant-numeric: tabular-nums;
  line-height: 1.1; }
.card .value small { font-size: .9rem; font-weight: 500; color: var(--muted); margin-left: 4px; }
.card .sub { margin: 0; font-size: .8rem; color: var(--muted); }
.card.alert { background: var(--alert-bg); border-color: var(--bad); border-top-color: var(--bad); }
.card.alert .value { color: var(--bad); }

/* bảng, danh sách */
.tbl-wrap { overflow-x: auto; }
table.tbl { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; font-size: .9rem; }
table.tbl th, table.tbl td { text-align: right; padding: 6px 8px; border-bottom: 1px solid var(--border);
  white-space: nowrap; }
table.tbl th:first-child, table.tbl td:first-child { text-align: left; }
table.tbl th { color: var(--muted); font-weight: 500; font-size: .8rem; }
.sensor { display: flex; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border); }
.sensor:last-child { border-bottom: 0; }
.sensor i { width: 9px; height: 9px; border-radius: 50%; margin-top: 6px; flex: none; background: var(--c); }
.sensor { font-size: .88rem; }
.sensor b { font-weight: 600; }
.sensor small { color: var(--muted); display: block; font-size: .78rem; }
.alert-row { padding: 8px 0; border-bottom: 1px solid var(--border); font-size: .88rem; }
.alert-row time { display: block; font-size: .75rem; color: var(--muted); }
.lvl { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: .75rem; font-weight: 600;
  color: #fff; background: var(--c); margin-right: 6px; }
.empty { color: var(--muted); font-size: .9rem; padding: 6px 0; }
</style>
"""


def _vega_theme() -> alt.theme.ThemeConfig:
    muted = "#8a94a3"
    return alt.theme.ThemeConfig({"config": {
        "background": "transparent", "font": "system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
        "view": {"stroke": "transparent"},
        "axis": {"labelColor": muted, "titleColor": muted, "gridColor": "rgba(127,127,127,0.16)", "domain": False,
                 "tickColor": "transparent", "labelFontSize": 11, "titleFontWeight": 500, "titleFontSize": 11},
        "legend": {"labelColor": muted, "titleColor": muted, "orient": "bottom"},
    }})


alt.theme.register("vku_dashboard", enable=True)(_vega_theme)


def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def pill(label: str, kind: str = "") -> str:
    return f"<span class='pill {kind}'><i></i><b>{esc(label)}</b></span>"


def topbar(subtitle: str, pills: list[str]) -> str:
    return (f"<header class='topbar'><div class='brand'><span class='logo'>◐</span><div>"
            f"<h1>Trạm AIoT giám sát môi trường</h1><p>{esc(subtitle)}</p></div></div>"
            f"<div class='topbar-right'>{''.join(pills)}</div></header>")


def info_bar(items: list[tuple[str, str]]) -> str:
    return "<section class='info-bar'>" + "".join(
        f"<div><span>{esc(k)}</span><b>{esc(v)}</b></div>" for k, v in items) + "</section>"


def card(title: str, value: str, unit: str, sub: str, color: str, alert: bool = False) -> str:
    unit_html = f"<small>{esc(unit)}</small>" if unit else ""
    return (f"<article class='card{' alert' if alert else ''}' style='--c:{color}'><h3>{esc(title)}</h3>"
            f"<p class='value'>{esc(value)}{unit_html}</p><p class='sub'>{esc(sub)}</p></article>")


def cards(items: list[str]) -> str:
    return "<section class='cards'>" + "".join(items) + "</section>"


def status(text_html: str, color: str) -> str:
    return f"<div class='status' style='--c:{color}'><span class='dot'></span><div class='txt'>{text_html}</div></div>"


def title(text: str, extra: str = "") -> str:
    return f"<p class='panel-title'>{esc(text)}{f' <span>{esc(extra)}</span>' if extra else ''}</p>"


def level_badge(level: int, name: str) -> str:
    return f"<span class='lvl' style='--c:{LEVEL_COLORS.get(int(level), '#6b7686')}'>{int(level)} · {esc(name)}</span>"


def table(df, raw_html_cols: tuple = ()) -> str:
    head = "".join(f"<th>{esc(c)}</th>" for c in df.columns)
    rows = []
    for _, r in df.iterrows():
        cells = "".join(f"<td>{r[c] if c in raw_html_cols else esc(r[c])}</td>" for c in df.columns)
        rows.append(f"<tr>{cells}</tr>")
    return f"<div class='tbl-wrap'><table class='tbl'><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"


def line_chart(df, x: str, y: str, color: str, height: int = 220, x_format: str = "%H:%M"):
    s = df[y].dropna()
    lo, hi = (float(s.min()), float(s.max())) if len(s) else (0.0, 1.0)
    pad = (hi - lo) * 0.1 or max(abs(hi) * 0.01, 0.5)
    lo, hi = lo - pad, hi + pad
    base = alt.Chart(df).encode(x=alt.X(f"{x}:T", title=None, axis=alt.Axis(format=x_format, labelOverlap=True,
                                                                             grid=False)))
    scale = alt.Scale(domain=[lo, hi], nice=False)
    area = base.mark_area(color=color, opacity=0.13).encode(
        y=alt.Y(f"{y}:Q", title=None, scale=scale, axis=alt.Axis(format="~g",
                                                                tickCount=5)), y2=alt.datum(lo))
    line = base.mark_line(color=color, strokeWidth=2).encode(
        y=f"{y}:Q", tooltip=[alt.Tooltip(f"{x}:T", title="Thời gian", format="%H:%M %d/%m"),
                             alt.Tooltip(f"{y}:Q", title="Giá trị", format=".2f")])
    return alt.layer(area, line).properties(height=height)
