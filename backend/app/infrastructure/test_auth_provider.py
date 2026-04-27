"""
TDD-тесты для infrastructure/auth_provider.py
Спецификация: infrastructure/auth_provider_spec.md

Покрытие:
- authenticate: правильные credentials → token + session_id
- authenticate: неправильный пароль → None
- authenticate: неправильный логин → None
- validate_token: действующий → session_id
- validate_token: истёкший → None, удалён
- validate_token: несуществующий → None
- invalidate_token: существующий → True
- invalidate_token: повторная валидация → None
- cleanup_expired_tokens: expired удаляются
- [SRE_MARKER] hmac.compare_digest для timing attack защиты
- [SRE_MARKER] threading.Lock потокобезопасность
- [SRE_MARKER] лимит 100 токенов (OOM защита)
"""

import time
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_config():
    """Мок конфигурации для AuthProvider."""
    config = MagicMock()
    config.AUTH_USERNAME = "testuser"
    # SecretStr mock
    password_mock = MagicMock()
    password_mock.get_secret_value.return_value = "SuperSecurePass123"
    config.AUTH_PASSWORD = password_mock
    config.TOKEN_TTL_HOURS = 24
    return config


@pytest.fixture
def auth_provider(mock_config):
    from app.infrastructure.auth_provider import AuthProvider
    return AuthProvider(mock_config)


# ──────────────────────────────────────────────
# 4.1 authenticate
# ──────────────────────────────────────────────
class TestAuthenticate:
    def test_correct_credentials_returns_token(self, auth_provider):
        """Правильные credentials → token + session_id + expires_at."""
        result = auth_provider.authenticate("testuser", "SuperSecurePass123")

        assert result is not None
        token, session_id, expires_at = result
        assert isinstance(token, str)
        assert len(token) == 32  # uuid4().hex
        assert isinstance(session_id, str)
        assert len(session_id) == 32
        assert isinstance(expires_at, datetime)

    def test_wrong_password_returns_none(self, auth_provider):
        """Неправильный пароль → None."""
        result = auth_provider.authenticate("testuser", "wrong_password")
        assert result is None

    def test_wrong_username_returns_none(self, auth_provider):
        """Неправильный логин → None."""
        result = auth_provider.authenticate("wronguser", "SuperSecurePass123")
        assert result is None

    def test_both_wrong_returns_none(self, auth_provider):
        """Оба неверные → None."""
        result = auth_provider.authenticate("wrong", "wrong")
        assert result is None

    def test_empty_credentials_returns_none(self, auth_provider):
        """Пустые credentials → None."""
        result = auth_provider.authenticate("", "")
        assert result is None

    def test_token_stored_after_auth(self, auth_provider):
        """Токен сохраняется и может быть валидирован."""
        result = auth_provider.authenticate("testuser", "SuperSecurePass123")
        token, session_id, _ = result

        validated_session = auth_provider.validate_token(token)
        assert validated_session == session_id

    def test_expires_at_in_future(self, auth_provider):
        """expires_at = now + TOKEN_TTL_HOURS."""
        result = auth_provider.authenticate("testuser", "SuperSecurePass123")
        _, _, expires_at = result

        now = datetime.now(timezone.utc)
        assert expires_at > now
        # Примерно +24 часа (допуск 1 минута)
        diff = (expires_at - now).total_seconds()
        assert abs(diff - 24 * 3600) < 60

    def test_unique_tokens_per_login(self, auth_provider):
        """Каждый login генерирует уникальный token."""
        r1 = auth_provider.authenticate("testuser", "SuperSecurePass123")
        r2 = auth_provider.authenticate("testuser", "SuperSecurePass123")
        assert r1[0] != r2[0]  # tokens differ
        assert r1[1] != r2[1]  # session_ids differ


# ──────────────────────────────────────────────
# 4.2 validate_token
# ──────────────────────────────────────────────
class TestValidateToken:
    def test_valid_token_returns_session_id(self, auth_provider):
        result = auth_provider.authenticate("testuser", "SuperSecurePass123")
        token, session_id, _ = result

        assert auth_provider.validate_token(token) == session_id

    def test_nonexistent_token_returns_none(self, auth_provider):
        assert auth_provider.validate_token("nonexistent_token_12345678") is None

    def test_expired_token_returns_none(self, auth_provider):
        """Истёкший token → None, token удалён из хранилища."""
        result = auth_provider.authenticate("testuser", "SuperSecurePass123")
        token = result[0]

        # Искусственно просрочить токен
        # Доступ к внутреннему хранилищу для изменения expires_at
        if hasattr(auth_provider, "_tokens"):
            token_data = auth_provider._tokens.get(token)
            if token_data is not None:
                # Установить expires_at в прошлое
                if hasattr(token_data, "expires_at"):
                    token_data.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
                elif isinstance(token_data, dict):
                    token_data["expires_at"] = datetime.now(timezone.utc) - timedelta(hours=1)

        assert auth_provider.validate_token(token) is None


# ──────────────────────────────────────────────
# 4.3 invalidate_token
# ──────────────────────────────────────────────
class TestInvalidateToken:
    def test_invalidate_existing_returns_true(self, auth_provider):
        result = auth_provider.authenticate("testuser", "SuperSecurePass123")
        token = result[0]

        assert auth_provider.invalidate_token(token) is True

    def test_invalidated_token_no_longer_valid(self, auth_provider):
        result = auth_provider.authenticate("testuser", "SuperSecurePass123")
        token = result[0]

        auth_provider.invalidate_token(token)
        assert auth_provider.validate_token(token) is None

    def test_invalidate_nonexistent_returns_false(self, auth_provider):
        assert auth_provider.invalidate_token("nonexistent_token_abc") is False

    def test_double_invalidate_returns_false(self, auth_provider):
        result = auth_provider.authenticate("testuser", "SuperSecurePass123")
        token = result[0]

        assert auth_provider.invalidate_token(token) is True
        assert auth_provider.invalidate_token(token) is False


# ──────────────────────────────────────────────
# 4.4 cleanup_expired_tokens
# ──────────────────────────────────────────────
class TestCleanupExpiredTokens:
    def test_expired_tokens_removed(self, auth_provider):
        """Создать token, просрочить, cleanup удалит."""
        result = auth_provider.authenticate("testuser", "SuperSecurePass123")
        token = result[0]

        # Просрочить
        if hasattr(auth_provider, "_tokens"):
            token_data = auth_provider._tokens.get(token)
            if token_data is not None:
                if hasattr(token_data, "expires_at"):
                    token_data.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
                elif isinstance(token_data, dict):
                    token_data["expires_at"] = datetime.now(timezone.utc) - timedelta(hours=1)

        count = auth_provider.cleanup_expired_tokens()
        assert count >= 1
        assert auth_provider.validate_token(token) is None

    def test_fresh_tokens_preserved(self, auth_provider):
        """Свежий token не удаляется cleanup."""
        result = auth_provider.authenticate("testuser", "SuperSecurePass123")
        token = result[0]

        count = auth_provider.cleanup_expired_tokens()
        assert auth_provider.validate_token(token) is not None

    def test_returns_count_of_removed(self, auth_provider):
        """Возвращает количество удалённых."""
        count = auth_provider.cleanup_expired_tokens()
        assert isinstance(count, int)
        assert count >= 0


# ──────────────────────────────────────────────
# [SRE_MARKER] Безопасность
# ──────────────────────────────────────────────
class TestAuthProviderSecurity:
    def test_constant_time_comparison_used(self, mock_config):
        """[SRE_MARKER] hmac.compare_digest используется для сравнения."""
        from app.infrastructure.auth_provider import AuthProvider

        provider = AuthProvider(mock_config)

        with patch("hmac.compare_digest", return_value=True) as mock_hmac:
            provider.authenticate("testuser", "SuperSecurePass123")
            # hmac.compare_digest должен быть вызван хотя бы раз
            assert mock_hmac.call_count >= 1

    def test_token_limit_100(self, auth_provider):
        """[SRE_MARKER] Лимит 100 токенов — при превышении удаляется старейший."""
        # Создать 100 токенов
        tokens = []
        for _ in range(100):
            result = auth_provider.authenticate("testuser", "SuperSecurePass123")
            tokens.append(result[0])

        # 101-й login должен успеть (с удалением старейшего)
        result = auth_provider.authenticate("testuser", "SuperSecurePass123")
        assert result is not None

        # Количество токенов не должно превышать 100
        if hasattr(auth_provider, "_tokens"):
            assert len(auth_provider._tokens) <= 100

    def test_thread_safety_concurrent_auth(self, auth_provider):
        """[SRE_MARKER] Потокобезопасность: параллельные authenticate."""
        results = []
        errors = []

        def login():
            try:
                r = auth_provider.authenticate("testuser", "SuperSecurePass123")
                results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=login) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 20
        # Все токены уникальны
        unique_tokens = set(r[0] for r in results if r is not None)
        assert len(unique_tokens) == 20
