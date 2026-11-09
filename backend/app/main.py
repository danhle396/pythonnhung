"""FastAPI app: REST + WebSocket + MQTT ingest + scheduler (forecast, leo thang, offline, nhắc lại, tin 6h sáng).

    uvicorn app.main:app --reload            (thư mục backend/)
Swagger: http://localhost:8000/docs
"""
from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api import routes, ws
from app.core.config import get_settings
from app.db.models import Device
from app.db.session import SessionLocal, create_all, get_engine
from app.mqtt.ingest import MqttService
from app.runtime import build_runtime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("aiot")


def _ensure_device(settings):
    with SessionLocal() as s:
        if s.get(Device, settings.default_device_id) is None:
            s.add(Device(id=settings.default_device_id, name="Trạm VKU 01",
                         location="VKU, 470 Trần Đại Nghĩa, Ngũ Hành Sơn, Đà Nẵng", lat=settings.station_lat,
                         lon=settings.station_lon, altitude=settings.station_alt_m, status="unknown"))
            s.commit()
        routes.sync_registry(s, settings.ml_registry)


def start_scheduler(r):
    from apscheduler.schedulers.background import BackgroundScheduler
    s = r.settings
    sch = BackgroundScheduler(timezone=s.station_tz, job_defaults={"coalesce": True, "max_instances": 1})

    def evaluate_all():
        with SessionLocal() as db:
            ids = [d.id for d in db.scalars(select(Device).where(Device.status == "online"))]
        for i in ids:
            r.alerts.evaluate(i)

    def forecast_all():
        with SessionLocal() as db:
            ids = [d.id for d in db.scalars(select(Device))] or [s.default_device_id]
        for i in ids:
            try:
                r.forecast.run_once(i)
            except Exception:
                log.exception("forecast lỗi")

    sch.add_job(forecast_all, "interval", minutes=s.forecast_every_min, id="forecast")
    sch.add_job(evaluate_all, "interval", seconds=30, id="escalation")
    sch.add_job(r.alerts.check_offline, "interval", seconds=15, id="offline")
    sch.add_job(r.alerts.reminders, "interval", seconds=20, id="reminders")
    sch.add_job(r.forecast.daily_summary, "cron", hour=6, minute=0, id="daily_summary")
    sch.start()
    # chạy forecast lần đầu sau 20 s (không chặn khởi động)
    threading.Timer(20, forecast_all).start()
    return sch


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    get_engine()
    create_all()  # production: alembic upgrade head (docker entrypoint) — create_all không làm gì nếu bảng đã có
    _ensure_device(settings)
    r = build_runtime(settings)
    r.hub.attach_loop(asyncio.get_running_loop())
    r.mqtt = MqttService(settings, r.publisher, r.hub, r.alerts)
    r.mqtt.start()
    stop = threading.Event()
    if settings.scheduler_enabled:
        r.scheduler = start_scheduler(r)
    if settings.telegram_poll and r.notifier.telegram_enabled:
        threading.Thread(target=r.notifier.poll_forever, args=(r.alerts.ack, stop), daemon=True,
                         name="telegram-poll").start()
    log.info("Backend sẵn sàng — DB %s", settings.database_url.split("@")[-1])
    yield
    stop.set()
    if r.scheduler:
        r.scheduler.shutdown(wait=False)
    r.mqtt.stop()


app = FastAPI(title="VKU AIoT Station API", version="1.0.0", lifespan=lifespan,
              description="Trạm quan trắc môi trường AIoT — dự báo thời tiết ngắn hạn & cảnh báo khí/khói đa cấp")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(routes.router)
app.include_router(ws.router)


@app.get("/", include_in_schema=False)
def root():
    return {"app": "VKU AIoT Station", "docs": "/docs"}
