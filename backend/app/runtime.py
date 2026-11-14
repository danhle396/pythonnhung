from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.mqtt.publisher import Publisher
from app.services.alert_service import AlertService
from app.services.forecast_service import ForecastService
from app.services.hub import Hub
from app.services.notifier import Notifier


@dataclass
class Runtime:
    settings: Settings
    hub: Hub
    notifier: Notifier
    publisher: Publisher
    alerts: AlertService
    forecast: ForecastService
    mqtt: object = None
    scheduler: object = None


_rt: Runtime | None = None


def build_runtime(settings: Settings | None = None) -> Runtime:
    global _rt
    s = settings or get_settings()
    hub = Hub()
    notifier = Notifier(s)
    pub = Publisher(s.mqtt_topic_prefix)
    alerts = AlertService(s, notifier, pub, hub)
    fc = ForecastService(s, pub, hub, notifier)
    _rt = Runtime(s, hub, notifier, pub, alerts, fc)
    return _rt


def rt() -> Runtime:
    if _rt is None:
        return build_runtime()
    return _rt
