from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

from .config import EXPERIMENTS_DIR, MODELS_DIR


def log_experiment(run_name: str, params: dict, metrics: dict, seed: int, duration_s: float,
                   log_dir: Path = EXPERIMENTS_DIR):
    log_dir.mkdir(parents=True, exist_ok=True)
    row = {"time": dt.datetime.now().isoformat(timespec="seconds"), "run": run_name, "seed": seed,
           "duration_s": round(duration_s, 3), "params": json.dumps(params, ensure_ascii=False, default=str),
           "metrics": json.dumps(metrics, ensure_ascii=False, default=float)}
    path = log_dir / "experiments.csv"
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)
    return row


class ModelRegistry:
    def __init__(self, path: Path = MODELS_DIR / "registry.json"):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False, default=float), encoding="utf-8")

    def active(self, name):
        return self.data.get(name, {}).get("active")

    def propose(self, name, entry: dict, force=False) -> bool:
        entry = dict(entry)
        entry.setdefault("created_at", dt.datetime.now().isoformat(timespec="seconds"))
        slot = self.data.setdefault(name, {"active": None, "history": []})
        slot["history"].append(entry)
        cur = slot["active"]
        better = (cur is None or force or cur.get("metric_name") != entry["metric_name"]
                  or (entry["metric_value"] > cur["metric_value"] if entry.get("greater_is_better")
                      else entry["metric_value"] < cur["metric_value"]))
        entry["promoted"] = bool(better)
        if better:
            slot["active"] = entry
        self.save()
        return bool(better)
