import config
from compat import isnan

W, H = 160, 128
COLS1, COLS2 = 20, 10
N_ROWS = 10

LEVEL_TXT = ("AN TOAN", "CHU Y", "CANH BAO", "NGUY HIEM")
RAIN_TXT = ("kho", "mua phun", "mua vua", "mua to")


def _f(fmt, v):
    return "--" if isnan(v) else fmt % v


def wrap(text, cols, n):
    out = []
    p = text.strip()
    for _ in range(n):
        if len(p) <= cols:
            out.append(p)
            p = ""
        else:
            k = p.rfind(" ", cols // 2, cols + 1)
            k = cols if k < 0 else k
            out.append(p[:k])
            p = p[k:].strip()
    return out


def compose_rows(st, page, clock, colors):
    C = colors
    lv = st.level & 3
    level_bg = (C["DARKGREEN"], C["YELLOW"], C["ORANGE"], C["RED"])
    level_fg = (C["WHITE"], C["BLACK"], C["BLACK"], C["WHITE"])
    hbg = C["GREY"] if st.warming_up else level_bg[lv]
    hfg = C["WHITE"] if st.warming_up else level_fg[lv]
    s = st.s
    rows = [None] * N_ROWS
    titles = ("MOI TRUONG", "KHI GAS / KHOI", "DU BAO")
    flags = ("W" if st.wifi else "-") + ("M" if st.mqtt else "-") + (" x" if st.muted else "  ")
    rows[0] = (3, 1, hfg, hbg, "%-16s%s" % (titles[page], flags))
    if page == 0:
        rows[1] = (18, 2, C["ORANGE"], C["BLACK"], "T " + _f("%5.1f", s.temp) + " C")
        rows[2] = (36, 2, C["CYAN"], C["BLACK"], "H " + _f("%5.0f", s.hum) + " %")
        rows[3] = (58, 1, C["WHITE"], C["BLACK"], "Ap suat " + _f("%7.1f", s.pressure_msl) + "hPa")
        rows[4] = (70, 1, C["WHITE"], C["BLACK"], "Anh sang " + _f("%6.0f", s.lux) + "lx")
        rows[5] = (82, 1, C["WHITE"], C["BLACK"], "Mua %s %dmV" % (RAIN_TXT[s.rain_level & 3], s.rain_mv))
        rows[6] = (94, 1, C["WHITE"], C["BLACK"], "Diem suong " + _f("%5.1f", s.dew) + " C")
        rows[7] = (106, 1, C["WHITE"], C["BLACK"], "Chi so nhiet" + _f("%5.1f", s.heat_index) + " C")
    elif page == 1:
        txt = "LAM NONG.." if st.warming_up else LEVEL_TXT[lv]
        pad = (COLS2 - len(txt)) // 2
        rows[1] = (20, 2, hfg, hbg, " " * pad + txt)
        rows[2] = (42, 2, C["WHITE"], C["BLACK"], _f("%6.0f", s.mq2.ppm) + " ppm")
        rows[3] = (64, 1, C["WHITE"], C["BLACK"], "Rs/R0       %.2f" % s.mq2.ratio)
        rows[4] = (76, 1, C["WHITE"], C["BLACK"], "AI score    %.2f" % st.score)
        if st.muted:
            rows[5] = (88, 1, C["YELLOW"], C["BLACK"], "Coi: DA TAT 5 phut")
        else:
            rows[5] = (88, 1, C["WHITE"], C["BLACK"], "Coi: san sang")
        if s.gas_fault:
            rows[6] = (100, 1, C["RED"], C["BLACK"], "LOI MQ-2 (ma %d)" % s.gas_fault)
        else:
            rows[6] = (100, 1, C["WHITE"], C["BLACK"], "")
    else:
        rows[1] = (20, 1, C["CYAN"], C["BLACK"], "Cloud (AI du bao)")
        for i, line in enumerate(wrap(st.cloud_forecast or "(chua co)", COLS1, 6)):
            rows[2 + i] = (34 + 12 * i, 1, C["WHITE"], C["BLACK"], line)
    rows[N_ROWS - 1] = (H - 10, 1, C["GREY"], C["BLACK"], "%-5s fw %-6s %d/3" % (clock, config.FW_VERSION, page + 1))
    return rows


class Display:
    def __init__(self, tft):
        import st7735
        self.tft = tft
        self.colors = {k: getattr(st7735, k) for k in
                       ("BLACK", "WHITE", "RED", "DARKGREEN", "YELLOW", "ORANGE", "CYAN", "GREY")}
        self.page = 0
        self.shown = -1
        self.last_flip = None
        self.rows = [None] * N_ROWS
        C = self.colors
        tft.fill(C["BLACK"])
        tft.text_row("VKU AIoT Station", 3, 1, C["WHITE"], C["DARKGREEN"])
        tft.text_row("Tram AIoT", 40, 2, C["WHITE"], C["BLACK"])
        tft.text_row("15.975N 108.253E", 66, 1, C["WHITE"], C["BLACK"])
        tft.text_row("fw " + config.FW_VERSION, 80, 1, C["WHITE"], C["BLACK"])
        tft.text_row("Dang khoi dong...", 100, 1, C["GREY"], C["BLACK"])

    def render(self, st, now, clock):
        from compat import ticks_diff
        if self.last_flip is None or ticks_diff(now, self.last_flip) > 4000:
            self.page = (self.page + 1) % 3 if self.last_flip is not None else 0
            self.last_flip = now
        page = 1 if st.level >= 2 else self.page
        if page != self.shown:
            self.tft.fill(self.colors["BLACK"])
            self.rows = [None] * N_ROWS
            self.shown = page
        for i, r in enumerate(compose_rows(st, page, clock, self.colors)):
            if r == self.rows[i]:
                continue
            if r is None:
                old = self.rows[i]
                self.tft.fill_rect(0, old[0], W, 8 * old[1], self.colors["BLACK"])
            else:
                y, size, fg, bg, text = r
                old = self.rows[i]
                if old is not None and (old[0] != y or old[1] != size):
                    self.tft.fill_rect(0, old[0], W, 8 * old[1], self.colors["BLACK"])
                self.tft.text_row(text, y, size, fg, bg)
            self.rows[i] = r
