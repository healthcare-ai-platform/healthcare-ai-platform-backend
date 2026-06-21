from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

from app.core.config import (
    JWT_ACCESS_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_REFRESH_EXPIRE_DAYS,
    JWT_SECRET,
)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(payload: dict) -> str:
    data = {k: v for k, v in payload.items() if k not in ("exp", "type")}
    data["exp"] = datetime.now(timezone.utc) + timedelta(minutes=JWT_ACCESS_EXPIRE_MINUTES)
    data["type"] = "access"
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(payload: dict) -> str:
    data = {k: v for k, v in payload.items() if k not in ("exp", "type")}
    data["exp"] = datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_EXPIRE_DAYS)
    data["type"] = "refresh"
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
