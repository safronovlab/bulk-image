"""
FastAPI Depends — авторизация, rate limiting, инъекция сервисов.
"""

from __future__ import annotations

import time
import threading
from typing import Optional

from fastapi import HTTPException, Request

# Global service instances (set by main.py)
_image_service = None
_job_service = None
_preset_service = None
_auth_provider = None

# Rate limit storage — recreated on each init_services call
_rate_state: Optional["RateLimitState"] = None


class RateLimitState:
    """Rate limit state that is recreated per service initialization."""

    def __init__(self) -> None:
        self._stores: dict[str, dict[str, list[float]]] = {
            "login": {},
            "upload": {},
            "pick_color": {},
            "dominant_colors": {},
            "suggest": {},
            "preview": {},
        }
        self._lock = threading.Lock()

    def check(self, store_key: str, key: str, max_requests: int, window: float = 60.0) -> None:
        now = time.time()
        with self._lock:
            store = self._stores[store_key]
            if key not in store:
                store[key] = []

            store[key] = [t for t in store[key] if now - t < window]

            if len(store[key]) >= max_requests:
                raise HTTPException(status_code=429, detail="Rate limit exceeded")

            store[key].append(now)


def get_current_session(request: Request, auth_provider: object = None) -> str:
    """Извлечь и валидировать Bearer token."""
    if auth_provider is None:
        auth_provider = _auth_provider

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Authorization header required")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")

    token = auth_header[7:]

    # Валидация длины токена ДО обращения к auth_provider
    if len(token) != 32:
        raise HTTPException(status_code=401, detail="Invalid token format")

    session_id = auth_provider.validate_token(token)
    if session_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return session_id


def get_raw_token(request: Request) -> str:
    """Извлечь raw token из header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Authorization header required")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")

    return auth_header[7:]


def rate_limit_login(request: Request) -> None:
    """Rate limit: 5 login/мин по IP."""
    ip = request.client.host if request.client else "unknown"
    if _rate_state is not None:
        _rate_state.check("login", ip, 5)


def rate_limit_upload(session_id: str) -> None:
    """Rate limit: 10 upload/мин по session."""
    if _rate_state is not None:
        _rate_state.check("upload", session_id, 10)


def rate_limit_pick_color(session_id: str) -> None:
    """Rate limit: 60 pick-color/мин."""
    if _rate_state is not None:
        _rate_state.check("pick_color", session_id, 60)


def rate_limit_dominant_colors(session_id: str) -> None:
    """Rate limit: 20 dominant-colors/мин."""
    if _rate_state is not None:
        _rate_state.check("dominant_colors", session_id, 20)


def rate_limit_suggest(session_id: str) -> None:
    """Rate limit: 10 suggest/мин."""
    if _rate_state is not None:
        _rate_state.check("suggest", session_id, 10)


def rate_limit_preview(session_id: str) -> None:
    """Rate limit: 30 preview/мин."""
    if _rate_state is not None:
        _rate_state.check("preview", session_id, 30)


def get_image_service():
    return _image_service


def get_job_service():
    return _job_service


def get_preset_service():
    return _preset_service


def get_auth_provider():
    return _auth_provider


def init_services(image_service, job_service, preset_service, auth_provider):
    """Инициализация глобальных сервисов (вызывается из main.py)."""
    global _image_service, _job_service, _preset_service, _auth_provider, _rate_state
    _image_service = image_service
    _job_service = job_service
    _preset_service = preset_service
    _auth_provider = auth_provider
    # Fresh rate limit state
    _rate_state = RateLimitState()
