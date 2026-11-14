import json
import os

import config
from alert import RuleConfig
from compat import allocate_lock


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


class DeviceConfig:
    def __init__(self):
        self.rule = RuleConfig(config.DEF_TH1_PPM, config.DEF_TH2_PPM, config.DEF_TH3_PPM, config.DEF_SLOPE1,
                               config.DEF_DTEMP3, config.DEF_HYST, config.DEF_DEBOUNCE_UP, config.DEF_DEBOUNCE_DOWN)
        self.r0_kohm = config.MQ2_R0_DEFAULT_KOHM
        self.telemetry_ms = config.TELEMETRY_PERIOD_MS
        self.edge_mode = 2
        self.version = 0

    def copy(self):
        c = DeviceConfig()
        c.rule = self.rule.copy()
        c.r0_kohm, c.telemetry_ms, c.edge_mode, c.version = self.r0_kohm, self.telemetry_ms, self.edge_mode, self.version
        return c

    def to_dict(self):
        r = self.rule
        return {"th1": r.th1, "th2": r.th2, "th3": r.th3, "slope1": r.slope1, "dtemp3": r.dtemp3, "hyst": r.hyst,
                "debounce_up": r.debounce_up, "debounce_down": r.debounce_down, "r0_kohm": self.r0_kohm,
                "telemetry_ms": self.telemetry_ms, "edge_mode": self.edge_mode, "version": self.version}

    def update_from(self, d):
        r = self.rule
        r.th1 = float(d.get("th1", r.th1))
        r.th2 = float(d.get("th2", r.th2))
        r.th3 = float(d.get("th3", r.th3))
        r.slope1 = float(d.get("slope1", r.slope1))
        r.dtemp3 = float(d.get("dtemp3", r.dtemp3))
        r.hyst = float(d.get("hyst", r.hyst))
        r.debounce_up = int(d.get("debounce_up", r.debounce_up))
        r.debounce_down = int(d.get("debounce_down", r.debounce_down))
        self.r0_kohm = float(d.get("r0_kohm", self.r0_kohm))
        self.telemetry_ms = int(d.get("telemetry_ms", self.telemetry_ms))
        self.edge_mode = int(d.get("edge_mode", self.edge_mode))
        self.version = int(d.get("version", self.version))

    def valid(self):
        r = self.rule
        return (0 < r.th1 < r.th2 < r.th3 < 10000 and 0 <= r.hyst < 0.5 and 1 <= r.debounce_up <= 30
                and 1 <= r.debounce_down <= 60 and 1000 <= self.telemetry_ms <= 600000
                and 0.1 < self.r0_kohm < 1000 and self.edge_mode in (0, 1, 2))


class Storage:
    SEQ_BLOCK = 100

    def __init__(self, base="", max_records=config.OFFLINE_MAX_RECORDS):
        self.base = base
        self.f_old = base + "/offline_a.jsonl"
        self.f_cur = base + "/offline_b.jsonl"
        self.half = max_records // 2
        self.lock = allocate_lock()
        self.seq_lock = allocate_lock()
        self.count_old = self._count_lines(self.f_old)
        self.count_cur = self._count_lines(self.f_cur)
        self._seq = 0
        self._reserved = 0

    @staticmethod
    def _count_lines(path):
        if not _exists(path):
            return 0
        n = 0
        with open(path) as f:
            for line in f:
                if line.strip():
                    n += 1
        return n

    def pending(self):
        return self.count_old + self.count_cur

    def append(self, topic, payload):
        with self.lock:
            try:
                if self.count_cur >= self.half:
                    _remove(self.f_old)
                    os.rename(self.f_cur, self.f_old)
                    self.count_old, self.count_cur = self.count_cur, 0
                with open(self.f_cur, "a") as f:
                    f.write(topic + "\t" + payload + "\n")
                self.count_cur += 1
                return True
            except OSError:
                return False

    def replay(self, send, max_records=200):
        sent = 0
        with self.lock:
            for i, path in enumerate((self.f_old, self.f_cur)):
                if sent >= max_records:
                    break
                if not _exists(path):
                    continue
                tmp = path + ".tmp"
                remain = 0
                stop = False
                with open(path) as src, open(tmp, "w") as dst:
                    for line in src:
                        line = line.rstrip("\n")
                        if not line:
                            continue
                        if not stop and sent < max_records:
                            tab = line.find("\t")
                            if tab < 0:
                                continue
                            if send(line[:tab], line[tab + 1:]):
                                sent += 1
                                continue
                            stop = True
                        dst.write(line + "\n")
                        remain += 1
                _remove(path)
                if remain:
                    os.rename(tmp, path)
                else:
                    _remove(tmp)
                if i == 0:
                    self.count_old = remain
                else:
                    self.count_cur = remain
                if stop:
                    break
        return sent

    def _read_json(self, name, default):
        try:
            with open(self.base + name) as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    def _write_json(self, name, obj):
        tmp = self.base + name + ".tmp"
        with open(tmp, "w") as f:
            json.dump(obj, f)
        _remove(self.base + name)
        os.rename(tmp, self.base + name)

    def load_config(self):
        c = DeviceConfig()
        d = self._read_json("/config.json", None)
        if d:
            try:
                c.update_from(d)
            except (TypeError, ValueError):
                c = DeviceConfig()
        return c

    def save_config(self, c):
        self._write_json("/config.json", c.to_dict())

    def next_seq(self):
        with self.seq_lock:
            if self._seq >= self._reserved:
                try:
                    with open(self.base + "/seq.txt") as f:
                        self._seq = int(f.read().strip() or 0)
                except (OSError, ValueError):
                    self._seq = 0
                self._reserved = self._seq + self.SEQ_BLOCK
                with open(self.base + "/seq.txt", "w") as f:
                    f.write(str(self._reserved))
            self._seq += 1
            return self._seq
