"""REST API (task.md 7.5). Đọc: công khai cho dashboard. Ghi: cần JWT (POST /api/auth/token)."""
from __future__ import annotations

import datetime as dt
import io
import json
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import authenticate, create_token, require_user
from app.db.models import Alert, Command, Device, DeviceConfig, Forecast, ModelRegistryEntry, Nowcast, Telemetry
from app.db.session import as_utc, get_db
from app.runtime import rt
from app.schemas.payloads import AckRequest, CommandIn, DeviceConfigIn

router = APIRouter(prefix="/api")
RES = {"1m": "1min", "10m": "10min", "1h": "1h", "1d": "1D"}
NUMERIC = ["temp_dht", "hum", "temp_bmp", "pressure", "pressure_msl", "lux", "dew_point", "heat_index", "rain_raw",
           "rain_level", "gas_raw", "gas_rs_r0", "gas_ppm", "gas_slope", "edge_risk", "edge_score"]


def _row(o):
    return {c.name: getattr(o, c.name) for c in o.__table__.columns}


def _parse_time(v: str | None, default: dt.datetime) -> dt.datetime:
    if not v:
        return default
    try:
        return dt.datetime.fromtimestamp(float(v), tz=dt.timezone.utc)
    except ValueError:
        t = pd.Timestamp(v)
        return (t.tz_localize("UTC") if t.tzinfo is None else t).to_pydatetime()


# ------------------------------------------------------------------ auth & health
@router.post("/auth/token", tags=["auth"])
def login(form: OAuth2PasswordRequestForm = Depends()):
    if not authenticate(form.username, form.password):
        raise HTTPException(401, "Sai tài khoản hoặc mật khẩu")
    return {"access_token": create_token(form.username), "token_type": "bearer"}


@router.get("/health", tags=["system"])
def health(db: Session = Depends(get_db)):
    r = rt()
    n = db.scalar(select(func.count()).select_from(Device))
    return {"status": "ok", "devices": n, "mqtt": getattr(r.mqtt, "stats", None),
            "telegram": r.notifier.telegram_enabled, "last_forecast": (r.forecast.last_run or {}).get("ts")}


# ------------------------------------------------------------------ devices
@router.get("/devices", tags=["devices"])
def list_devices(db: Session = Depends(get_db)):
    return [_row(d) for d in db.scalars(select(Device).order_by(Device.id))]


@router.get("/devices/{device_id}", tags=["devices"])
def get_device(device_id: str, db: Session = Depends(get_db)):
    d = db.get(Device, device_id)
    if d is None:
        raise HTTPException(404, "Không có thiết bị")
    cfg = db.scalars(select(DeviceConfig).where(DeviceConfig.device_id == device_id)
                     .order_by(DeviceConfig.version.desc())).first()
    return {**_row(d), "config": _row(cfg) if cfg else None}


@router.put("/devices/{device_id}/config", tags=["devices"])
def put_config(device_id: str, body: DeviceConfigIn, db: Session = Depends(get_db), user: str = Depends(require_user)):
    prev = db.scalars(select(DeviceConfig).where(DeviceConfig.device_id == device_id)
                      .order_by(DeviceConfig.version.desc())).first()
    merged = {**(prev.config if prev else {}), **body.model_dump(exclude_none=True)}
    th = [merged.get(k) for k in ("th1", "th2", "th3")]
    if all(t is not None for t in th) and not th[0] < th[1] < th[2]:
        raise HTTPException(422, "cần th1 < th2 < th3")
    version = (prev.version if prev else 0) + 1
    merged["version"] = version
    cfg = DeviceConfig(device_id=device_id, version=version, config=merged, created_by=user)
    db.add(cfg)
    db.commit()
    rt().publisher.config(device_id, merged)
    return _row(cfg)


@router.get("/devices/{device_id}/configs", tags=["devices"])
def config_history(device_id: str, db: Session = Depends(get_db)):
    return [_row(c) for c in db.scalars(select(DeviceConfig).where(DeviceConfig.device_id == device_id)
                                        .order_by(DeviceConfig.version.desc()).limit(50))]


@router.post("/devices/{device_id}/cmd", tags=["devices"])
def send_cmd(device_id: str, body: CommandIn, db: Session = Depends(get_db), user: str = Depends(require_user)):
    kw = {"level": body.level} if body.cmd == "escalate" else {}
    cid = rt().publisher.cmd(device_id, body.cmd, **kw)
    db.add(Command(id=cid, device_id=device_id, cmd=body.cmd, payload=kw or None, created_by=user))
    db.commit()
    return {"id": cid, "device_id": device_id, "cmd": body.cmd}


@router.get("/devices/{device_id}/commands", tags=["devices"])
def list_commands(device_id: str, db: Session = Depends(get_db)):
    return [_row(c) for c in db.scalars(select(Command).where(Command.device_id == device_id)
                                        .order_by(Command.created_at.desc()).limit(50))]


# ------------------------------------------------------------------ telemetry
def _telemetry_df(db, device_id, t_from, t_to):
    q = select(Telemetry).where(Telemetry.device_id == device_id, Telemetry.ts >= t_from, Telemetry.ts <= t_to) \
        .order_by(Telemetry.ts)
    rows = [_row(r) for r in db.scalars(q)]
    df = pd.DataFrame(rows)
    if len(df):
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


@router.get("/telemetry", tags=["telemetry"])
def telemetry(device_id: str = Query(None), from_: str | None = Query(None, alias="from"), to: str | None = None,
              resolution: str = Query("raw", pattern="^(raw|1m|10m|1h|1d)$"), limit: int = Query(20000, le=200000),
              db: Session = Depends(get_db)):
    device_id = device_id or rt().settings.default_device_id
    now = dt.datetime.now(dt.timezone.utc)
    t_to = _parse_time(to, now)
    t_from = _parse_time(from_, t_to - dt.timedelta(hours=1))
    df = _telemetry_df(db, device_id, t_from, t_to)
    if not len(df):
        return []
    if resolution != "raw":
        df = df.set_index("ts")[[c for c in NUMERIC if c in df]].astype(float) \
            .resample(RES[resolution]).mean().dropna(how="all").reset_index()
    df = df.tail(limit)
    df["ts"] = df["ts"].map(lambda t: t.isoformat())
    return json.loads(df.drop(columns=["extra"], errors="ignore").to_json(orient="records", date_format="iso"))


@router.get("/telemetry/latest", tags=["telemetry"])
def telemetry_latest(device_id: str | None = None, db: Session = Depends(get_db)):
    q = select(Telemetry).order_by(Telemetry.ts.desc())
    if device_id:
        q = q.where(Telemetry.device_id == device_id)
        r = db.scalars(q).first()
        return _row(r) if r else None
    out = {}
    for d in db.scalars(select(Device)):
        r = db.scalars(q.where(Telemetry.device_id == d.id)).first()
        if r:
            out[d.id] = _row(r)
    return out


@router.get("/export.csv", tags=["telemetry"])
def export_csv(device_id: str | None = None, from_: str | None = Query(None, alias="from"), to: str | None = None,
               db: Session = Depends(get_db)):
    device_id = device_id or rt().settings.default_device_id
    now = dt.datetime.now(dt.timezone.utc)
    t_to = _parse_time(to, now)
    t_from = _parse_time(from_, t_to - dt.timedelta(days=1))
    df = _telemetry_df(db, device_id, t_from, t_to)
    buf = io.StringIO()
    df.drop(columns=["extra"], errors="ignore").to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={device_id}_telemetry.csv"})


# ------------------------------------------------------------------ alerts
@router.get("/alerts", tags=["alerts"])
def list_alerts(device_id: str | None = None, level: int | None = Query(None, ge=0, le=3),
                min_level: int | None = Query(None, ge=0, le=3), source: str | None = None,
                from_: str | None = Query(None, alias="from"), to: str | None = None,
                unacked: bool = False, limit: int = Query(200, le=5000), db: Session = Depends(get_db)):
    q = select(Alert)
    if device_id:
        q = q.where(Alert.device_id == device_id)
    if level is not None:
        q = q.where(Alert.level == level)
    if min_level is not None:
        q = q.where(Alert.level >= min_level)
    if source:
        q = q.where(Alert.source == source)
    if from_:
        q = q.where(Alert.ts >= _parse_time(from_, None))
    if to:
        q = q.where(Alert.ts <= _parse_time(to, None))
    if unacked:
        q = q.where(Alert.ack_ts.is_(None))
    return [_row(a) for a in db.scalars(q.order_by(Alert.ts.desc(), Alert.id.desc()).limit(limit))]


@router.post("/alerts/{alert_id}/ack", tags=["alerts"])
def ack_alert(alert_id: int, body: AckRequest | None = None, user: str = Depends(require_user)):
    if not rt().alerts.ack(alert_id, (body.by if body and body.by else user)):
        raise HTTPException(404, "Không có cảnh báo")
    return {"ok": True, "alert_id": alert_id}


# ------------------------------------------------------------------ forecast & nowcast
@router.get("/forecast/{device_id}", tags=["forecast"])
def get_forecast(device_id: str, history_h: int = Query(48, le=24 * 30), db: Session = Depends(get_db)):
    latest = db.scalars(select(Forecast).where(Forecast.device_id == device_id)
                        .order_by(Forecast.created_at.desc())).first()
    if latest is None:
        return {"latest": [], "history": []}
    batch = db.scalars(select(Forecast).where(Forecast.device_id == device_id,
                                              Forecast.created_at == latest.created_at)).all()
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=history_h)
    hist = db.scalars(select(Forecast).where(Forecast.device_id == device_id, Forecast.created_at >= since)
                      .order_by(Forecast.created_at)).all()
    out_hist = []
    for f in hist:
        r = _row(f)
        r["valid_at"] = (as_utc(f.issued_for) + dt.timedelta(hours=f.horizon)).isoformat()
        out_hist.append(r)
    return {"latest": [_row(f) for f in batch], "issued_for": latest.issued_for, "source": latest.source,
            "history": out_hist}


@router.post("/forecast/{device_id}/run", tags=["forecast"])
def run_forecast(device_id: str, user: str = Depends(require_user)):
    return rt().forecast.run_once(device_id)


@router.get("/nowcast/{device_id}", tags=["forecast"])
def get_nowcast(device_id: str, limit: int = 50, db: Session = Depends(get_db)):
    return [_row(n) for n in db.scalars(select(Nowcast).where(Nowcast.device_id == device_id)
                                        .order_by(Nowcast.ts.desc()).limit(limit))]


# ------------------------------------------------------------------ models
@router.get("/models", tags=["models"])
def models(db: Session = Depends(get_db)):
    rows = db.scalars(select(ModelRegistryEntry).order_by(ModelRegistryEntry.name,
                                                          ModelRegistryEntry.created_at.desc())).all()
    return [_row(r) for r in rows]


def sync_registry(db: Session, path: str):
    """Đồng bộ ml/models/registry.json vào bảng model_registry."""
    p = Path(path)
    if not p.exists():
        return 0
    reg = json.loads(p.read_text(encoding="utf-8"))
    n = 0
    for name, slot in reg.items():
        active_ver = (slot.get("active") or {}).get("model_ver")
        for e in slot.get("history", []):
            row = db.scalars(select(ModelRegistryEntry).where(ModelRegistryEntry.name == name,
                                                              ModelRegistryEntry.model_ver == e["model_ver"])).first()
            if row is None:
                row = ModelRegistryEntry(name=name, model_ver=e["model_ver"])
                db.add(row)
                n += 1
            row.model, row.path = e.get("model"), e.get("path")
            row.metric_name, row.metric_value = e.get("metric_name"), e.get("metric_value")
            row.metrics = {k: v for k, v in e.items() if k not in ("model_ver", "path", "model")}
            row.active = e["model_ver"] == active_ver
    db.commit()
    return n
