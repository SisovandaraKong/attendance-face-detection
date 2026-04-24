"""Lightweight authentication helpers for thesis-sized admin access."""

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from sqlalchemy import select

from database.models import SystemUser

TOKEN_TTL_SECONDS = int(os.getenv("ACCESS_TOKEN_TTL_SECONDS", "28800"))
SECRET_KEY = os.getenv("APP_SECRET_KEY", "change-me-in-production")

ROLE_ALIASES = {
    "system_admin": "super_admin",
    "super_admin": "super_admin",
    "hr_admin": "hr_admin",
}


def hash_password(password: str, salt: str | None = None) -> str:
    raw_salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        raw_salt.encode("utf-8"),
        200_000,
    ).hex()
    return f"{raw_salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, expected = stored_hash.split("$", 1)
    except ValueError:
        return False
    candidate = hash_password(password, salt=salt).split("$", 1)[1]
    return hmac.compare_digest(candidate, expected)


def _urlsafe_encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("utf-8").rstrip("=")


def _urlsafe_decode(payload: str) -> bytes:
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode(payload + padding)


def create_access_token(user: SystemUser) -> str:
    body = {
        "sub": user.username,
        "uid": user.id,
        "role": normalize_role(user.role),
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    encoded_body = _urlsafe_encode(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        encoded_body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{encoded_body}.{signature}"


def verify_access_token(token: str) -> dict[str, Any] | None:
    try:
        encoded_body, signature = token.split(".", 1)
    except ValueError:
        return None

    expected = hmac.new(
        SECRET_KEY.encode("utf-8"),
        encoded_body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None

    try:
        body = json.loads(_urlsafe_decode(encoded_body).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None

    if body.get("exp", 0) < int(time.time()):
        return None
    return body


def authenticate_user(username: str, password: str) -> SystemUser | None:
    from database.session import get_db_session

    with get_db_session() as session:
        user = session.scalar(select(SystemUser).where(SystemUser.username == username))
        if user is None or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        user.last_login_at = func_now()
        session.flush()
        return user


def get_user_by_username(username: str) -> SystemUser | None:
    from database.session import get_db_session

    with get_db_session() as session:
        return session.scalar(select(SystemUser).where(SystemUser.username == username))


def func_now():
    import datetime as _dt

    return _dt.datetime.now(_dt.timezone.utc)


def normalize_role(role: str | None) -> str:
    if not role:
        return "hr_admin"
    return ROLE_ALIASES.get(role.strip().lower(), role.strip().lower())
