import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    """App FastAPI với SQLite tạm, không MQTT thật, không scheduler."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("MQTT_ENABLED", "false")
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_TOKEN", "")
    monkeypatch.setenv("SMTP_HOST", "")
    monkeypatch.setenv("USE_OPEN_METEO_FALLBACK", "false")
    monkeypatch.setenv("NOTIFY_COOLDOWN_S", "120")
    from app.core.config import get_settings
    get_settings.cache_clear()
    from app.db import session
    session.init_engine(os.environ["DATABASE_URL"])
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


@pytest.fixture()
def token(app_client):
    r = app_client.post("/api/auth/token", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
