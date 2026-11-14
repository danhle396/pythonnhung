from __future__ import annotations

import datetime as dt
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

_engine = None
SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)


def get_engine():
    global _engine
    if _engine is None:
        init_engine(get_settings().database_url)
    return _engine


def init_engine(url: str):
    global _engine
    kw = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kw["connect_args"] = {"check_same_thread": False, "timeout": 30}
    _engine = create_engine(url, **kw)
    if url.startswith("sqlite"):
        @event.listens_for(_engine, "connect")
        def _pragma(conn, _):
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()
    SessionLocal.configure(bind=_engine)
    return _engine


def create_all():
    from .models import Base
    Base.metadata.create_all(get_engine())


@contextmanager
def session_scope():
    get_engine()
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_db():
    get_engine()
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def as_utc(t: dt.datetime | None):
    if t is None:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
