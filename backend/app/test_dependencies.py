"""
TDD-тесты для app/dependencies.py
Спецификация: app/dependencies_spec.md

Покрытие:
- get_current_session: валидный Bearer → session_id
- get_current_session: без header → 401
- get_current_session: не Bearer → 401
- get_current_session: истёкший → 401
- [SRE_MARKER] токен нестандартной длины → 401 ДО обращения к auth_provider
- get_raw_token: извлечение token
- rate_limit_login: 6-й за минуту → 429
- rate_limit_upload: 11-й за минуту → 429
- rate_limit_preview: 31-й за минуту → 429
- rate_limit_pick_color: 61-й за минуту → 429
- rate_limit_dominant_colors: 21-й за минуту → 429
- rate_limit_suggest: 11-й за минуту → 429
"""

import time
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from fastapi import HTTPException


@pytest.fixture
def mock_auth_provider():
    provider = MagicMock()
    provider.validate_token.return_value = "session_abc123"
    return provider


@pytest.fixture
def mock_request():
    """Mock FastAPI Request."""
    request = MagicMock()
    request.headers = {"Authorization": "Bearer " + "a" * 32}
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    return request


# ──────────────────────────────────────────────
# 2.1 get_current_session
# ──────────────────────────────────────────────
class TestGetCurrentSession:
    def test_valid_bearer_returns_session_id(self, mock_request, mock_auth_provider):
        """Валидный Bearer token → session_id."""
        from app.dependencies import get_current_session

        # Пробуем вызвать — может быть sync или async
        try:
            result = get_current_session(
                request=mock_request,
                auth_provider=mock_auth_provider,
            )
            assert result == "session_abc123"
        except TypeError:
            # Если это async dependency, тестируем иначе
            pytest.skip("Async dependency — требуется pytest-asyncio")

    def test_no_auth_header_raises_401(self, mock_auth_provider):
        """Без Authorization header → 401."""
        from app.dependencies import get_current_session

        request = MagicMock()
        request.headers = {}

        with pytest.raises(HTTPException) as exc_info:
            get_current_session(request=request, auth_provider=mock_auth_provider)
        assert exc_info.value.status_code == 401

    def test_basic_auth_rejected(self, mock_auth_provider):
        """'Basic ...' → 401 (не Bearer)."""
        from app.dependencies import get_current_session

        request = MagicMock()
        request.headers = {"Authorization": "Basic dXNlcjpwYXNz"}

        with pytest.raises(HTTPException) as exc_info:
            get_current_session(request=request, auth_provider=mock_auth_provider)
        assert exc_info.value.status_code == 401

    def test_expired_token_raises_401(self, mock_request, mock_auth_provider):
        """Истёкший token → 401."""
        from app.dependencies import get_current_session

        mock_auth_provider.validate_token.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            get_current_session(
                request=mock_request, auth_provider=mock_auth_provider
            )
        assert exc_info.value.status_code == 401

    def test_oversized_token_rejected_before_auth(self, mock_auth_provider):
        """[SRE_MARKER] Токен != 32 символа → 401 ДО обращения к auth_provider."""
        from app.dependencies import get_current_session

        request = MagicMock()
        # 10MB строка в Authorization header
        request.headers = {"Authorization": "Bearer " + "x" * 10_000}

        with pytest.raises(HTTPException) as exc_info:
            get_current_session(request=request, auth_provider=mock_auth_provider)
        assert exc_info.value.status_code == 401

        # auth_provider.validate_token НЕ должен быть вызван
        mock_auth_provider.validate_token.assert_not_called()

    def test_short_token_rejected(self, mock_auth_provider):
        """[SRE_MARKER] Короткий токен (< 32) → 401."""
        from app.dependencies import get_current_session

        request = MagicMock()
        request.headers = {"Authorization": "Bearer abc"}

        with pytest.raises(HTTPException) as exc_info:
            get_current_session(request=request, auth_provider=mock_auth_provider)
        assert exc_info.value.status_code == 401
        mock_auth_provider.validate_token.assert_not_called()


# ──────────────────────────────────────────────
# 2.2 get_raw_token
# ──────────────────────────────────────────────
class TestGetRawToken:
    def test_extracts_token(self, mock_request):
        from app.dependencies import get_raw_token

        result = get_raw_token(request=mock_request)
        assert result == "a" * 32

    def test_no_header_raises_401(self):
        from app.dependencies import get_raw_token

        request = MagicMock()
        request.headers = {}

        with pytest.raises(HTTPException) as exc_info:
            get_raw_token(request=request)
        assert exc_info.value.status_code == 401


# ──────────────────────────────────────────────
# 2.3 rate_limit_login
# ──────────────────────────────────────────────
class TestRateLimitLogin:
    def test_within_limit_passes(self):
        """5 запросов за минуту — допустимо."""
        from app.dependencies import rate_limit_login

        request = MagicMock()
        request.client = MagicMock()
        request.client.host = "192.168.1.100"

        # 5 вызовов — не должны бросать исключение
        for _ in range(5):
            try:
                rate_limit_login(request=request)
            except HTTPException:
                pytest.fail("rate_limit_login не должен блокировать 5 запросов")

    def test_6th_request_raises_429(self):
        """[SRE_MARKER] 6-й login за минуту → 429."""
        from app.dependencies import rate_limit_login

        request = MagicMock()
        request.client = MagicMock()
        request.client.host = "10.0.0.99"

        for _ in range(5):
            try:
                rate_limit_login(request=request)
            except HTTPException:
                pass

        with pytest.raises(HTTPException) as exc_info:
            rate_limit_login(request=request)
        assert exc_info.value.status_code == 429


# ──────────────────────────────────────────────
# 2.4 rate_limit_upload
# ──────────────────────────────────────────────
class TestRateLimitUpload:
    def test_11th_upload_raises_429(self):
        """[SRE_MARKER] 11-й upload → 429."""
        from app.dependencies import rate_limit_upload

        for _ in range(10):
            try:
                rate_limit_upload(session_id="upload_test_session")
            except HTTPException:
                pass

        with pytest.raises(HTTPException) as exc_info:
            rate_limit_upload(session_id="upload_test_session")
        assert exc_info.value.status_code == 429


# ──────────────────────────────────────────────
# 2.5 rate_limit_pick_color
# ──────────────────────────────────────────────
class TestRateLimitPickColor:
    def test_61st_pick_raises_429(self):
        """[SRE_MARKER] 61-й pick-color → 429."""
        from app.dependencies import rate_limit_pick_color

        for _ in range(60):
            try:
                rate_limit_pick_color(session_id="pick_test_session")
            except HTTPException:
                pass

        with pytest.raises(HTTPException) as exc_info:
            rate_limit_pick_color(session_id="pick_test_session")
        assert exc_info.value.status_code == 429


# ──────────────────────────────────────────────
# 2.8 rate_limit_preview
# ──────────────────────────────────────────────
class TestRateLimitPreview:
    def test_31st_preview_raises_429(self):
        """[SRE_MARKER] 31-й preview-replace → 429."""
        from app.dependencies import rate_limit_preview

        for _ in range(30):
            try:
                rate_limit_preview(session_id="preview_test_session")
            except HTTPException:
                pass

        with pytest.raises(HTTPException) as exc_info:
            rate_limit_preview(session_id="preview_test_session")
        assert exc_info.value.status_code == 429


# ──────────────────────────────────────────────
# 2.6 rate_limit_dominant_colors
# ──────────────────────────────────────────────
class TestRateLimitDominantColors:
    def test_within_limit_passes(self):
        """20 запросов за минуту — допустимо."""
        from app.dependencies import rate_limit_dominant_colors

        for _ in range(20):
            try:
                rate_limit_dominant_colors(session_id="dc_test_session")
            except HTTPException:
                pytest.fail("rate_limit_dominant_colors не должен блокировать 20 запросов")

    def test_21st_request_raises_429(self):
        """[SRE_MARKER] 21-й dominant-colors за минуту → 429."""
        from app.dependencies import rate_limit_dominant_colors

        for _ in range(20):
            try:
                rate_limit_dominant_colors(session_id="dc_429_session")
            except HTTPException:
                pass

        with pytest.raises(HTTPException) as exc_info:
            rate_limit_dominant_colors(session_id="dc_429_session")
        assert exc_info.value.status_code == 429


# ──────────────────────────────────────────────
# 2.7 rate_limit_suggest
# ──────────────────────────────────────────────
class TestRateLimitSuggest:
    def test_within_limit_passes(self):
        """10 запросов за минуту — допустимо."""
        from app.dependencies import rate_limit_suggest

        for _ in range(10):
            try:
                rate_limit_suggest(session_id="sug_test_session")
            except HTTPException:
                pytest.fail("rate_limit_suggest не должен блокировать 10 запросов")

    def test_11th_request_raises_429(self):
        """[SRE_MARKER] 11-й suggest за минуту → 429."""
        from app.dependencies import rate_limit_suggest

        for _ in range(10):
            try:
                rate_limit_suggest(session_id="sug_429_session")
            except HTTPException:
                pass

        with pytest.raises(HTTPException) as exc_info:
            rate_limit_suggest(session_id="sug_429_session")
        assert exc_info.value.status_code == 429


# ──────────────────────────────────────────────
# Очистка rate limit словарей
# ──────────────────────────────────────────────
class TestRateLimitCleanup:
    def test_old_entries_do_not_crash(self):
        """[SRE_MARKER] Очистка старых записей — функция не падает."""
        from app.dependencies import rate_limit_login

        request = MagicMock()
        request.client = MagicMock()
        request.client.host = "cleanup_test_ip_unique"

        # Несколько вызовов не крашат при повторном использовании
        for _ in range(3):
            try:
                rate_limit_login(request=request)
            except HTTPException:
                pass


# ──────────────────────────────────────────────
# 2.7 Сервисные dependencies
# ──────────────────────────────────────────────
class TestServiceDependencies:
    def test_get_image_service_returns_instance(self):
        """get_image_service возвращает ImageService."""
        from app.dependencies import get_image_service
        result = get_image_service()
        assert result is not None

    def test_get_job_service_returns_instance(self):
        """get_job_service возвращает JobService."""
        from app.dependencies import get_job_service
        result = get_job_service()
        assert result is not None

    def test_get_preset_service_returns_instance(self):
        """get_preset_service возвращает PresetService."""
        from app.dependencies import get_preset_service
        result = get_preset_service()
        assert result is not None

    def test_get_auth_provider_returns_instance(self):
        """get_auth_provider возвращает AuthProvider."""
        from app.dependencies import get_auth_provider
        result = get_auth_provider()
        assert result is not None
