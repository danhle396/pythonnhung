"""Xác thực JWT (HS256) cho các API ghi."""
from __future__ import annotations

import datetime as dt
import hmac

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.core.config import get_settings

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


def authenticate(username: str, password: str) -> bool:
    s = get_settings()
    return hmac.compare_digest(username, s.admin_user) and hmac.compare_digest(password, s.admin_pass)


def create_token(sub: str) -> str:
    s = get_settings()
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=s.jwt_expire_min)
    return jwt.encode({"sub": sub, "exp": exp}, s.jwt_secret, algorithm="HS256")


def require_user(token: str | None = Depends(oauth2)) -> str:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Thiếu token", headers={"WWW-Authenticate": "Bearer"})
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])["sub"]
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token không hợp lệ", headers={"WWW-Authenticate": "Bearer"})
