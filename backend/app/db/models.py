"""Mô hình CSDL (SQLAlchemy 2). Chạy được trên PostgreSQL/TimescaleDB (production) và SQLite (dev/test)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(128))
    location: Mapped[str | None] = mapped_column(String(256))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    altitude: Mapped[float | None] = mapped_column(Float)
    fw: Mapped[str | None] = mapped_column(String(32))
    model_ver: Mapped[str | None] = mapped_column(String(64))
    last_seen: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="unknown")
    rssi: Mapped[int | None] = mapped_column(Integer)
    last_status: Mapped[dict | None] = mapped_column(JSON)


class Telemetry(Base):
    """Hypertable theo ts trên TimescaleDB. Khoá (device_id, ts, seq) đồng thời dùng để chống trùng."""
    __tablename__ = "telemetry"
    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    temp_dht: Mapped[float | None] = mapped_column(Float)
    hum: Mapped[float | None] = mapped_column(Float)
    temp_bmp: Mapped[float | None] = mapped_column(Float)
    pressure: Mapped[float | None] = mapped_column(Float)
    pressure_msl: Mapped[float | None] = mapped_column(Float)
    lux: Mapped[float | None] = mapped_column(Float)
    dew_point: Mapped[float | None] = mapped_column(Float)
    heat_index: Mapped[float | None] = mapped_column(Float)
    rain_raw: Mapped[int | None] = mapped_column(Integer)
    rain_level: Mapped[int | None] = mapped_column(Integer)
    gas_raw: Mapped[float | None] = mapped_column(Float)
    gas_rs_r0: Mapped[float | None] = mapped_column(Float)
    gas_ppm: Mapped[float | None] = mapped_column(Float)
    gas_slope: Mapped[float | None] = mapped_column(Float)
    edge_risk: Mapped[int | None] = mapped_column(Integer)
    edge_score: Mapped[float | None] = mapped_column(Float)
    fw: Mapped[str | None] = mapped_column(String(32))
    model_ver: Mapped[str | None] = mapped_column(String(64))
    received_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    extra: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (Index("ix_telemetry_device_ts", "device_id", "ts"),)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    seq: Mapped[int | None] = mapped_column(BigInteger)
    type: Mapped[str] = mapped_column(String(32), default="gas")  # gas | sensor_fault | device_offline | anomaly | test
    level: Mapped[int] = mapped_column(Integer)
    prev_level: Mapped[int | None] = mapped_column(Integer)
    cause: Mapped[list | None] = mapped_column(JSON)
    gas_ppm: Mapped[float | None] = mapped_column(Float)
    score: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(8), default="edge")  # edge | cloud
    message: Mapped[str | None] = mapped_column(Text)
    acknowledged_by: Mapped[str | None] = mapped_column(String(64))
    ack_ts: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    notified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    notify_count: Mapped[int] = mapped_column(Integer, default=0)
    received_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("device_id", "seq", "ts", name="uq_alert_dedupe"),)


class Forecast(Base):
    __tablename__ = "forecasts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    issued_for: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))  # mốc thời gian dữ liệu cuối
    horizon: Mapped[int] = mapped_column(Integer)
    target: Mapped[str] = mapped_column(String(16))  # temp | hum | pres | rain_prob
    value: Mapped[float] = mapped_column(Float)
    lower: Mapped[float | None] = mapped_column(Float)
    upper: Mapped[float | None] = mapped_column(Float)
    model_ver: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str | None] = mapped_column(String(16))  # station | open-meteo | fallback


class Nowcast(Base):
    __tablename__ = "nowcasts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    code: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str | None] = mapped_column(String(64))
    trend: Mapped[int | None] = mapped_column(Integer)
    trend_3h: Mapped[float | None] = mapped_column(Float)
    zambretti: Mapped[str | None] = mapped_column(String(2))


class DeviceConfig(Base):
    __tablename__ = "device_configs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer)
    config: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[str | None] = mapped_column(String(64))
    acked: Mapped[bool] = mapped_column(Boolean, default=False)
    acked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Command(Base):
    __tablename__ = "commands"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    cmd: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[str | None] = mapped_column(String(64))
    acked: Mapped[bool] = mapped_column(Boolean, default=False)
    acked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    ack_msg: Mapped[str | None] = mapped_column(String(128))


class ModelRegistryEntry(Base):
    __tablename__ = "model_registry"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    model_ver: Mapped[str] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(32))
    path: Mapped[str | None] = mapped_column(String(256))
    metric_name: Mapped[str | None] = mapped_column(String(64))
    metric_value: Mapped[float | None] = mapped_column(Float)
    metrics: Mapped[dict | None] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("name", "model_ver", name="uq_model_ver"),)


class Notification(Base):
    """Nhật ký thông báo đã gửi (Telegram/Email) — phục vụ cooldown và đo độ trễ end-to-end."""
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id"))
    channel: Mapped[str] = mapped_column(String(16))
    sent_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    text: Mapped[str | None] = mapped_column(Text)
