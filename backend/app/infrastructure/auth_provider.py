"""
Адаптер авторизации. Проверка credentials, управление сессионными токенами.
"""

from __future__ import annotations

import hmac
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass
class TokenData:
    session_id: str
    created_at: datetime
    expires_at: datetime


class AuthProvider:
    def __init__(self, config: object) -> None:
        self._config = config
        self._tokens: dict[str, TokenData] = {}
        self._lock = threading.RLock()

    def authenticate(
        self, username: str, password: str
    ) -> Optional[tuple[str, str, datetime]]:
        """Проверка credentials. Возвращает (token, session_id, expires_at) или None."""
        expected_username: str = self._config.AUTH_USERNAME
        expected_password_obj = self._config.AUTH_PASSWORD
        # Support SecretStr
        if hasattr(expected_password_obj, "get_secret_value"):
            expected_password: str = expected_password_obj.get_secret_value()
        else:
            expected_password = str(expected_password_obj)

        # Constant-time comparison для обоих полей (ВСЕГДА оба проверяются)
        username_ok = hmac.compare_digest(username, expected_username)
        password_ok = hmac.compare_digest(password, expected_password)

        if not (username_ok and password_ok):
            return None

        token = uuid.uuid4().hex
        session_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        ttl_hours = getattr(self._config, "TOKEN_TTL_HOURS", 24)
        expires_at = now + timedelta(hours=ttl_hours)

        token_data = TokenData(
            session_id=session_id,
            created_at=now,
            expires_at=expires_at,
        )

        with self._lock:
            # Лимит 100 токенов
            if len(self._tokens) >= 100:
                # Удалить старейший токен
                oldest_key = min(
                    self._tokens, key=lambda k: self._tokens[k].created_at
                )
                del self._tokens[oldest_key]

            self._tokens[token] = token_data

        return (token, session_id, expires_at)

    def validate_token(self, token: str) -> Optional[str]:
        """Валидация токена. Возвращает session_id или None."""
        with self._lock:
            token_data = self._tokens.get(token)
            if token_data is None:
                return None
            if token_data.expires_at < datetime.now(timezone.utc):
                del self._tokens[token]
                return None
            return token_data.session_id

    def invalidate_token(self, token: str) -> bool:
        """Инвалидация токена. True если удалён."""
        with self._lock:
            if token in self._tokens:
                del self._tokens[token]
                return True
            return False

    def cleanup_expired_tokens(self) -> int:
        """Удаление просроченных токенов. Возвращает количество."""
        now = datetime.now(timezone.utc)
        with self._lock:
            expired_keys = [
                k for k, v in self._tokens.items() if v.expires_at < now
            ]
            for k in expired_keys:
                del self._tokens[k]
        return len(expired_keys)
