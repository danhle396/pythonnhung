"""Cấu hình backend, đọc từ biến môi trường / file .env (xem .env.example ở thư mục gốc)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(REPO_DIR / ".env", ".env"), extra="ignore")

    app_name: str = "VKU AIoT Station API"
    database_url: str = f"sqlite:///{(REPO_DIR / 'backend' / 'aiot.db').as_posix()}"

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_user: str = "backend"
    mqtt_pass: str = "backend-pass"
    mqtt_topic_prefix: str = "vku/aiot"
    mqtt_enabled: bool = True

    jwt_secret: str = "change-me-in-production"
    jwt_expire_min: int = 720
    admin_user: str = "admin"
    admin_pass: str = "admin123"

    telegram_token: str = ""
    telegram_chat_id: str = ""
    telegram_poll: bool = True
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_pass: str = ""
    alert_email_to: str = ""
    dashboard_url: str = "http://localhost:8501"

    station_lat: float = 15.975
    station_lon: float = 108.253
    station_alt_m: float = 8.0
    station_tz: str = "Asia/Ho_Chi_Minh"
    default_device_id: str = "station01"

    offline_after_s: int = 60
    notify_cooldown_s: int = 120
    reminder_every_s: int = 60
    forecast_every_min: int = 10
    escalation_window_min: int = 10
    escalation_slope_ppm_min: float = 20.0
    ml_registry: str = str(REPO_DIR / "ml" / "models" / "registry.json")
    anomaly_model: str = str(REPO_DIR / "ml" / "models" / "gas_anomaly.json")
    scheduler_enabled: bool = True
    use_open_meteo_fallback: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
