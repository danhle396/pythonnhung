from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT / "docs" / "report"
FIG = REP / "figures"
COL = {"Persistence": "#9aa5b1", "Seasonal naive": "#cbd2d9", "Holt-Winters": "#f0b429", "Ridge": "#3e7cb1",
       "GBDT": "#0b6e4f", "GRU (PyTorch)": "#c75146", "Logistic": "#3e7cb1",
       "Rule": "#9aa5b1", "Model": "#3e7cb1", "Hybrid": "#0b6e4f"}
LEVEL_COLORS = ["#2e7d32", "#f9a825", "#ef6c00", "#c62828"]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.3, "figure.dpi": 150})


def md_tables(path: Path) -> list[pd.DataFrame]:
    out, cur = [], []
    for line in path.read_text(encoding="utf-8").splitlines() + [""]:
        if line.strip().startswith("|"):
            cur.append([c.strip() for c in line.strip().strip("|").split("|")])
        elif cur:
            rows = [r for r in cur if not set("".join(r)) <= set("-: ")]
            df = pd.DataFrame(rows[1:], columns=rows[0])
            out.append(df.set_index(df.columns[0]))
            cur = []
    return out


def num(s: str) -> float:
    m = re.search(r"-?\d+(?:\.\d+)?", s.replace("*", ""))
    return float(m.group()) if m else float("nan")


def fig_forecast_mae():
    reg = md_tables(REP / "results_forecast.md")[0]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
    for ax, (tgt, unit) in zip(axes, [("temp", "°C"), ("hum", "%RH")]):
        hs = [1, 3, 6]
        models = [m for m in reg.index if m != "Seasonal naive"]
        w = 0.8 / len(models)
        for i, m in enumerate(models):
            v = [num(reg.loc[m, f"{tgt}_{h}h"]) for h in hs]
            ax.bar([j + (i - (len(models) - 1) / 2) * w for j in range(3)], v, w, label=m, color=COL[m])
        ax.set_xticks(range(3), [f"+{h}h" for h in hs])
        ax.set_title({"temp": "Nhiệt độ", "hum": "Độ ẩm"}[tgt] + f" — MAE ({unit})")
    axes[0].legend(fontsize=8, frameon=False)
    fig.suptitle("Sai số dự báo trên tập test 2025 (thấp hơn là tốt hơn)", fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIG / "forecast_mae_compare.png")
    plt.close(fig)


def fig_rain():
    t = md_tables(REP / "results_forecast.md")[1]
    fig, ax = plt.subplots(figsize=(6, 3.4))
    hs = ["rain_1h", "rain_3h", "rain_6h"]
    for i, m in enumerate(t.index):
        f1 = [num(t.loc[m, h].split("/")[0]) for h in hs]
        ax.bar([j + (i - 1) * 0.27 for j in range(3)], f1, 0.27, label=m, color=COL[m])
    ax.set_xticks(range(3), ["+1h", "+3h", "+6h"])
    ax.set_ylim(0.6, 0.9)
    ax.set_ylabel("F1")
    ax.set_title("Dự báo có mưa — F1 trên tập test 2025", fontweight="bold")
    ax.legend(frameon=False, fontsize=8, ncol=3)
    fig.tight_layout()
    fig.savefig(FIG / "rain_f1_compare.png")
    plt.close(fig)


def fig_gas_edge():
    p = REP / "results_gas_edge.md"
    if not p.exists():
        print("bỏ qua hình gas edge: chưa có results_gas_edge.md (chưa có dữ liệu khí đo thật)")
        return
    t = md_tables(p)[0]
    rows = ["Macro-F1 (theo mẫu)", "Recall cấp ≥2 (theo mẫu)", "Precision cấp ≥2 (theo mẫu)",
            "Recall cấp ≥2 (theo sự kiện)"]
    labels = ["Macro-F1", "Recall ≥2\n(mẫu)", "Precision ≥2\n(mẫu)", "Recall ≥2\n(sự kiện)"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6), gridspec_kw={"width_ratios": [2, 1]})
    for i, m in enumerate(["Rule", "Model", "Hybrid"]):
        axes[0].bar([j + (i - 1) * 0.27 for j in range(len(rows))], [num(t.loc[r, m]) for r in rows], 0.27,
                    label=m, color=COL[m])
        d = [num(t.loc["Độ trễ phát hiện cấp ≥2, trung vị (s)", m]), num(t.loc["Độ trễ phát hiện cấp ≥2, P95 (s)", m])]
        axes[1].bar([j + (i - 1) * 0.27 for j in range(2)], d, 0.27, color=COL[m], label=m)
    axes[0].set_xticks(range(len(rows)), labels)
    axes[0].set_ylim(0, 1.05)
    axes[0].legend(frameon=False, ncol=3, fontsize=8)
    axes[0].set_title("Chất lượng phân cấp cảnh báo", fontweight="bold")
    axes[1].set_xticks(range(2), ["Trung vị", "P95"])
    axes[1].set_ylabel("giây")
    axes[1].set_title("Độ trễ phát hiện cấp ≥ 2", fontweight="bold")
    fig.suptitle("Rule / Model / Hybrid tại edge — dữ liệu đo thật")
    fig.tight_layout()
    fig.savefig(FIG / "gas_edge_compare.png")
    plt.close(fig)


def fig_load():
    runs = [("20 TB\nSQLite", "results_load_20.md"), ("50 TB\nSQLite", "results_load_50.md"),
            ("50 TB\nDocker+Timescale", "results_load_50_docker.md")]
    rows = []
    for name, f in runs:
        p = REP / f
        if not p.exists():
            continue
        t = md_tables(p)[0]
        rows.append((name, num(t.loc["Độ trễ broker P50", "Giá trị"]), num(t.loc["Độ trễ broker P95", "Giá trị"]),
                     num(t.loc["Độ trễ broker P99", "Giá trị"]), num(t.loc["Mất gói (broker)", "Giá trị"])))
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    for i, (lab, c) in enumerate([("P50", "#9fb3c8"), ("P95", "#3e7cb1"), ("P99", "#102a43")]):
        ax.bar([j + (i - 1) * 0.27 for j in range(len(rows))], [r[1 + i] for r in rows], 0.27, label=lab, color=c)
    ax.set_xticks(range(len(rows)), [r[0] for r in rows])
    ax.set_ylabel("ms")
    ax.set_title("Độ trễ broker khi tải (QoS 1, 1 msg/s/thiết bị) — mất gói 0 %", fontweight="bold")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG / "load_latency.png")
    plt.close(fig)


def fig_alert_timeline(api: str, device: str, minutes: int, user: str, pw: str, start: str | None = None):
    import requests
    tok = requests.post(f"{api}/api/auth/token", data={"username": user, "password": pw}, timeout=10).json()
    h = {"Authorization": f"Bearer {tok['access_token']}"} if "access_token" in tok else {}
    t0 = (pd.Timestamp(start).to_pydatetime() if start
          else dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes))
    t1 = t0 + dt.timedelta(minutes=minutes)
    tel = pd.DataFrame(requests.get(f"{api}/api/telemetry", headers=h, timeout=20, params={
        "device_id": device, "resolution": "raw", "from": t0.timestamp(), "to": t1.timestamp()}).json())
    if not len(tel):
        print("không có telemetry trong khoảng thời gian")
        return
    tel["ts"] = pd.to_datetime(tel["ts"], utc=True, format="mixed").dt.tz_convert("Asia/Ho_Chi_Minh")
    tel = tel.sort_values("ts")
    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.plot(tel.ts, tel.gas_ppm, color="#102a43", lw=1.6, label="gas_ppm")
    for th, c, n in [(300, LEVEL_COLORS[1], "Chú ý 300"), (1000, LEVEL_COLORS[2], "Cảnh báo 1000"),
                     (2000, LEVEL_COLORS[3], "Nguy hiểm 2000")]:
        ax.axhline(th, color=c, ls="--", lw=1)
        ax.text(tel.ts.iloc[0], th, f" {n}", color=c, va="bottom", fontsize=8)
    ax.set_ylabel("ppm (MQ-2)")
    ax2 = ax.twinx()
    ax2.step(tel.ts, tel.edge_risk, where="post", color="#c62828", lw=1.4, alpha=0.8, label="cấp edge")
    ax2.set_ylim(-0.1, 3.5)
    ax2.set_yticks([0, 1, 2, 3])
    ax2.set_ylabel("cấp cảnh báo edge")
    ax2.grid(False)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M:%S", tz=tel.ts.dt.tz))
    ax.set_title(f"Diễn biến cảnh báo khí (telemetry thật trong DB) — {device}", fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIG / "alert_timeline.png")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api")
    ap.add_argument("--device", default="station01")
    ap.add_argument("--minutes", type=int, default=15)
    ap.add_argument("--start", help="mốc bắt đầu ISO (UTC), mặc định = bây giờ − minutes")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    a = ap.parse_args()
    FIG.mkdir(parents=True, exist_ok=True)
    fig_forecast_mae()
    fig_rain()
    fig_gas_edge()
    fig_load()
    if a.api:
        fig_alert_timeline(a.api, a.device, a.minutes, a.user, a.password, a.start)
    print("Đã ghi hình vào", FIG)


if __name__ == "__main__":
    main()
