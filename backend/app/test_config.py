"""
TDD-тесты для app/config.py
Спецификация: app/config_spec.md

Покрытие:
- Все переменные заданы → Settings создаётся
- AUTH_USERNAME не задан → ValidationError
- AUTH_PASSWORD не задан → ValidationError
- Значения по умолчанию
- CORS_ORIGINS парсится из JSON-строки
- [SRE_MARKER] Минимальная длина пароля >= 12
- [SRE_MARKER] Запрет шаблонных паролей
- [SRE_MARKER] Запрет CORS wildcard ["*"]
- [SRE_MARKER] Верхние границы числовых параметров
- [SRE_MARKER] Валидация путей (path traversal)
"""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError


def _env_with(**overrides):
    """Базовый набор env-переменных для корректного Settings."""
    base = {
        "AUTH_USERNAME": "admin",
        "AUTH_PASSWORD": "VeryStrongPass123!",
        "CORS_ORIGINS": '["http://localhost:3000"]',
        "UPLOAD_DIR": "/tmp/test_uploads",
        "PREVIEW_DIR": "/tmp/test_previews",
        "RESULT_DIR": "/tmp/test_results",
        "PRESETS_PATH": "/tmp/test_presets.json",
    }
    base.update(overrides)
    return base


class TestSettingsValid:
    def test_all_variables_set(self):
        """Все переменные заданы → Settings создаётся."""
        from app.config import Settings

        with patch.dict(os.environ, _env_with(), clear=False):
            settings = Settings()
            assert settings.AUTH_USERNAME == "admin"

    def test_default_max_upload_size(self):
        from app.config import Settings

        with patch.dict(os.environ, _env_with(), clear=False):
            settings = Settings()
            assert settings.MAX_UPLOAD_SIZE_MB == 50

    def test_default_max_total_upload(self):
        from app.config import Settings

        with patch.dict(os.environ, _env_with(), clear=False):
            settings = Settings()
            assert settings.MAX_TOTAL_UPLOAD_MB == 500

    def test_default_max_files(self):
        from app.config import Settings

        with patch.dict(os.environ, _env_with(), clear=False):
            settings = Settings()
            assert settings.MAX_FILES_PER_UPLOAD == 20

    def test_default_file_ttl(self):
        from app.config import Settings

        with patch.dict(os.environ, _env_with(), clear=False):
            settings = Settings()
            assert settings.FILE_TTL_HOURS == 24

    def test_default_token_ttl(self):
        from app.config import Settings

        with patch.dict(os.environ, _env_with(), clear=False):
            settings = Settings()
            assert settings.TOKEN_TTL_HOURS == 24

    def test_cors_origins_parsed(self):
        """CORS_ORIGINS парсится из JSON-строки."""
        from app.config import Settings

        env = _env_with(CORS_ORIGINS='["http://localhost:3000","https://app.example.com"]')
        with patch.dict(os.environ, env, clear=False):
            settings = Settings()
            assert isinstance(settings.CORS_ORIGINS, list)
            assert len(settings.CORS_ORIGINS) == 2


class TestSettingsRequired:
    def test_auth_username_missing(self):
        """AUTH_USERNAME не задан → ValidationError."""
        from app.config import Settings

        env = _env_with()
        del env["AUTH_USERNAME"]
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError):
                Settings()

    def test_auth_password_missing(self):
        """AUTH_PASSWORD не задан → ValidationError."""
        from app.config import Settings

        env = _env_with()
        del env["AUTH_PASSWORD"]
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError):
                Settings()


class TestPasswordValidation:
    def test_password_min_12_chars(self):
        """[SRE_MARKER] Пароль < 12 символов → ValidationError."""
        from app.config import Settings

        env = _env_with(AUTH_PASSWORD="short")
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValidationError):
                Settings()

    def test_password_exactly_12_chars(self):
        """Пароль ровно 12 символов → допустимо."""
        from app.config import Settings

        env = _env_with(AUTH_PASSWORD="Abcdef123456")
        with patch.dict(os.environ, env, clear=False):
            settings = Settings()
            assert settings.AUTH_PASSWORD.get_secret_value() == "Abcdef123456"

    def test_template_password_change_me_rejected(self):
        """[SRE_MARKER] Шаблонный пароль 'change_me_to_strong_password' → отклонён."""
        from app.config import Settings

        env = _env_with(AUTH_PASSWORD="change_me_to_strong_password")
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValidationError):
                Settings()

    def test_template_password_password_rejected(self):
        """[SRE_MARKER] Шаблонный пароль 'password' → отклонён."""
        from app.config import Settings

        env = _env_with(AUTH_PASSWORD="password")
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValidationError):
                Settings()

    def test_template_password_admin_rejected(self):
        """[SRE_MARKER] Шаблонный пароль 'admin' → отклонён."""
        from app.config import Settings

        env = _env_with(AUTH_PASSWORD="admin")
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValidationError):
                Settings()

    def test_template_password_123456_rejected(self):
        """[SRE_MARKER] Шаблонный пароль '123456' → отклонён."""
        from app.config import Settings

        env = _env_with(AUTH_PASSWORD="123456")
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValidationError):
                Settings()

    def test_password_is_secret_str(self):
        """AUTH_PASSWORD — SecretStr, маскируется при repr."""
        from app.config import Settings

        with patch.dict(os.environ, _env_with(), clear=False):
            settings = Settings()
            # repr не должен содержать реальный пароль
            repr_str = repr(settings.AUTH_PASSWORD)
            assert "VeryStrongPass123!" not in repr_str


class TestCorsValidation:
    def test_cors_wildcard_rejected(self):
        """[SRE_MARKER] CORS_ORIGINS=["*"] → отклонён."""
        from app.config import Settings

        env = _env_with(CORS_ORIGINS='["*"]')
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValidationError):
                Settings()


class TestNumericUpperBounds:
    def test_max_upload_size_upper_bound(self):
        """[SRE_MARKER] MAX_UPLOAD_SIZE_MB <= 200."""
        from app.config import Settings

        env = _env_with(MAX_UPLOAD_SIZE_MB="999999")
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValidationError):
                Settings()

    def test_max_total_upload_upper_bound(self):
        """[SRE_MARKER] MAX_TOTAL_UPLOAD_MB <= 2000."""
        from app.config import Settings

        env = _env_with(MAX_TOTAL_UPLOAD_MB="999999")
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValidationError):
                Settings()

    def test_max_files_upper_bound(self):
        """[SRE_MARKER] MAX_FILES_PER_UPLOAD <= 50."""
        from app.config import Settings

        env = _env_with(MAX_FILES_PER_UPLOAD="100")
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValidationError):
                Settings()

    def test_job_timeout_upper_bound(self):
        """[SRE_MARKER] JOB_TIMEOUT_SECONDS <= 3600."""
        from app.config import Settings

        env = _env_with(JOB_TIMEOUT_SECONDS="99999")
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValidationError):
                Settings()

    def test_max_image_pixels_upper_bound(self):
        """[SRE_MARKER] MAX_IMAGE_PIXELS <= 100_000_000."""
        from app.config import Settings

        env = _env_with(MAX_IMAGE_PIXELS="999999999")
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValidationError):
                Settings()


class TestPathValidation:
    def test_upload_dir_etc_rejected(self):
        """[SRE_MARKER] UPLOAD_DIR=/etc → отклонён (path traversal при старте)."""
        from app.config import Settings

        env = _env_with(UPLOAD_DIR="/etc")
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValidationError):
                Settings()

    def test_upload_dir_proc_rejected(self):
        """[SRE_MARKER] UPLOAD_DIR=/proc → отклонён."""
        from app.config import Settings

        env = _env_with(UPLOAD_DIR="/proc")
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValidationError):
                Settings()

    def test_preview_dir_outside_app_rejected(self):
        """[SRE_MARKER] PREVIEW_DIR за пределами app root → отклонён."""
        from app.config import Settings

        env = _env_with(PREVIEW_DIR="/var/log/evil")
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValidationError):
                Settings()

    def test_result_dir_traversal_rejected(self):
        """[SRE_MARKER] RESULT_DIR с .. → отклонён."""
        from app.config import Settings

        env = _env_with(RESULT_DIR="/app/data/../../../etc")
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValidationError):
                Settings()

    def test_presets_path_outside_rejected(self):
        """[SRE_MARKER] PRESETS_PATH за пределами app → отклонён."""
        from app.config import Settings

        env = _env_with(PRESETS_PATH="/etc/shadow")
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValidationError):
                Settings()
